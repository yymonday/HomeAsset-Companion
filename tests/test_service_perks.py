"""Gift subscription periods must follow renewals without becoming cash costs."""

from copy import deepcopy
from datetime import date
from types import SimpleNamespace
import asyncio

import pytest
import voluptuous as vol
from homeassistant.exceptions import ServiceValidationError

import custom_components.device_companion as integration
from custom_components.device_companion.sensor import DeviceCompanionSensor
from custom_components.device_companion.calendar import DeviceCompanionCalendar


@pytest.fixture
def perk_service(monkeypatch):
    entry = SimpleNamespace(
        entry_id="perks", data={"kind": "service", "device_name": "主订阅",
                                "purchase_date": "2025-10-08", "total_price": 300},
        options={"status": "active", "sub_period": "1年", "expiration_date": "2026-10-08",
                 "service_period_start": "2025-10-08", "current_period_cost": 300,
                 "service_period_months": 12, "plan_monthly_price": 25,
                 "accessories_list": [{"id": "music", "name": "网易云音乐VIP", "price": 216,
                                       "purchase_date": "2025-10-08", "expiration_date": "2026-10-08",
                                       "status": "active", "image": "/local/music.png"}]},
    )

    class Entries:
        def async_get_entry(self, _id):
            return entry

        def async_update_entry(self, target, **changes):
            for key, value in changes.items():
                setattr(target, key, value)

    hass = SimpleNamespace(data={"device_companion": {"entry_locks": {}}}, config_entries=Entries(), states={})

    async def resolve(_hass, _entity_id):
        return entry

    monkeypatch.setattr(integration, "_resolve_target_entry", resolve)
    monkeypatch.setattr(integration, "today_local", lambda: date(2026, 10, 11))
    monkeypatch.setattr("custom_components.device_companion.sensor.today_local", lambda: date(2026, 10, 11))
    return entry, hass


@pytest.mark.asyncio
async def test_main_renewal_updates_expired_gift_without_extra_payment(perk_service):
    entry, hass = perk_service
    original_data = deepcopy(entry.data)
    call = SimpleNamespace(data={"entity_id": "sensor.main", "paid_at": "2026-10-10",
                                 "months": 12, "cost": 300, "request_id": "annual"})
    await integration._handle_renew_service(hass, call)
    perk = entry.options["accessories_list"][0]
    assert perk["expiration_date"] == "2027-10-10"
    assert perk["service_period_start"] == "2026-10-10"
    assert perk["purchase_date"] == "2025-10-08"
    assert (perk["id"], perk["price"], perk["image"]) == ("music", 216, "/local/music.png")
    assert entry.data == original_data
    assert len(entry.options["service_payments"]) == 1
    assert entry.options["accumulated_cost"] == 300
    sensor = DeviceCompanionSensor(entry)
    sensor.hass = hass
    attrs = sensor._compute()[1]
    assert attrs["accessories_list"][0]["status"] == "active"
    assert attrs["total_saved_value"] == 216
    before = deepcopy(entry.options)
    await integration._handle_renew_service(hass, call)
    assert entry.options == before


@pytest.mark.asyncio
async def test_existing_renewal_can_sync_gift_without_new_bill(perk_service):
    entry, hass = perk_service
    entry.options.update(service_period_start="2026-10-10", expiration_date="2027-10-10")
    parent = {key: deepcopy(value) for key, value in entry.options.items() if key != "accessories_list"}
    await integration._handle_renew_perk(hass, SimpleNamespace(data={
        "entity_id": "sensor.main", "perk_id": "music", "follow_main_renewal": True,
    }))
    assert entry.options["accessories_list"][0]["expiration_date"] == "2027-10-10"
    assert {key: value for key, value in entry.options.items() if key != "accessories_list"} == parent


@pytest.mark.asyncio
async def test_main_renewal_preserves_independent_canceled_and_malformed_items(perk_service):
    entry, hass = perk_service
    original = entry.options["accessories_list"][0]
    independent = {**deepcopy(original), "id": "independent", "follow_main_renewal": False}
    canceled = {**deepcopy(original), "id": "canceled", "status": "canceled", "is_retired": True}
    legacy_stopped = {**deepcopy(original), "id": "legacy", "is_retired": True}
    legacy_stopped.pop("status")
    entry.options["accessories_list"].extend([independent, canceled, legacy_stopped, None, "bad"])
    untouched = deepcopy(entry.options["accessories_list"][1:])
    await integration._handle_renew_service(hass, SimpleNamespace(data={
        "entity_id": "sensor.main", "paid_at": "2026-10-10", "months": 12, "cost": 300,
    }))
    assert entry.options["accessories_list"][1:] == untouched


