"""Regression tests for HomeAsset Companion v1.1.1."""

from types import SimpleNamespace

import pytest
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.exceptions import ServiceValidationError

from custom_components.device_companion import (
    _handle_legacy_quick_action,
    _handle_replace_consumable,
    _handle_renew_service,
    async_migrate_entry,
)
from custom_components.device_companion.const import (
    CONF_CONSUMABLES_LIST,
    CONF_CURRENT_PERIOD_COST,
    CONF_EXPIRATION_DATE,
    CONF_KIND,
    CONF_SUB_PERIOD,
    DOMAIN,
    KIND_SERVICE,
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
