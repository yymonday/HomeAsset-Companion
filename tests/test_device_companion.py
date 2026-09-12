"""Regression tests for HomeAsset Companion v1.2.0."""

from datetime import date
from types import SimpleNamespace
from pathlib import Path

import aiohttp
import pytest
import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID, STATE_UNAVAILABLE
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.device_companion import (
    MAX_UPLOAD_BYTES,
    _handle_legacy_quick_action,
    _handle_replace_consumable,
    _handle_renew_service,
    _handle_service_charge,
    DeviceCompanionUploadView,
    RENEW_SCHEMA,
    REPLACE_SCHEMA,
    SERVICE_CHARGE_SCHEMA,
    async_migrate_entry,
)
from custom_components.device_companion.config_flow import DeviceCompanionConfigFlow
from custom_components.device_companion.const import (
    CONF_ACCESSORIES_LIST,
    CONF_AUTO_RECORD_REPLACEMENT,
    CONF_CONSUMABLES_LIST,
    CONF_CURRENT_PERIOD_COST,
    CONF_EXPIRATION_DATE,
    CONF_PLAN_MONTHLY_PRICE,
    CONF_SERVICE_CHARGES,
    CONF_SERVICE_PAYMENTS,
    CONF_SERVICE_PERIOD_MONTHS,
    CONF_CATEGORY,
    CONF_DEVICE_NAME,
    CONF_KIND,
    CONF_LINKED_ENTITY,
    CONF_PURCHASE_DATE,
    CONF_SUB_PERIOD,
    CONF_TRACKING_MODE,
    CONF_TOTAL_PRICE,
    DOMAIN,
    KIND_SERVICE,
    TRACKING_MODE_SMART,
)
from custom_components.device_companion.sensor import DeviceCompanionSensor
from custom_components.device_companion.helpers import today_local


class FakeConfigEntries:
    """Small Config Entry manager for service and migration unit tests."""

    def __init__(self, entry):
        self.entry = entry

    def async_get_entry(self, entry_id):
        return self.entry if entry_id == self.entry.entry_id else None

    def async_update_entry(self, entry, **changes):
        for key, value in changes.items():
            setattr(entry, key, value)


@pytest.mark.asyncio
async def test_service_config_records_actual_prepaid_coverage(monkeypatch):
    monkeypatch.setattr(
        "custom_components.device_companion.config_flow.today_local",
        lambda: date(2026, 6, 28),
    )
    flow = DeviceCompanionConfigFlow()
    flow._init_data = {CONF_CATEGORY: "虚拟服务", CONF_KIND: KIND_SERVICE}

    result = await flow.async_step_setup_service(
        {
            CONF_DEVICE_NAME: "Chat-GPT Plus",
            CONF_PURCHASE_DATE: "2026-06-28",
            CONF_TOTAL_PRICE: 280.0,
            CONF_PLAN_MONTHLY_PRICE: 140.0,
            CONF_SUB_PERIOD: "1个月",
            CONF_SERVICE_PERIOD_MONTHS: 2,
            CONF_EXPIRATION_DATE: "2026-09-29",
        }
    )

    assert result["type"] == "create_entry"
    payment = result["options"][CONF_SERVICE_PAYMENTS][0]
    assert payment["amount"] == 280.0
    assert payment["months_covered"] == 2
    assert payment["period_end"] == "2026-08-28"
    assert result["options"][CONF_EXPIRATION_DATE] == "2026-09-29"


@pytest.mark.asyncio
async def test_service_config_defaults_coverage_to_standard_period(monkeypatch):
    monkeypatch.setattr(
        "custom_components.device_companion.config_flow.today_local",
        lambda: date(2026, 6, 28),
    )
    flow = DeviceCompanionConfigFlow()
    flow._init_data = {CONF_CATEGORY: "虚拟服务", CONF_KIND: KIND_SERVICE}

    result = await flow.async_step_setup_service(
        {
            CONF_DEVICE_NAME: "年度服务",
            CONF_PURCHASE_DATE: "2026-06-28",
            CONF_TOTAL_PRICE: 1680.0,
            CONF_PLAN_MONTHLY_PRICE: 140.0,
            CONF_SUB_PERIOD: "1年",
        }
    )

    options = result["options"]
    assert options[CONF_SERVICE_PERIOD_MONTHS] == 12
    assert options[CONF_EXPIRATION_DATE] == "2027-06-28"
    assert options[CONF_SERVICE_PAYMENTS][0]["period_end"] == "2027-06-28"


def _hass_for_entry(entry):
    return SimpleNamespace(
        data={DOMAIN: {"entry_locks": {}}},
        config_entries=FakeConfigEntries(entry),
    )


def _async_return(value):
    async def resolver(_hass, _entity_id):
        return value

    return resolver