@pytest.mark.asyncio
async def test_independent_renewal_changes_only_gift_and_keeps_history(perk_service):
    entry, hass = perk_service
    before = deepcopy(entry.options)
    await integration._handle_renew_perk(hass, SimpleNamespace(data={
        "entity_id": "sensor.main", "perk_id": "music", "follow_main_renewal": False,
        "start_date": "2026-10-09", "expiration_date": "2026-11-09",
    }))
    perk = entry.options["accessories_list"][0]
    assert perk["follow_main_renewal"] is False
    assert perk["service_period_start"] == "2026-10-09"
    assert perk["expiration_date"] == "2026-11-09"
    assert perk["renewal_history"] == [{
        "before": {"period_start": "2025-10-08", "period_end": "2026-10-08"},
        "after": {"period_start": "2026-10-09", "period_end": "2026-11-09"},
        "recorded_at": "2026-10-11", "source": "manual",
    }]
    assert {key: value for key, value in entry.options.items() if key != "accessories_list"} == {
        key: value for key, value in before.items() if key != "accessories_list"
    }


@pytest.mark.asyncio
async def test_sync_concurrency_retry_and_restart_deduplicate(perk_service):
    entry, hass = perk_service
    entry.options.update(service_period_start="2026-10-10", expiration_date="2027-10-10")
    payload = {"entity_id": "sensor.main", "perk_id": "music", "request_id": "gift-sync"}
    await asyncio.gather(*[integration._handle_renew_perk(hass, SimpleNamespace(data=payload)) for _ in range(8)])
    before = deepcopy(entry.options)
    hass.data["device_companion"]["entry_locks"] = {}
    await integration._handle_renew_perk(hass, SimpleNamespace(data=payload))
    assert entry.options == before
    assert len(entry.options["accessories_list"][0]["renewal_history"]) == 1
    assert len(entry.options["payment_requests"]) == 1
    assert "service_payments" not in entry.options
    with pytest.raises(ServiceValidationError):
        await integration._handle_renew_perk(hass, SimpleNamespace(data={
            **payload, "follow_main_renewal": False, "start_date": "2026-10-11", "expiration_date": "2027-11-11",
        }))
    assert entry.options == before


@pytest.mark.asyncio
@pytest.mark.parametrize("fields", [
    {"perk_id": "unknown"},
    {"start_date": "2026-10-11"},
    {"follow_main_renewal": False},
    {"follow_main_renewal": False, "start_date": "bad", "expiration_date": "2027-10-11"},
    {"follow_main_renewal": False, "start_date": "2026-10-11", "expiration_date": "2026-10-11"},
    {"follow_main_renewal": False, "start_date": "2026-10-12", "expiration_date": "2026-10-11"},
    {"follow_main_renewal": False, "start_date": "2025-10-07", "expiration_date": "2027-10-11"},
])
async def test_invalid_perk_actions_never_write(perk_service, fields):
    entry, hass = perk_service
    before = deepcopy(entry.options)
    with pytest.raises(ServiceValidationError):
        await integration._handle_renew_perk(hass, SimpleNamespace(data={
            "entity_id": "sensor.main", "perk_id": "music", "request_id": "invalid", **fields,
        }))
    assert entry.options == before


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["parent", "perk", "kind", "duplicate_id"])
async def test_stopped_wrong_kind_and_ambiguous_perks_rejected(perk_service, target):
    entry, hass = perk_service
    entry.options.update(service_period_start="2026-10-10", expiration_date="2027-10-10")
    if target == "parent":
        entry.options["status"] = "canceled"
    elif target == "perk":
        entry.options["accessories_list"][0]["status"] = "canceled"
    elif target == "kind":
        entry.data["kind"] = "asset"
    else:
        entry.options["accessories_list"].append(deepcopy(entry.options["accessories_list"][0]))
    before = deepcopy(entry.options)
    with pytest.raises(ServiceValidationError):
        await integration._handle_renew_perk(hass, SimpleNamespace(data={"entity_id": "sensor.main", "perk_id": "music"}))
    assert entry.options == before


def test_perk_schema_rejects_cash_and_invalid_fields():
    assert integration.RENEW_PERK_SCHEMA({"entity_id": "sensor.main", "perk_id": "music"})["follow_main_renewal"] is True
    for extra in [{"cost": 216}, {"perk_id": ""}, {"start_date": "bad"}, {"unknown": "x"}]:
        with pytest.raises(vol.Invalid):
            integration.RENEW_PERK_SCHEMA({"entity_id": "sensor.main", "perk_id": "music", **extra})


@pytest.mark.asyncio
async def test_current_parent_date_correction_updates_following_gift_calendar(perk_service):
    entry, hass = perk_service
    await integration._handle_renew_service(hass, SimpleNamespace(data={
        "entity_id": "sensor.main", "paid_at": "2026-10-10", "months": 12, "cost": 300,
    }))
    bill = entry.options["service_payments"][0]
    await integration._handle_adjust_bill(hass, SimpleNamespace(data={
        "entity_id": "sensor.main", "bill_id": bill["id"], "operation": "correction", "cost": 300,
        "corrected_paid_at": "2026-10-09", "description": "纠正日期", "request_id": "parent-fix",
    }))
    perk = entry.options["accessories_list"][0]
    assert (perk["service_period_start"], perk["expiration_date"]) == ("2026-10-09", "2027-10-09")
    assert perk["renewal_history"][-1]["source"] == "main_date_correction"
    events = DeviceCompanionCalendar(entry)._build_events(date(2027, 10, 9), date(2027, 10, 11))
    assert len(events) == 2
    assert all(event.start == date(2027, 10, 9) for event in events)


