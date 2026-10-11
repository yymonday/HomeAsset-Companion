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


@pytest.fixture
def recorded_service(service):
    entry, hass = service
    entry.options["service_payments"] = [{"id": "initial", "payment_type": "initial", "amount": 140.0, "paid_at": "2026-08-15", "period_start": "2026-09-15", "period_end": "2026-10-15", "months_covered": 1}]
    return entry, hass


def adjustment(operation="refund", cost=20.0, request_id="adjust-1", **extra):
    return SimpleNamespace(data={"entity_id": "sensor.test", "bill_id": "initial", "operation": operation, "cost": cost, "request_id": request_id, "description": "核对账单", "paid_at": "2026-09-30", **extra})


@pytest.mark.asyncio
async def test_correct_actual_payment_date_replaces_old_coverage(service, monkeypatch):
    from copy import deepcopy

    entry, hass = service
    entry.data.update(purchase_date="2026-06-28", total_price=280.0)
    entry.options.update(
        expiration_date="2026-10-30", service_period_start="2026-09-30",
        current_period_cost=670.0, accumulated_cost=670.0,
        service_payments=[
            {"id": "history", "payment_type": "initial", "amount": 280.0,
             "paid_at": "2026-06-28", "period_start": "2026-06-28",
             "period_end": "2026-07-28", "months_covered": 1},
            {"id": "current", "payment_type": "renewal", "amount": 670.0,
             "paid_at": "2026-09-30", "period_start": "2026-09-30",
             "period_end": "2026-10-30", "months_covered": 1},
        ],
        service_period_snapshots=[
            {"period_start": "2026-09-30", "period_end": "2026-10-30",
             "amount": 670.0, "months_covered": 1},
        ],
    )
    monkeypatch.setattr(integration, "today_local", lambda: date(2026, 10, 11))
    monkeypatch.setattr("custom_components.device_companion.sensor.today_local", lambda: date(2026, 10, 11))
    original = deepcopy(entry.options["service_payments"])

    await integration._handle_adjust_bill(hass, adjustment(
        "correction", 670.0, "date-fix", bill_id="current",
        paid_at="2026-10-11", corrected_paid_at="2026-10-09",
    ))

    assert entry.options["expiration_date"] == "2026-11-09"
    assert entry.options["service_period_start"] == "2026-10-09"
    assert entry.options["service_period_days"] == 31
    assert entry.options["service_payments"] == original  # Audit source stays intact.
    attrs = costs(entry, hass)
    assert attrs["service_payments"][-1]["paid_at"] == "2026-10-09"
    assert attrs["service_payments"][-1]["period_end"] == "2026-11-09"
    assert attrs["payment_coverage_end"] == "2026-11-09"
    assert attrs["current_period_start"] == "2026-10-09"
    assert attrs["current_monthly_cost"] == 670.0
    assert attrs["main_net_investment"] == 950.0
    assert attrs["service_adjustments"][-1]["amount"] == 0
    # The superseded September snapshot must not remain active before Oct 9.
    monkeypatch.setattr("custom_components.device_companion.sensor.today_local", lambda: date(2026, 10, 5))
    assert costs(entry, hass)["current_monthly_cost"] == 0


@pytest.mark.asyncio
async def test_date_revisions_replace_each_other_and_replay_after_restart(recorded_service):
    from copy import deepcopy

    entry, hass = recorded_service
    original = deepcopy(entry.options["service_payments"])
    first = adjustment("correction", 180, "date-1", corrected_paid_at="2026-09-09")
    await asyncio.gather(*(integration._handle_adjust_bill(hass, first) for _ in range(2)))
    assert len(entry.options["service_adjustments"]) == 1
    assert costs(entry, hass)["current_period_start"] == "2026-09-09"
    second = adjustment("correction", 180, "date-2", corrected_paid_at="2026-09-12")
    await integration._handle_adjust_bill(hass, second)
    hass.data["device_companion"]["entry_locks"] = {}
    await integration._handle_adjust_bill(hass, second)
    assert len(entry.options["service_adjustments"]) == 2
    assert entry.options["service_payments"] == original
    assert entry.options["expiration_date"] == "2026-10-12"
    assert costs(entry, hass)["current_monthly_cost"] == 180
    assert costs(entry, hass)["main_net_investment"] == 180
    revision = entry.options["service_adjustments"][-1]["date_correction"]
    assert revision["before"]["paid_at"] == "2026-09-09"
    assert revision["after"]["paid_at"] == "2026-09-12"