@pytest.mark.asyncio
async def test_v1_service_entry_migrates_without_losing_price():
    entry = SimpleNamespace(
        entry_id="legacy-service",
        version=1,
        data={"category": "虚拟服务", "total_price": 88.0},
        options={"sub_period": "1个月"},
    )

    assert await async_migrate_entry(_hass_for_entry(entry), entry)

    assert entry.version == 2
    assert entry.data[CONF_KIND] == KIND_SERVICE
    assert entry.options[CONF_CURRENT_PERIOD_COST] == 88.0
    assert entry.options["schema_version"] == 2


@pytest.mark.asyncio
async def test_renew_service_records_current_period_cost(monkeypatch):
    entry = SimpleNamespace(
        entry_id="service-entry",
        data={CONF_KIND: KIND_SERVICE, "total_price": 99.0},
        options={
            CONF_SUB_PERIOD: "1个月",
            CONF_EXPIRATION_DATE: "2026-08-30",
            "accumulated_cost": 99.0,
            "status": "active",
        },
    )
    hass = _hass_for_entry(entry)
    monkeypatch.setattr(
        "custom_components.device_companion._resolve_target_entry",
        _async_return(entry),
    )

    await _handle_renew_service(
        hass,
        SimpleNamespace(
            data={ATTR_ENTITY_ID: "sensor.service", "cost": 25.0, "months": 1}
        ),
    )

    assert entry.options[CONF_CURRENT_PERIOD_COST] == 25.0
    assert entry.options["accumulated_cost"] == 124.0


@pytest.mark.asyncio
async def test_renew_service_uses_current_period_cost_when_cost_is_omitted(monkeypatch):
    entry = SimpleNamespace(
        entry_id="service-default-cost",
        data={CONF_KIND: KIND_SERVICE, "total_price": 99.0},
        options={
            CONF_SUB_PERIOD: "1个月",
            CONF_EXPIRATION_DATE: "2026-08-30",
            CONF_CURRENT_PERIOD_COST: 25.0,
            "accumulated_cost": 124.0,
            "status": "active",
        },
    )
    hass = _hass_for_entry(entry)
    monkeypatch.setattr(
        "custom_components.device_companion._resolve_target_entry",
        _async_return(entry),
    )

    await _handle_renew_service(
        hass,
        SimpleNamespace(data={ATTR_ENTITY_ID: "sensor.service", "months": 1}),
    )

    assert entry.options[CONF_CURRENT_PERIOD_COST] == 25.0
    assert entry.options["accumulated_cost"] == 149.0


@pytest.mark.asyncio
async def test_service_charge_records_paid_extra_quota_without_extending_service(
    monkeypatch,
):
    monkeypatch.setattr(
        "custom_components.device_companion.today_local",
        lambda: date(2026, 9, 12),
    )
    entry = SimpleNamespace(
        entry_id="service-charge",
        data={CONF_KIND: KIND_SERVICE, CONF_TOTAL_PRICE: 99.0},
        options={
            CONF_SUB_PERIOD: "1个月",
            CONF_EXPIRATION_DATE: "2099-01-01",
            "service_period_start": "2026-09-01",
            "current_period_cost": 25.0,
            "accumulated_cost": 124.0,
        },
    )
    hass = _hass_for_entry(entry)
    monkeypatch.setattr(
        "custom_components.device_companion._resolve_target_entry",
        _async_return(entry),
    )

    await _handle_service_charge(
        hass,
        SimpleNamespace(
            data={
                ATTR_ENTITY_ID: "sensor.service",
                "charge_type": "extra_quota",
                "cost": 10.0,
                "description": "本月额外额度",
            }
        ),
    )

    assert entry.options["accumulated_cost"] == 134.0
    assert entry.options[CONF_EXPIRATION_DATE] == "2099-01-01"
    charge = entry.options[CONF_SERVICE_CHARGES][0]
    assert charge["charge_type"] == "extra_quota"
    assert charge["cost"] == 10.0
    assert charge["description"] == "本月额外额度"
    assert charge["period_start"] == "2026-09-01"
    assert charge["period_end"] == "2026-09-30"


@pytest.mark.asyncio
async def test_renew_service_uses_monthly_price_for_multiple_prepaid_months(
    monkeypatch,
):
    entry = SimpleNamespace(
        entry_id="service-prepaid-two-months",
        data={CONF_KIND: KIND_SERVICE, CONF_TOTAL_PRICE: 140.0},
        options={
            CONF_SUB_PERIOD: "1个月",
            CONF_EXPIRATION_DATE: "2026-08-30",
            CONF_CURRENT_PERIOD_COST: 140.0,
            CONF_PLAN_MONTHLY_PRICE: 140.0,
            CONF_SERVICE_PERIOD_MONTHS: 1,
            "accumulated_cost": 140.0,
        },
    )
    hass = _hass_for_entry(entry)
    monkeypatch.setattr(
        "custom_components.device_companion._resolve_target_entry",
        _async_return(entry),
    )

    await _handle_renew_service(
        hass,
        SimpleNamespace(
            data={ATTR_ENTITY_ID: "sensor.service", "months": 2}
        ),
    )

    assert entry.options["accumulated_cost"] == 420.0
    assert entry.options[CONF_CURRENT_PERIOD_COST] == 280.0
    assert entry.options[CONF_SERVICE_PERIOD_MONTHS] == 2
    assert entry.options[CONF_PLAN_MONTHLY_PRICE] == 140.0
    assert entry.options[CONF_SERVICE_PAYMENTS][-1]["amount"] == 280.0
    assert entry.options[CONF_SERVICE_PAYMENTS][-1]["months_covered"] == 2