def test_no_expiry_gift_inherits_dates_without_writing_history(perk_service):
    entry, hass = perk_service
    perk = entry.options["accessories_list"][0]
    perk["expiration_date"] = ""
    entry.options.update(service_period_start="2026-10-10", expiration_date="2027-10-10")
    before = deepcopy(entry.options)
    sensor = DeviceCompanionSensor(entry)
    sensor.hass = hass
    attrs = sensor._compute()[1]
    assert attrs["accessories_list"][0]["expiration_date"] == "2027-10-10"
    assert attrs["accessories_list"][0]["service_period_start"] == "2026-10-10"
    assert len(DeviceCompanionCalendar(entry)._build_events(date(2027, 10, 10), date(2027, 10, 11))) == 2
    assert entry.options == before
    perk["follow_main_renewal"] = False
    assert sensor._compute()[1]["accessories_list"][0]["expiration_date"] == ""


@pytest.mark.asyncio
async def test_legacy_future_renewal_and_mid_period_gift_keep_valid_dates(perk_service):
    entry, hass = perk_service
    entry.options["expiration_date"] = "2026-10-20"
    entry.options["accessories_list"][0]["purchase_date"] = "2026-10-25"
    await integration._handle_renew_service(hass, SimpleNamespace(data={"entity_id": "sensor.main", "months": 1, "cost": 25}))
    perk = entry.options["accessories_list"][0]
    assert entry.options["service_period_start"] == "2026-10-20"
    assert perk["service_period_start"] == "2026-10-25"
    assert perk["expiration_date"] == "2026-11-20"


@pytest.mark.asyncio
async def test_real_perk_options_service_reload_and_stable_ids(hass, enable_custom_integrations, monkeypatch):
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from homeassistant.helpers import entity_registry as er

    monkeypatch.setattr(integration, "today_local", lambda: date(2026, 10, 11))
    monkeypatch.setattr("custom_components.device_companion.sensor.today_local", lambda: date(2026, 10, 11))
    entry = MockConfigEntry(domain="device_companion", version=2,
        data={"kind": "service", "device_name": "实测赠送权益", "purchase_date": "2025-10-08", "total_price": 300},
        options={"status": "active", "expiration_date": "2027-10-10", "service_period_start": "2026-10-10",
                 "accessories_list": [{"id": "music", "name": "音乐权益", "price": 216,
                                       "purchase_date": "2025-10-08", "expiration_date": "2026-10-08", "status": "active"}]})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    unique_ids = [f"companion_{entry.entry_id}", f"acc_{entry.entry_id}_music"]
    ids = [registry.async_get_entity_id("sensor", "device_companion", unique) for unique in unique_ids]
    original_data = deepcopy(dict(entry.data))
    payload = {"entity_id": ids[0], "perk_id": "music", "request_id": "real-perk"}
    assert hass.services.has_service("device_companion", "renew_service_perk")
    await hass.services.async_call("device_companion", "renew_service_perk", payload, blocking=True)
    await hass.async_block_till_done()
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    await hass.services.async_call("device_companion", "renew_service_perk", payload, blocking=True)
    await hass.async_block_till_done()
    assert len(entry.options["accessories_list"][0]["renewal_history"]) == 1
    assert [registry.async_get_entity_id("sensor", "device_companion", unique) for unique in unique_ids] == ids
    assert hass.states.get(ids[1]).attributes["expiration_date"] == "2027-10-10"
    assert "service_payments" not in entry.options

    flow = await hass.config_entries.options.async_init(entry.entry_id)
    flow = await hass.config_entries.options.async_configure(flow["flow_id"], {"next_step_id": "manage_perk_select"})
    flow = await hass.config_entries.options.async_configure(flow["flow_id"], {"selected_item": "music"})
    assert "follow_main_renewal" in {field.schema for field in flow["data_schema"].schema}
    result = await hass.config_entries.options.async_configure(flow["flow_id"], {
        "name": "音乐权益", "price": 216, "purchase_date": "2025-10-08", "expiration_date": "2027-10-10",
        "follow_main_renewal": False, "status": "active",
    })
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    assert entry.options["accessories_list"][0]["follow_main_renewal"] is False
    assert entry.options["accessories_list"][0]["id"] == "music"
    assert len(entry.options["accessories_list"][0]["renewal_history"]) == 1
    assert dict(entry.data) == original_data
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