@pytest.mark.asyncio
async def test_historical_date_correction_preserves_later_subscription(recorded_service):
    entry, hass = recorded_service
    await integration._handle_renew_service(hass, SimpleNamespace(data={"entity_id": "sensor.test", "months": 1, "cost": 200}))
    later_period = entry.options["service_payments"][-1].copy()
    await integration._handle_adjust_bill(hass, adjustment("correction", 140, corrected_paid_at="2026-09-20"))
    assert entry.options["expiration_date"] == "2026-11-15"
    assert entry.options["service_period_start"] == "2026-10-15"
    assert entry.options["service_payments"][-1] == later_period
    assert costs(entry, hass)["current_period_start"] == "2026-09-20"


@pytest.mark.asyncio
async def test_recorrecting_after_renewal_cannot_restore_superseded_snapshot(recorded_service, monkeypatch):
    entry, hass = recorded_service
    await integration._handle_adjust_bill(hass, adjustment("correction", 140, "before-renewal", corrected_paid_at="2026-09-09"))
    await integration._handle_renew_service(hass, SimpleNamespace(data={"entity_id": "sensor.test", "months": 1, "cost": 200}))
    await integration._handle_adjust_bill(hass, adjustment("correction", 140, "after-renewal", corrected_paid_at="2026-09-12"))
    monkeypatch.setattr("custom_components.device_companion.sensor.today_local", lambda: date(2026, 9, 10))
    assert costs(entry, hass)["current_monthly_cost"] == 0
    assert entry.options["expiration_date"] == "2026-11-09"


@pytest.mark.asyncio
@pytest.mark.parametrize("extra", [
    {"corrected_paid_at": "2026-10-01"}, {"corrected_paid_at": "2026-08-14"},
    {"corrected_paid_at": "bad"}, {"corrected_paid_at": "2026-08-15"},
    {"operation": "refund", "corrected_paid_at": "2026-09-01"},
])
async def test_invalid_or_unchanged_date_revision_never_writes(recorded_service, extra):
    from copy import deepcopy

    entry, hass = recorded_service
    before = deepcopy(entry.options)
    with pytest.raises(ServiceValidationError):
        await integration._handle_adjust_bill(hass, adjustment(**{"operation": "correction", "cost": 140, **extra}))
    assert entry.options == before


@pytest.mark.asyncio
async def test_date_correction_requires_known_coverage_and_rejects_refunded_bill(recorded_service):
    from copy import deepcopy

    entry, hass = recorded_service
    entry.options["service_payments"][0].pop("months_covered")
    before = deepcopy(entry.options)
    with pytest.raises(ServiceValidationError, match="覆盖月数"):
        await integration._handle_adjust_bill(hass, adjustment("correction", 140, corrected_paid_at="2026-09-01"))
    assert entry.options == before
    entry.options["service_payments"][0]["months_covered"] = 1
    await integration._handle_adjust_bill(hass, adjustment(cost=20))
    before = deepcopy(entry.options)
    with pytest.raises(ServiceValidationError, match="已有退款"):
        await integration._handle_adjust_bill(hass, adjustment("correction", 140, "after-refund", corrected_paid_at="2026-09-01"))
    assert entry.options == before


@pytest.mark.asyncio
async def test_charge_date_correction_moves_month_without_touching_expiry(recorded_service, monkeypatch):
    entry, hass = recorded_service
    await integration._handle_service_charge(hass, SimpleNamespace(data={"entity_id": "sensor.test", "cost": 40, "charge_type": "other", "paid_at": "2026-09-01"}))
    charge = entry.options["service_charges"][0]
    await integration._handle_adjust_bill(hass, adjustment("correction", 40, bill_id=charge["id"], corrected_paid_at="2026-08-20"))
    assert entry.options["expiration_date"] == "2026-10-15"
    assert charge["paid_at"] == "2026-09-01"
    assert costs(entry, hass)["current_month_extra_cost"] == 0
    monkeypatch.setattr("custom_components.device_companion.sensor.today_local", lambda: date(2026, 8, 25))
    assert costs(entry, hass)["current_month_extra_cost"] == 40