@pytest.mark.asyncio
async def test_service_upgrade_can_update_future_monthly_price(monkeypatch):
    entry = SimpleNamespace(
        entry_id="service-upgrade",
        data={CONF_KIND: KIND_SERVICE, CONF_TOTAL_PRICE: 140.0},
        options={
            CONF_SUB_PERIOD: "1个月",
            CONF_EXPIRATION_DATE: "2099-01-01",
            CONF_PLAN_MONTHLY_PRICE: 140.0,
            CONF_SERVICE_PERIOD_MONTHS: 1,
            "service_period_start": "2026-09-01",
            "accumulated_cost": 140.0,
        },
    )
    hass = _hass_for_entry(entry)
    monkeypatch.setattr(
        "custom_components.device_companion._resolve_target_entry",
        _async_return(entry),
    )

    await _handle_service_charge(
        hass,
        SimpleNamespace(
            data={
                ATTR_ENTITY_ID: "sensor.service",
                "charge_type": "upgrade",
                "cost": 50.0,
                "new_monthly_price": 200.0,
            }
        ),
    )

    assert entry.options["accumulated_cost"] == 190.0
    assert entry.options[CONF_PLAN_MONTHLY_PRICE] == 200.0
    assert entry.options[CONF_EXPIRATION_DATE] == "2099-01-01"
    assert entry.options[CONF_SERVICE_CHARGES][-1]["new_monthly_price"] == 200.0


def test_service_charge_schema_requires_non_negative_paid_amount():
    with pytest.raises(vol.Invalid):
        SERVICE_CHARGE_SCHEMA(
            {
                ATTR_ENTITY_ID: "sensor.service",
                "charge_type": "extra_quota",
                "cost": -1,
            }
        )


def test_service_charge_schema_allows_new_monthly_price_for_upgrade():
    data = SERVICE_CHARGE_SCHEMA(
        {
            ATTR_ENTITY_ID: "sensor.service",
            "charge_type": "upgrade",
            "cost": 50,
            "new_monthly_price": 200,
        }
    )
    assert data["new_monthly_price"] == 200.0


@pytest.mark.asyncio
async def test_service_charge_rejects_new_monthly_price_for_extra_quota(monkeypatch):
    entry = SimpleNamespace(
        entry_id="service-charge-invalid-price",
        data={CONF_KIND: KIND_SERVICE, CONF_TOTAL_PRICE: 99.0},
        options={CONF_EXPIRATION_DATE: "2099-01-01"},
    )
    hass = _hass_for_entry(entry)
    monkeypatch.setattr(
        "custom_components.device_companion._resolve_target_entry",
        _async_return(entry),
    )

    with pytest.raises(ServiceValidationError, match="只有升级订阅"):
        await _handle_service_charge(
            hass,
            SimpleNamespace(
                data={
                    ATTR_ENTITY_ID: "sensor.service",
                    "charge_type": "extra_quota",
                    "cost": 10.0,
                    "new_monthly_price": 200.0,
                }
            ),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("expiration", "status", "message"),
    [
        ("2026-09-01", "active", "服务已到期"),
        ("2099-01-01", "canceled", "服务已取消"),
    ],
)
async def test_service_charge_requires_a_live_service(
    monkeypatch, expiration, status, message
):
    monkeypatch.setattr(
        "custom_components.device_companion.today_local",
        lambda: date(2026, 9, 12),
    )
    entry = SimpleNamespace(
        entry_id="service-charge-not-live",
        data={CONF_KIND: KIND_SERVICE, CONF_TOTAL_PRICE: 99.0},
        options={CONF_EXPIRATION_DATE: expiration, "status": status},
    )
    hass = _hass_for_entry(entry)
    monkeypatch.setattr(
        "custom_components.device_companion._resolve_target_entry",
        _async_return(entry),
    )

    with pytest.raises(ServiceValidationError, match=message):
        await _handle_service_charge(
            hass,
            SimpleNamespace(
                data={
                    ATTR_ENTITY_ID: "sensor.service",
                    "charge_type": "extra_quota",
                    "cost": 10.0,
                }
            ),
        )


