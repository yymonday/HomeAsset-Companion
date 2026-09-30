"""Billing boundaries and persistent reminders for v1.3."""

import asyncio
from datetime import date, datetime, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
import voluptuous as vol
from homeassistant.exceptions import ServiceValidationError

import custom_components.device_companion as integration
from custom_components.device_companion.calendar import DeviceCompanionCalendar
from custom_components.device_companion.helpers import safe_float, safe_int
from custom_components.device_companion.reminders import async_check_expiry
from custom_components.device_companion.sensor import DeviceCompanionSensor


@pytest.fixture
def service(monkeypatch):
    entry = SimpleNamespace(entry_id="v13", data={"kind": "service", "device_name": "测试订阅", "purchase_date": "2026-08-15", "total_price": 140.0}, options={"status": "active", "sub_period": "1个月", "expiration_date": "2026-10-15", "current_period_cost": 140.0, "service_period_months": 1, "plan_monthly_price": 200.0, "service_period_start": "2026-09-15"})
    class Entries:
        def async_get_entry(self, _id):
            return entry

        def async_update_entry(self, target, **changes):
            for key, value in changes.items():
                setattr(target, key, value)

    hass = SimpleNamespace(data={"device_companion": {"entry_locks": {}}}, config_entries=Entries(), states={})

    async def resolve(_hass, _id):
        return entry

    monkeypatch.setattr(integration, "_resolve_target_entry", resolve)
    monkeypatch.setattr(integration, "today_local", lambda: date(2026, 9, 30))
    monkeypatch.setattr("custom_components.device_companion.sensor.today_local", lambda: date(2026, 9, 30))
    return entry, hass


def costs(entry, hass):
    sensor = DeviceCompanionSensor(entry)
    sensor.hass = hass
    return sensor._compute()[1]


@pytest.mark.asyncio
async def test_multiple_advance_payments_activate_on_their_start(service, monkeypatch):
    entry, hass = service
    for cost in (200, 300):
        await integration._handle_renew_service(hass, SimpleNamespace(data={"entity_id": "sensor.test", "cost": cost, "months": 1}))
    assert costs(entry, hass)["current_monthly_cost"] == 140
    assert costs(entry, hass)["current_period_start"] == "2026-09-15"
    for day, expected in ((date(2026, 10, 15), 200), (date(2026, 11, 15), 300)):
        monkeypatch.setattr("custom_components.device_companion.sensor.today_local", lambda: day)
        assert costs(entry, hass)["current_monthly_cost"] == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("action,extra", [("renew_service", {"months": 1}), ("record_service_charge", {"charge_type": "extra_quota"})])
async def test_parallel_payment_retry_is_persistently_idempotent(service, action, extra):
    entry, hass = service
    handler = getattr(integration, "_handle_renew_service" if action == "renew_service" else "_handle_service_charge")
    call = SimpleNamespace(data={"entity_id": "sensor.test", "cost": 25.0, "request_id": "receipt-1", **extra})
    await asyncio.gather(handler(hass, call), handler(hass, call))
    assert entry.options["accumulated_cost"] == 25
    assert len(entry.options.get("service_payments", entry.options.get("service_charges"))) == 1
    # A fresh runtime lock simulates restart, with receipts preserved in options.
    hass.data["device_companion"]["entry_locks"] = {}
    await handler(hass, call)
    assert entry.options["accumulated_cost"] == 25
    with pytest.raises(ServiceValidationError, match="另一笔"):
        await handler(hass, SimpleNamespace(data={**call.data, "cost": 30}))
    assert entry.options["accumulated_cost"] == 25


@pytest.mark.asyncio
async def test_backdated_charge_belongs_to_payment_month(service):
    entry, hass = service
    await integration._handle_service_charge(hass, SimpleNamespace(data={"entity_id": "sensor.test", "cost": 25, "charge_type": "extra_quota", "paid_at": date(2026, 8, 20)}))
    assert entry.options["service_charges"][0]["paid_at"] == "2026-08-20"
    assert entry.options["accumulated_cost"] == 25
    assert costs(entry, hass)["current_month_extra_cost"] == 0
    assert entry.options["expiration_date"] == "2026-10-15"


@pytest.mark.asyncio
async def test_future_payment_rejected_without_mutation(service):
    entry, hass = service
    before = dict(entry.options)
    with pytest.raises(ServiceValidationError, match="晚于今天"):
        await integration._handle_renew_service(hass, SimpleNamespace(data={"entity_id": "sensor.test", "paid_at": date(2026, 10, 1), "request_id": "future"}))
    assert entry.options == before


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_money_rejected_and_legacy_values_do_not_crash(value):
    with pytest.raises(vol.Invalid):
        integration.RENEW_SCHEMA({"entity_id": "sensor.test", "cost": value})
    assert safe_float(value, 5) == 5
    assert safe_int(value, 5) == 5


@pytest.mark.asyncio
async def test_calendar_utc_window_is_converted_to_ha_timezone(service, monkeypatch):
    entry, _ = service
    entry.options["expiration_date"] = "2026-10-01"
    calendar = DeviceCompanionCalendar(entry)
    with monkeypatch.context() as zone:
        zone.setattr("homeassistant.util.dt.DEFAULT_TIME_ZONE", ZoneInfo("Asia/Shanghai"))
        events = await calendar.async_get_events(None, datetime(2026, 9, 30, 16, tzinfo=timezone.utc), datetime(2026, 10, 1, 16, tzinfo=timezone.utc))
        assert [event.start for event in events] == [date(2026, 10, 1)]
        events = await calendar.async_get_events(None, datetime(2026, 9, 30, 15, tzinfo=timezone.utc), datetime(2026, 9, 30, 16, tzinfo=timezone.utc))
        assert events == []
        events = await calendar.async_get_events(None, datetime(2026, 9, 30, 16, tzinfo=timezone.utc), datetime(2026, 10, 1, 3, tzinfo=timezone.utc))
        assert [event.start for event in events] == [date(2026, 10, 1)]