@pytest.mark.asyncio
async def test_actual_date_can_correct_original_wrong_future_date(recorded_service):
    entry, hass = recorded_service
    entry.options["service_payments"][0]["paid_at"] = "2026-10-15"
    await integration._handle_adjust_bill(hass, adjustment("correction", 140, corrected_paid_at="2026-09-09"))
    assert entry.options["expiration_date"] == "2026-10-09"
    assert costs(entry, hass)["service_payments"][0]["paid_at"] == "2026-09-09"


@pytest.mark.asyncio
async def test_corrected_expiry_replaces_calendar_and_reminder(recorded_service, monkeypatch):
    entry, hass = recorded_service
    notifications, dismissed = [], []
    monkeypatch.setattr(integration.persistent_notification, "async_dismiss", lambda _hass, notification_id: dismissed.append(notification_id))
    monkeypatch.setattr(integration.persistent_notification, "async_create", lambda _hass, message, **kwargs: notifications.append({"message": message, **kwargs}))
    monkeypatch.setattr("custom_components.device_companion.reminders.today_local", lambda: date(2026, 9, 30))
    entry.options.update(expiry_reminders=True, expiry_reminder_sent={"expiration": "2026-10-15", "thresholds": [7]})
    await integration._handle_adjust_bill(hass, adjustment("correction", 140, corrected_paid_at="2026-09-01"))
    assert dismissed == ["device_companion_expiry_v13"]
    assert "expiry_reminder_sent" not in entry.options
    events = DeviceCompanionCalendar(entry)._build_events(date(2026, 9, 30), date(2026, 10, 16))
    assert [event.start for event in events] == [date(2026, 10, 1)]
    await async_check_expiry(hass, entry)
    await async_check_expiry(hass, entry)
    assert len(notifications) == 1
    assert "2026-10-01" in notifications[0]["message"]
    assert "2026-10-15" not in notifications[0]["message"]


@pytest.mark.asyncio
async def test_refund_preserves_original_and_coverage_replay_after_restart(recorded_service):
    from copy import deepcopy
    entry, hass = recorded_service
    original = deepcopy(entry.options["service_payments"])
    await integration._handle_adjust_bill(hass, adjustment(cost=140.0))
    assert entry.options["service_payments"] == original
    assert entry.options["expiration_date"] == "2026-10-15"
    assert entry.options["plan_monthly_price"] == 200
    assert costs(entry, hass)["main_net_investment"] == 0
    assert costs(entry, hass)["current_monthly_cost"] == 0
    hass.data["device_companion"]["entry_locks"] = {}
    await integration._handle_adjust_bill(hass, adjustment(cost=140.0))
    assert len(entry.options["service_adjustments"]) == 1
    assert "accumulated_cost" not in entry.options


@pytest.mark.asyncio
async def test_adjustment_request_conflict_and_missing_or_duplicate_bill(recorded_service):
    from copy import deepcopy
    entry, hass = recorded_service
    await integration._handle_adjust_bill(hass, adjustment(cost=20))
    before = deepcopy(entry.options)
    with pytest.raises(ServiceValidationError, match="另一笔"):
        await integration._handle_adjust_bill(hass, adjustment(cost=21))
    assert entry.options == before
    entry.options["service_charges"] = [{"id": "initial", "cost": 10}]
    with pytest.raises(ServiceValidationError, match="唯一"):
        await integration._handle_adjust_bill(hass, adjustment(request_id="new"))


@pytest.mark.asyncio
async def test_future_coverage_refund_does_not_change_active_snapshot(recorded_service):
    entry, hass = recorded_service
    await integration._handle_renew_service(hass, SimpleNamespace(data={"entity_id": "sensor.test", "months": 1, "cost": 200}))
    future_id = entry.options["service_payments"][-1]["id"]
    await integration._handle_adjust_bill(hass, adjustment(cost=50, bill_id=future_id))
    assert costs(entry, hass)["current_monthly_cost"] == 140
    assert costs(entry, hass)["main_net_investment"] == 290
    assert entry.options["expiration_date"] == "2026-11-15"


@pytest.mark.asyncio
async def test_corrections_append_deltas_and_refund_uses_corrected_balance(recorded_service):
    entry, hass = recorded_service
    await integration._handle_adjust_bill(hass, adjustment("correction", 100, "c-1"))
    await integration._handle_adjust_bill(hass, adjustment("correction", 180, "c-2"))
    await integration._handle_adjust_bill(hass, adjustment("refund", 30, "r-1"))
    assert [row["amount"] for row in entry.options["service_adjustments"]] == [-40, 80, -30]
    assert costs(entry, hass)["main_net_investment"] == 150
    assert costs(entry, hass)["current_monthly_cost"] == 150
    with pytest.raises(ServiceValidationError, match="已有退款"):
        await integration._handle_adjust_bill(hass, adjustment("correction", 200, "c-3"))