@pytest.mark.asyncio
async def test_renew_service_rejects_expired_explicit_date(monkeypatch):
    entry = SimpleNamespace(
        entry_id="service-expired-date",
        data={CONF_KIND: KIND_SERVICE, CONF_TOTAL_PRICE: 99.0},
        options={
            CONF_SUB_PERIOD: "1个月",
            CONF_EXPIRATION_DATE: "2099-01-01",
            CONF_CURRENT_PERIOD_COST: 25.0,
            "accumulated_cost": 124.0,
        },
    )
    hass = _hass_for_entry(entry)
    monkeypatch.setattr(
        "custom_components.device_companion._resolve_target_entry",
        _async_return(entry),
    )

    with pytest.raises(ServiceValidationError, match="晚于今天"):
        await _handle_renew_service(
            hass,
            SimpleNamespace(
                data={
                    ATTR_ENTITY_ID: "sensor.service",
                    CONF_EXPIRATION_DATE: str(today_local()),
                }
            ),
        )

    assert entry.options["accumulated_cost"] == 124.0


def test_service_schemas_reject_negative_costs():
    with pytest.raises(vol.Invalid):
        RENEW_SCHEMA({ATTR_ENTITY_ID: "sensor.service", "cost": -1})
    with pytest.raises(vol.Invalid):
        REPLACE_SCHEMA(
            {ATTR_ENTITY_ID: "sensor.asset", "cons_id": "filter", "cost": -1}
        )


@pytest.mark.parametrize(
    ("old_value", "new_value", "expected"),
    [
        ("on", "off", True),
        ("10", "95", True),
        ("unknown", "95", False),
        ("unavailable", "95", False),
        ("95", "10", False),
    ],
)
def test_replacement_reset_transition_boundaries(old_value, new_value, expected):
    assert DeviceCompanionSensor._is_replacement_reset(
        old_value, new_value
    ) is expected


@pytest.mark.asyncio
async def test_legacy_quick_action_still_routes_renewal(monkeypatch):
    entry = SimpleNamespace(
        entry_id="legacy-action",
        data={CONF_KIND: KIND_SERVICE, "total_price": 40.0},
        options={CONF_SUB_PERIOD: "1个月", CONF_EXPIRATION_DATE: "2026-08-30"},
    )
    hass = _hass_for_entry(entry)
    monkeypatch.setattr(
        "custom_components.device_companion._resolve_target_entry",
        _async_return(entry),
    )

    async def async_call(_domain, service, data, blocking=False):
        assert service == "renew_service"
        await _handle_renew_service(hass, SimpleNamespace(data=data))

    hass.services = SimpleNamespace(async_call=async_call)
    await _handle_legacy_quick_action(
        hass,
        SimpleNamespace(
            data={
                ATTR_ENTITY_ID: "sensor.service",
                "action": "renew_service",
                "cost": 15.0,
            }
        ),
    )

    assert entry.options[CONF_CURRENT_PERIOD_COST] == 15.0


@pytest.mark.asyncio
async def test_replace_consumable_records_actual_cost(monkeypatch):
    entry = SimpleNamespace(
        entry_id="asset-entry",
        data={CONF_KIND: "asset"},
        options={
            CONF_CONSUMABLES_LIST: [
                {"id": "filter", "price": 10.0, "accumulated_cost": 10.0}
            ]
        },
    )
    hass = _hass_for_entry(entry)
    monkeypatch.setattr(
        "custom_components.device_companion._resolve_target_entry",
        _async_return(entry),
    )

    await _handle_replace_consumable(
        hass,
        SimpleNamespace(
            data={ATTR_ENTITY_ID: "sensor.asset", "cons_id": "filter", "cost": 12.5}
        ),
    )

    item = entry.options[CONF_CONSUMABLES_LIST][0]
    assert item["accumulated_cost"] == 22.5
    assert item["last_replace"] == str(today_local())


def test_current_monthly_cost_uses_latest_service_price():
    entry = SimpleNamespace(
        entry_id="cost-entry",
        data={
            CONF_KIND: KIND_SERVICE,
            "device_name": "订阅",
            "category": "虚拟服务",
            "purchase_date": "2026-01-01",
            "total_price": 100.0,
        },
        options={
            CONF_SUB_PERIOD: "1个月",
            CONF_EXPIRATION_DATE: "2099-01-01",
            "service_period_start": "2098-12-01",
            "service_period_days": 31,
            CONF_CURRENT_PERIOD_COST: 25.0,
            "status": "active",
        },
    )
    entity = DeviceCompanionSensor(entry)
    entity.hass = SimpleNamespace(states=SimpleNamespace(get=lambda _entity_id: None))

    _state, attributes = entity._compute()

    assert attributes["service_monthly_cost"] == 25.0
    assert attributes["current_monthly_cost"] == 25.0
    assert attributes["renewal_price"] == 25.0