@pytest.mark.asyncio
async def test_reminders_deduplicate_and_follow_new_expiration(service, monkeypatch):
    entry, hass = service
    notifications = []
    monkeypatch.setattr("custom_components.device_companion.reminders.persistent_notification.async_create", lambda *_args, **kwargs: notifications.append(kwargs))
    entry.options.update(expiry_reminders=True, expiration_date="2026-10-07")
    for day, count in ((date(2026, 9, 30), 1), (date(2026, 10, 1), 1), (date(2026, 10, 4), 2), (date(2026, 10, 7), 3), (date(2026, 10, 8), 3)):
        monkeypatch.setattr("custom_components.device_companion.reminders.today_local", lambda: day)
        await async_check_expiry(hass, entry)
        await async_check_expiry(hass, entry)
        assert len(notifications) == count
    entry.options["expiration_date"] = "2026-10-15"
    await async_check_expiry(hass, entry)
    assert len(notifications) == 4
    entry.options["status"] = "canceled"
    entry.options["expiration_date"] = "2026-10-11"
    await async_check_expiry(hass, entry)
    assert len(notifications) == 4


@pytest.mark.asyncio
async def test_reminders_disabled_by_default(service, monkeypatch):
    entry, hass = service
    entry.options["expiration_date"] = "2026-10-01"
    monkeypatch.setattr("custom_components.device_companion.reminders.persistent_notification.async_create", lambda *_args, **_kwargs: pytest.fail("unexpected notification"))
    await async_check_expiry(hass, entry)
    assert "expiry_reminder_sent" not in entry.options


@pytest.mark.asyncio
async def test_real_config_and_options_flow_preserves_identity(hass, enable_custom_integrations):
    flow = await hass.config_entries.flow.async_init("device_companion", context={"source": "user"})
    flow = await hass.config_entries.flow.async_configure(flow["flow_id"], {"category": "虚拟服务"})
    assert flow["step_id"] == "setup_service"
    result = await hass.config_entries.flow.async_configure(flow["flow_id"], {"device_name": "流程订阅", "purchase_date": "2026-09-12", "total_price": 280.0, "plan_monthly_price": 140.0, "sub_period": "1个月", "service_period_months": 2})
    assert result["type"] == "create_entry"
    entry = result["result"]
    await hass.async_block_till_done()
    from homeassistant.helpers import entity_registry as er
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id("sensor", "device_companion", f"companion_{entry.entry_id}")
    before_payments = list(entry.options["service_payments"])
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    flow = await hass.config_entries.options.async_configure(flow["flow_id"], {"next_step_id": "edit_basic"})
    assert flow["step_id"] == "edit_basic"
    result = await hass.config_entries.options.async_configure(flow["flow_id"], {"device_name": "流程订阅", "purchase_date": "2026-09-12", "total_price": 280.0, "plan_monthly_price": 140.0, "sub_period": "1个月", "service_period_months": 2, "expiration_date": "2026-11-12", "expiry_reminders": True})
    assert result["type"] == "abort"
    await hass.async_block_till_done()
    assert entry.options["expiry_reminders"] is True
    assert entry.options["service_payments"] == before_payments
    assert registry.async_get_entity_id("sensor", "device_companion", f"companion_{entry.entry_id}") == entity_id
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.parametrize("start,months,expected", [(date(2026, 1, 31), 1, date(2026, 2, 28)), (date(2028, 1, 31), 1, date(2028, 2, 29)), (date(2026, 12, 31), 2, date(2027, 2, 28))])
def test_renewal_month_end_boundaries(start, months, expected):
    from custom_components.device_companion.helpers import add_months_to_date
    assert add_months_to_date(start, months) == expected


@pytest.mark.asyncio
async def test_real_reminder_catchup_reload_and_unload(hass, enable_custom_integrations, monkeypatch):
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from custom_components.device_companion import reminders
    calls = []
    monkeypatch.setattr(reminders, "today_local", lambda: date(2026, 9, 30))
    monkeypatch.setattr(reminders.dt_util, "now", lambda: datetime(2026, 9, 30, 10, tzinfo=timezone.utc))
    monkeypatch.setattr(reminders.persistent_notification, "async_create", lambda *_args, **kwargs: calls.append(kwargs))
    entry = MockConfigEntry(domain="device_companion", version=2, data={"kind": "service", "device_name": "提醒验收", "purchase_date": "2026-09-01", "total_price": 140}, options={"status": "active", "expiration_date": "2026-10-07", "expiry_reminders": True, "sub_period": "1个月"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert len(calls) == 1
    assert entry.options["expiry_reminder_sent"]["thresholds"] == [7]
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert len(calls) == 1
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    lock = hass.data["device_companion"]["entry_locks"][entry.entry_id]
    assert not lock.locked()
    await integration.async_remove_entry(hass, entry)
    assert entry.entry_id not in hass.data["device_companion"]["entry_locks"]