@pytest.mark.asyncio
@pytest.mark.parametrize("extra", [{"cost": 141}, {"cost": 0}, {"cost": -1}, {"cost": float("nan")}, {"cost": .001}, {"bill_id": "missing"}, {"paid_at": "2026-08-14"}, {"paid_at": "2026-10-01"}, {"description": " "}])
async def test_invalid_adjustment_never_writes_receipt_or_ledger(recorded_service, extra):
    from copy import deepcopy
    entry, hass = recorded_service
    before = deepcopy(entry.options)
    with pytest.raises(ServiceValidationError):
        await integration._handle_adjust_bill(hass, adjustment(**extra))
    assert entry.options == before


@pytest.mark.asyncio
async def test_concurrent_refunds_cannot_over_refund_and_cancel_does_not_block(recorded_service):
    entry, hass = recorded_service
    entry.options["status"] = "canceled"
    results = await asyncio.gather(*(integration._handle_adjust_bill(hass, adjustment(cost=80, request_id=f"r-{i}")) for i in range(2)), return_exceptions=True)
    assert sum(isinstance(result, ServiceValidationError) for result in results) == 1
    assert len(entry.options["service_adjustments"]) == 1
    assert costs(entry, hass)["main_net_investment"] == 60


@pytest.mark.asyncio
async def test_charge_refund_adjusts_original_month_not_refund_month(recorded_service, monkeypatch):
    entry, hass = recorded_service
    await integration._handle_service_charge(hass, SimpleNamespace(data={"entity_id": "sensor.test", "cost": 40, "charge_type": "other", "paid_at": "2026-09-01"}))
    charge_id = entry.options["service_charges"][0]["id"]
    await integration._handle_adjust_bill(hass, adjustment(cost=10, bill_id=charge_id))
    assert costs(entry, hass)["current_month_extra_cost"] == 30
    monkeypatch.setattr("custom_components.device_companion.sensor.today_local", lambda: date(2026, 10, 1))
    assert costs(entry, hass)["current_month_extra_cost"] == 0
    assert costs(entry, hass)["main_net_investment"] == 170


def test_adjustment_schema_requires_receipt_reason_and_original_bill():
    for key in ("request_id", "description", "bill_id"):
        payload = adjustment().data.copy()
        del payload[key]
        with pytest.raises(vol.Invalid):
            integration.ADJUST_BILL_SCHEMA(payload)


@pytest.mark.asyncio
async def test_refund_cents_and_corrupt_adjustments_fail_safely(recorded_service):
    from copy import deepcopy
    entry, hass = recorded_service
    entry.data["total_price"] = .30
    entry.options["service_payments"][0]["amount"] = .30
    await integration._handle_adjust_bill(hass, adjustment(cost=.1, request_id="cents-1"))
    await integration._handle_adjust_bill(hass, adjustment(cost=.2, request_id="cents-2"))
    assert costs(entry, hass)["main_net_investment"] == 0
    with pytest.raises(ServiceValidationError, match="剩余净额"):
        await integration._handle_adjust_bill(hass, adjustment(cost=.01, request_id="cents-3"))
    entry.options["service_adjustments"][0]["amount"] = "broken"
    before = deepcopy(entry.options)
    with pytest.raises(ServiceValidationError):
        await integration._handle_adjust_bill(hass, adjustment(cost=.01, request_id="cents-4"))
    assert entry.options == before


def test_no_adjustment_keeps_legacy_subcent_calculation(recorded_service):
    entry, hass = recorded_service
    entry.options["service_payments"][0]["amount"] = 1.005
    attrs = costs(entry, hass)
    assert attrs["current_monthly_cost"] == round(1.005, 2)
    assert "service_adjustments" not in entry.options