def test_current_monthly_cost_includes_current_period_extra_charge(monkeypatch):
    monkeypatch.setattr(
        "custom_components.device_companion.sensor.today_local",
        lambda: date(2026, 9, 12),
    )
    entry = SimpleNamespace(
        entry_id="cost-extra-entry",
        data={
            CONF_KIND: KIND_SERVICE,
            "device_name": "订阅",
            "category": "虚拟服务",
            "purchase_date": "2026-01-01",
            CONF_TOTAL_PRICE: 100.0,
        },
        options={
            CONF_SUB_PERIOD: "1个月",
            CONF_EXPIRATION_DATE: "2099-01-01",
            "service_period_start": "2098-12-01",
            "service_period_days": 31,
            CONF_CURRENT_PERIOD_COST: 25.0,
            CONF_PLAN_MONTHLY_PRICE: 25.0,
            CONF_SERVICE_PERIOD_MONTHS: 1,
            CONF_SERVICE_CHARGES: [
                {
                    "id": "charge-1",
                    "charge_type": "extra_quota",
                    "cost": 10.0,
                    "period_start": "2026-01-01",
                    "period_end": "2099-01-01",
                },
                {
                    "id": "charge-old",
                    "charge_type": "upgrade",
                    "cost": 99.0,
                    "period_start": "2026-01-01",
                    "period_end": "2026-08-31",
                },
            ],
            "status": "active",
        },
    )
    entity = DeviceCompanionSensor(entry)
    entity.hass = SimpleNamespace(states=SimpleNamespace(get=lambda _entity_id: None))

    _state, attributes = entity._compute()

    assert attributes["current_period_cost"] == 25.0
    assert attributes["current_period_extra_cost"] == 10.0
    assert attributes["current_month_extra_cost"] == 10.0
    assert attributes["current_period_total_cost"] == 35.0
    assert attributes["service_monthly_cost"] == 35.0
    assert attributes["current_monthly_cost"] == 35.0


def test_two_month_prepaid_cost_uses_actual_coverage_months(monkeypatch):
    monkeypatch.setattr(
        "custom_components.device_companion.sensor.today_local",
        lambda: date(2026, 9, 12),
    )
    entry = SimpleNamespace(
        entry_id="cost-two-month-entry",
        data={
            CONF_KIND: KIND_SERVICE,
            "device_name": "订阅",
            "category": "虚拟服务",
            "purchase_date": "2026-06-28",
            CONF_TOTAL_PRICE: 140.0,
        },
        options={
            CONF_SUB_PERIOD: "1个月",
            CONF_EXPIRATION_DATE: "2026-10-28",
            "service_period_start": "2026-08-28",
            "service_period_days": 61,
            CONF_SERVICE_PERIOD_MONTHS: 2,
            CONF_PLAN_MONTHLY_PRICE: 140.0,
            CONF_CURRENT_PERIOD_COST: 280.0,
            CONF_SERVICE_PAYMENTS: [
                {
                    "id": "payment-1",
                    "payment_type": "initial",
                    "amount": 280.0,
                    "paid_at": "2026-08-28",
                    "period_start": "2026-08-28",
                    "period_end": "2026-10-28",
                    "months_covered": 2,
                }
            ],
            "status": "active",
        },
    )
    entity = DeviceCompanionSensor(entry)
    entity.hass = SimpleNamespace(states=SimpleNamespace(get=lambda _entity_id: None))

    _state, attributes = entity._compute()

    assert attributes["plan_monthly_price"] == 140.0
    assert attributes["service_period_months"] == 2
    assert attributes["current_period_base_monthly_cost"] == 140.0
    assert attributes["service_monthly_cost"] == 140.0
    assert attributes["payment_coverage_status"] == "ok"


def test_prepaid_extra_quota_is_counted_in_the_current_month_only(monkeypatch):
    monkeypatch.setattr(
        "custom_components.device_companion.sensor.today_local",
        lambda: date(2026, 9, 12),
    )
    entry = SimpleNamespace(
        entry_id="cost-two-month-extra-entry",
        data={
            CONF_KIND: KIND_SERVICE,
            "device_name": "订阅",
            "category": "虚拟服务",
            "purchase_date": "2026-08-28",
            CONF_TOTAL_PRICE: 280.0,
        },
        options={
            CONF_SUB_PERIOD: "1个月",
            CONF_EXPIRATION_DATE: "2026-10-28",
            "service_period_start": "2026-08-28",
            "service_period_days": 61,
            CONF_SERVICE_PERIOD_MONTHS: 2,
            CONF_PLAN_MONTHLY_PRICE: 140.0,
            CONF_CURRENT_PERIOD_COST: 280.0,
            CONF_SERVICE_CHARGES: [
                {
                    "id": "charge-current",
                    "charge_type": "extra_quota",
                    "cost": 10.0,
                    "period_start": "2026-08-28",
                    "period_end": "2026-10-28",
                }
            ],
            "status": "active",
        },
    )
    entity = DeviceCompanionSensor(entry)
    entity.hass = SimpleNamespace(states=SimpleNamespace(get=lambda _entity_id: None))

    _state, attributes = entity._compute()

    assert attributes["current_period_base_monthly_cost"] == 140.0
    assert attributes["current_period_total_cost"] == 290.0
    assert attributes["current_month_extra_cost"] == 10.0
    assert attributes["service_monthly_cost"] == 150.0
    assert attributes["current_monthly_cost"] == 150.0


def test_previous_month_extra_quota_is_not_repeated_in_current_month(monkeypatch):
    monkeypatch.setattr(
        "custom_components.device_companion.sensor.today_local",
        lambda: date(2026, 10, 1),
    )
    entry = SimpleNamespace(
        entry_id="cost-previous-month-extra-entry",
        data={
            CONF_KIND: KIND_SERVICE,
            "device_name": "订阅",
            "category": "虚拟服务",
            "purchase_date": "2026-08-28",
            CONF_TOTAL_PRICE: 280.0,
        },
        options={
            CONF_SUB_PERIOD: "1个月",
            CONF_EXPIRATION_DATE: "2026-10-28",
            "service_period_start": "2026-08-28",
            "service_period_days": 61,
            CONF_SERVICE_PERIOD_MONTHS: 2,
            CONF_PLAN_MONTHLY_PRICE: 140.0,
            CONF_CURRENT_PERIOD_COST: 280.0,
            CONF_SERVICE_CHARGES: [
                {
                    "id": "charge-september",
                    "charge_type": "extra_quota",
                    "cost": 10.0,
                    "period_start": "2026-09-01",
                    "period_end": "2026-09-30",
                }
            ],
            "status": "active",
        },
    )
    entity = DeviceCompanionSensor(entry)
    entity.hass = SimpleNamespace(states=SimpleNamespace(get=lambda _entity_id: None))

    _state, attributes = entity._compute()

    assert attributes["current_period_extra_cost"] == 10.0
    assert attributes["current_month_extra_cost"] == 0.0
    assert attributes["service_monthly_cost"] == 140.0


def test_payment_coverage_mismatch_is_visible(monkeypatch):
    monkeypatch.setattr(
        "custom_components.device_companion.sensor.today_local",
        lambda: date(2026, 9, 12),
    )
    entry = SimpleNamespace(
        entry_id="payment-gap-entry",
        data={
            CONF_KIND: KIND_SERVICE,
            "device_name": "订阅",
            "purchase_date": "2026-06-28",
            CONF_TOTAL_PRICE: 140.0,
        },
        options={
            CONF_SUB_PERIOD: "1个月",
            CONF_EXPIRATION_DATE: "2026-09-29",
            CONF_SERVICE_PERIOD_MONTHS: 1,
            CONF_CURRENT_PERIOD_COST: 140.0,
            CONF_PLAN_MONTHLY_PRICE: 140.0,
            CONF_SERVICE_PAYMENTS: [
                {
                    "id": "payment-1",
                    "payment_type": "initial",
                    "amount": 280.0,
                    "period_start": "2026-06-28",
                    "period_end": "2026-08-28",
                    "months_covered": 2,
                }
            ],
            "status": "active",
        },
    )
    entity = DeviceCompanionSensor(entry)
    entity.hass = SimpleNamespace(states=SimpleNamespace(get=lambda _entity_id: None))

    _state, attributes = entity._compute()

    assert attributes["payment_coverage_end"] == "2026-08-28"
    assert attributes["payment_coverage_status"] == "mismatch"
    assert any(badge["label"] == "付款覆盖需核对" for badge in attributes["badges"])


@pytest.mark.asyncio
async def test_replace_consumable_rejects_unknown_id(monkeypatch):
    entry = SimpleNamespace(
        entry_id="asset-entry",
        data={CONF_KIND: "asset"},
        options={CONF_CONSUMABLES_LIST: []},
    )
    hass = _hass_for_entry(entry)
    monkeypatch.setattr(
        "custom_components.device_companion._resolve_target_entry",
        _async_return(entry),
    )

    with pytest.raises(ServiceValidationError):
        await _handle_replace_consumable(
            hass,
            SimpleNamespace(
                data={ATTR_ENTITY_ID: "sensor.asset", "cons_id": "missing"}
            ),
        )


def _real_service_entry(*, device_name: str = "真实订阅") -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="真实服务测试",
        version=2,
        data={
            CONF_KIND: KIND_SERVICE,
            CONF_CATEGORY: "虚拟服务",
            "device_name": device_name,
            CONF_PURCHASE_DATE: "2026-01-01",
            CONF_TOTAL_PRICE: 99.0,
        },
        options={
            CONF_SUB_PERIOD: "1个月",
            CONF_EXPIRATION_DATE: "2099-01-01",
            CONF_CURRENT_PERIOD_COST: 25.0,
            "accumulated_cost": 124.0,
            "status": "active",
        },
    )