@pytest.mark.asyncio
@pytest.mark.parametrize("expiration", [None, "永久"])
async def test_active_service_without_expiry_can_record_charge(service, expiration):
    entry, hass = service
    entry.options["expiration_date"] = expiration
    await integration._handle_service_charge(hass, SimpleNamespace(data={
        "entity_id": "sensor.test", "cost": 5.0,
        "charge_type": "extra_quota", "paid_at": "2026-09-30",
    }))
    assert entry.options["expiration_date"] == expiration
    assert entry.options["accumulated_cost"] == 5.0
    assert len(entry.options["service_charges"]) == 1


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
@pytest.mark.parametrize("expiration", ["2026-09-29", "2026-10-15"])
async def test_explicit_actual_payment_starts_renewal_not_today_or_old_expiry(service, expiration):
    entry, hass = service
    entry.options["expiration_date"] = expiration
    await integration._handle_renew_service(hass, SimpleNamespace(data={
        "entity_id": "sensor.test", "cost": 140, "months": 1, "paid_at": "2026-09-28",
    }))
    assert entry.options["service_period_start"] == "2026-09-28"
    assert entry.options["expiration_date"] == "2026-10-28"
    assert costs(entry, hass)["current_period_start"] == "2026-09-28"


@pytest.mark.asyncio
@pytest.mark.parametrize("day,months,expected", [
    ("2026-01-31", 1, "2026-02-28"), ("2028-01-31", 1, "2028-02-29"),
    ("2026-12-31", 2, "2027-02-28"),
])
async def test_date_correction_uses_calendar_month_boundaries(recorded_service, monkeypatch, day, months, expected):
    entry, hass = recorded_service
    entry.data["purchase_date"] = "2020-01-01"
    entry.options["service_payments"][0]["months_covered"] = months
    monkeypatch.setattr(integration, "today_local", lambda: date(2028, 2, 1))
    await integration._handle_adjust_bill(hass, adjustment("correction", 140, paid_at="2028-02-01", corrected_paid_at=day))
    assert entry.options["expiration_date"] == expected
    assert entry.options["service_period_start"] == day


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


@pytest.mark.asyncio
async def test_real_date_correction_service_reload_and_entity_identity(hass, enable_custom_integrations, monkeypatch):
    from copy import deepcopy
    from homeassistant.helpers import entity_registry as er

    monkeypatch.setattr(integration, "today_local", lambda: date(2026, 9, 30))
    monkeypatch.setattr("custom_components.device_companion.sensor.today_local", lambda: date(2026, 9, 30))
    flow = await hass.config_entries.flow.async_init("device_companion", context={"source": "user"})
    flow = await hass.config_entries.flow.async_configure(flow["flow_id"], {"category": "虚拟服务"})
    result = await hass.config_entries.flow.async_configure(flow["flow_id"], {
        "device_name": "日期纠错订阅", "purchase_date": "2026-09-12", "total_price": 280.0,
        "plan_monthly_price": 140.0, "sub_period": "1个月", "service_period_months": 2,
    })
    entry = result["result"]
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id("sensor", "device_companion", f"companion_{entry.entry_id}")
    calendar_id = registry.async_get_entity_id("calendar", "device_companion", f"calendar_{entry.entry_id}")
    original_data, original_bills = deepcopy(dict(entry.data)), deepcopy(entry.options["service_payments"])
    payload = {"entity_id": entity_id, "bill_id": original_bills[0]["id"], "operation": "correction",
               "cost": 280, "corrected_paid_at": "2026-09-15", "description": "更正实际付款日期", "request_id": "real-date-fix"}
    await hass.services.async_call("device_companion", "adjust_service_bill", payload, blocking=True)
    await hass.async_block_till_done()
    assert entry.options["expiration_date"] == "2026-11-15"
    assert entry.options["service_payments"] == original_bills
    assert dict(entry.data) == original_data
    attrs = hass.states.get(entity_id).attributes
    assert attrs["service_payments"][0]["paid_at"] == "2026-09-15"
    assert attrs["current_period_start"] == "2026-09-15"
    assert attrs["current_monthly_cost"] == 140
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    await hass.services.async_call("device_companion", "adjust_service_bill", payload, blocking=True)
    await hass.async_block_till_done()
    assert len(entry.options["service_adjustments"]) == 1
    assert registry.async_get_entity_id("sensor", "device_companion", f"companion_{entry.entry_id}") == entity_id
    assert registry.async_get_entity_id("calendar", "device_companion", f"calendar_{entry.entry_id}") == calendar_id
    assert hass.states.get(entity_id).attributes["expiration_date"] == "2026-11-15"
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