@pytest.mark.asyncio
async def test_real_entry_setup_service_and_unload(hass, enable_custom_integrations):
    entry = _real_service_entry()
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        "sensor", DOMAIN, f"companion_{entry.entry_id}"
    )
    assert entity_id is not None
    assert hass.states.get(entity_id) is not None

    await hass.services.async_call(
        DOMAIN,
        "renew_service",
        {ATTR_ENTITY_ID: entity_id, "months": 1},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert entry.options[CONF_CURRENT_PERIOD_COST] == 25.0
    assert entry.options["accumulated_cost"] == 149.0

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id) is not None

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
    assert hass.states.get(entity_id).state == STATE_UNAVAILABLE


@pytest.mark.asyncio
async def test_real_entry_setup_tolerates_invalid_child_lists(
    hass, enable_custom_integrations
):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="异常列表测试",
        version=2,
        data={
            CONF_KIND: KIND_SERVICE,
            CONF_CATEGORY: "虚拟服务",
            "device_name": "列表异常服务",
            CONF_PURCHASE_DATE: "2026-01-01",
            CONF_TOTAL_PRICE: 99.0,
        },
        options={
            CONF_CONSUMABLES_LIST: None,
            CONF_ACCESSORIES_LIST: None,
            CONF_SUB_PERIOD: "1个月",
            CONF_EXPIRATION_DATE: "2099-01-01",
            "status": "active",
        },
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        "sensor", DOMAIN, f"companion_{entry.entry_id}"
    )
    assert entity_id is not None
    assert hass.states.get(entity_id).state not in {"unknown", STATE_UNAVAILABLE}


@pytest.mark.asyncio
async def test_service_invalid_idle_status_is_treated_as_active(
    hass, enable_custom_integrations
):
    entry = _real_service_entry()
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, "status": "idle"}
    )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        "sensor", DOMAIN, f"companion_{entry.entry_id}"
    )
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.attributes["status"] == "active"
    assert state.attributes["current_monthly_cost"] == 25.0
    assert not any(
        badge["label"] == "闲置持有" for badge in state.attributes["badges"]
    )


@pytest.mark.asyncio
async def test_multiple_entries_keep_shared_services_and_isolated_entities(
    hass, enable_custom_integrations
):
    first = _real_service_entry(device_name="第一条订阅")
    second = _real_service_entry(device_name="第二条订阅")
    first.add_to_hass(hass)
    second.add_to_hass(hass)

    assert await hass.config_entries.async_setup(first.entry_id)
    if second.state is ConfigEntryState.NOT_LOADED:
        assert await hass.config_entries.async_setup(second.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    first_entity = registry.async_get_entity_id(
        "sensor", DOMAIN, f"companion_{first.entry_id}"
    )
    second_entity = registry.async_get_entity_id(
        "sensor", DOMAIN, f"companion_{second.entry_id}"
    )
    assert first_entity is not None
    assert second_entity is not None
    assert first_entity != second_entity
    assert hass.states.get(first_entity) is not None
    assert hass.states.get(second_entity) is not None
    assert hass.services.has_service(DOMAIN, "renew_service")
    upload_routes = [
        resource
        for resource in hass.http.app.router.resources()
        if resource.canonical == "/api/device_companion/upload"
    ]
    assert len(upload_routes) == 1

    assert await hass.config_entries.async_unload(first.entry_id)
    await hass.async_block_till_done()
    assert first.state is ConfigEntryState.NOT_LOADED
    assert second.state is ConfigEntryState.LOADED
    assert hass.services.has_service(DOMAIN, "renew_service")

    await hass.services.async_call(
        DOMAIN,
        "renew_service",
        {ATTR_ENTITY_ID: second_entity, "months": 1},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert second.options["accumulated_cost"] == 149.0

    assert await hass.config_entries.async_unload(second.entry_id)
    await hass.async_block_till_done()
    assert second.state is ConfigEntryState.NOT_LOADED
    assert hass.services.has_service(DOMAIN, "renew_service")
    assert len(upload_routes) == 1


async def _setup_upload_endpoint(hass, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def _upload_form(payload: bytes) -> aiohttp.FormData:
    form = aiohttp.FormData()
    form.add_field(
        "file",
        payload,
        filename="upload.bin",
        content_type="application/octet-stream",
    )
    return form


def test_upload_requires_authentication():
    assert DeviceCompanionUploadView.requires_auth is True


@pytest.mark.asyncio
@pytest.mark.enable_socket
async def test_upload_accepts_signed_png_and_writes_random_file(
    hass, hass_client, enable_custom_integrations, monkeypatch
):
    await _setup_upload_endpoint(hass, _real_service_entry())
    monkeypatch.setattr("aiohttp.connector.DefaultResolver", aiohttp.ThreadedResolver)
    client = await hass_client()
    payload = b"\x89PNG\r\n\x1a\npayload"

    response = await client.post(
        "/api/device_companion/upload", data=_upload_form(payload)
    )

    assert response.status == 200
    result = await response.json()
    assert result["success"] is True
    assert result["url"].startswith("/local/device_companion/dc_img_")
    assert result["url"].endswith(".png")
    filename = result["url"].rsplit("/", maxsplit=1)[-1]
    uploaded = Path(hass.config.path("www", DOMAIN)) / filename
    assert uploaded.read_bytes() == payload


@pytest.mark.asyncio
@pytest.mark.enable_socket
async def test_upload_rejects_empty_unsupported_and_oversized_files(
    hass, hass_client, enable_custom_integrations, monkeypatch
):
    await _setup_upload_endpoint(hass, _real_service_entry())
    monkeypatch.setattr("aiohttp.connector.DefaultResolver", aiohttp.ThreadedResolver)
    client = await hass_client()

    empty_response = await client.post(
        "/api/device_companion/upload", data=_upload_form(b"")
    )
    unsupported_response = await client.post(
        "/api/device_companion/upload", data=_upload_form(b"not-an-image")
    )
    oversized_response = await client.post(
        "/api/device_companion/upload",
        data=_upload_form(b"\x89PNG\r\n\x1a\n" + b"x" * MAX_UPLOAD_BYTES),
    )

    assert empty_response.status == 400
    assert (await empty_response.json())["error"] == "empty_file"
    assert unsupported_response.status == 415
    assert (await unsupported_response.json())["error"] == "unsupported_image"
    assert oversized_response.status == 413
    assert (await oversized_response.json())["error"] == "file_too_large"


@pytest.mark.asyncio
@pytest.mark.enable_socket
async def test_upload_reports_disk_write_failure(
    hass, hass_client, enable_custom_integrations, monkeypatch
):
    await _setup_upload_endpoint(hass, _real_service_entry())
    monkeypatch.setattr("aiohttp.connector.DefaultResolver", aiohttp.ThreadedResolver)

    def fail_write(_path, _payload):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "write_bytes", fail_write)
    client = await hass_client()

    response = await client.post(
        "/api/device_companion/upload",
        data=_upload_form(b"\x89PNG\r\n\x1a\npayload"),
    )

    assert response.status == 500
    assert (await response.json())["error"] == "upload_failed"


def _real_smart_consumable_entry(*, auto_record: bool) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="智能耗材测试",
        version=2,
        data={
            CONF_KIND: "asset",
            CONF_CATEGORY: "家用电器",
            "device_name": "智能设备",
            CONF_PURCHASE_DATE: "2026-01-01",
            CONF_TOTAL_PRICE: 100.0,
        },
        options={
            CONF_CONSUMABLES_LIST: [
                {
                    "id": "filter",
                    "name": "滤芯",
                    "price": 10.0,
                    "cycle": 30,
                    CONF_TRACKING_MODE: TRACKING_MODE_SMART,
                    CONF_LINKED_ENTITY: "sensor.filter_remaining",
                    CONF_AUTO_RECORD_REPLACEMENT: auto_record,
                    "last_replace": "2026-08-01",
                    "last_detected_reset": "",
                    "accumulated_cost": 10.0,
                }
            ]
        },
    )


async def _setup_smart_consumable(hass, entry: MockConfigEntry) -> str:
    hass.states.async_set("sensor.filter_remaining", "10")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        "sensor", DOMAIN, f"companion_{entry.entry_id}"
    )
    assert entity_id is not None
    return entity_id


@pytest.mark.asyncio
async def test_smart_consumable_manual_detection_is_persisted_and_deduplicated(
    hass, enable_custom_integrations
):
    entry = _real_smart_consumable_entry(auto_record=False)
    entity_id = await _setup_smart_consumable(hass, entry)
    detections = []
    hass.bus.async_listen(
        "device_companion_consumable_replacement_detected",
        lambda event: detections.append(event),
    )

    hass.states.async_set("sensor.filter_remaining", "95")
    await hass.async_block_till_done()

    assert entry.options[CONF_CONSUMABLES_LIST][0]["last_detected_reset"] == str(
        today_local()
    )
    assert len(detections) == 1

    hass.states.async_set("sensor.filter_remaining", "10")
    hass.states.async_set("sensor.filter_remaining", "95")
    await hass.async_block_till_done()

    assert len(detections) == 1
    assert entry.options[CONF_CONSUMABLES_LIST][0]["accumulated_cost"] == 10.0


@pytest.mark.asyncio
async def test_smart_consumable_auto_detection_records_once(
    hass, enable_custom_integrations
):
    entry = _real_smart_consumable_entry(auto_record=True)
    await _setup_smart_consumable(hass, entry)

    hass.states.async_set("sensor.filter_remaining", "95")
    await hass.async_block_till_done()

    assert entry.options[CONF_CONSUMABLES_LIST][0]["last_detected_reset"] == str(
        today_local()
    )
    assert entry.options[CONF_CONSUMABLES_LIST][0]["accumulated_cost"] == 20.0

    hass.states.async_set("sensor.filter_remaining", "10")
    hass.states.async_set("sensor.filter_remaining", "95")
    await hass.async_block_till_done()

    assert entry.options[CONF_CONSUMABLES_LIST][0]["accumulated_cost"] == 20.0
