"""Sensor platform for HomeAsset Companion."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_change,
)

from .const import (
    CONF_ACCESSORIES_LIST,
    CONF_AUTO_RECORD_REPLACEMENT,
    CONF_CATEGORY,
    CONF_CONSUMABLES_LIST,
    CONF_CURRENT_PERIOD_COST,
    CONF_DEVICE_IMAGE,
    CONF_DEVICE_NAME,
    CONF_EARLY_PAYOFF,
    CONF_EARLY_PAYOFF_FEE,
    CONF_EXPIRATION_DATE,
    CONF_INSTALLMENT_INTEREST,
    CONF_INSTALLMENT_MONTHS,
    CONF_IS_INSTALLMENT,
    CONF_KIND,
    CONF_LINKED_ENTITY,
    CONF_LINKED_PRICE_ENTITY,
    CONF_LOCATION,
    CONF_PURCHASE_DATE,
    CONF_RECOVERY_AMOUNT,
    CONF_STATUS_CHANGED_AT,
    CONF_STORY,
    CONF_SUB_PERIOD,
    CONF_TOTAL_PRICE,
    DOMAIN,
    KIND_ASSET,
    KIND_EVENT,
    KIND_MEMORIAL,
    KIND_SERVICE,
    STATUS_ACTIVE,
    STATUS_EXPIRED,
    STATUS_IDLE,
    STATUS_SOLD,
    TRACKING_MODE_SMART,
)
from .helpers import (
    infer_kind,
    is_terminal_status,
    legacy_status,
    safe_date,
    safe_float,
    safe_int,
    status_label,
    today_local,
)

_LOGGER = logging.getLogger(__name__)
DAYS_PER_MONTH = 30.4375
UNAVAILABLE_STATES = {"unknown", "unavailable", "none", ""}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up all entities for one record."""
    entities: list[SensorEntity] = [DeviceCompanionSensor(entry)]
    entities.extend(
        ConsumableSensor(entry, item)
        for item in entry.options.get(CONF_CONSUMABLES_LIST, [])
    )
    entities.extend(
        AccessorySensor(entry, item)
        for item in entry.options.get(CONF_ACCESSORIES_LIST, [])
    )
    async_add_entities(entities)


def _effective_status(
    stored_status: str,
    kind: str,
    expiration_date,
    today,
) -> str:
    if (
        kind == KIND_SERVICE
        and stored_status == STATUS_ACTIVE
        and expiration_date is not None
        and expiration_date < today
    ):
        return STATUS_EXPIRED
    return stored_status


def _record_end_date(
    record: dict[str, Any],
    status: str,
    *,
    expiration_date=None,
    today=None,
):
    today = today or today_local()
    if status == STATUS_EXPIRED and expiration_date is not None:
        return expiration_date
    if is_terminal_status(status):
        return safe_date(
            record.get(CONF_STATUS_CHANGED_AT) or record.get("retirement_date"), today
        )
    return today


def _installment_state(
    price: float,
    interest: float,
    months: int,
    purchase_date,
    calculation_date,
    early_payoff: bool,
) -> dict[str, Any]:
    if months <= 0:
        return {
            "months_paid": 0,
            "outstanding_balance": 0.0,
            "is_paid_off": True,
        }
    months_passed = max(
        0,
        (calculation_date.year - purchase_date.year) * 12
        + calculation_date.month
        - purchase_date.month,
    )
    months_paid = min(months, months_passed)
    total = price + interest
    outstanding = 0.0 if early_payoff else max(
        0.0, round(total - (total / months * months_paid), 2)
    )
    return {
        "months_paid": months_paid,
        "outstanding_balance": outstanding,
        "is_paid_off": early_payoff or outstanding <= 0,
    }


def _consumable_metrics(hass: HomeAssistant, item: dict[str, Any], today) -> dict[str, Any]:
    linked_id = item.get(CONF_LINKED_ENTITY, "")
    mode = item.get("tracking_mode")
    is_smart = mode == TRACKING_MODE_SMART or bool(linked_id)
    price = max(0.0, safe_float(item.get("price")))
    last_replace = safe_date(item.get("last_replace"), today)
    days_elapsed = max(1, (today - last_replace).days)
    cycle = max(0, safe_int(item.get("cycle")))

    percent: float | None
    remain: str
    current_daily = 0.0
    available = True
    source_state = ""

    if is_smart:
        state = hass.states.get(linked_id) if linked_id else None
        if state is None or state.state.lower() in UNAVAILABLE_STATES:
            percent = None
            remain = "实体不可用"
            available = False
        else:
            source_state = state.state
            normalized = state.state.lower()
            if normalized == "on":
                percent = 0.0
                remain = "已耗尽"
                current_daily = price / cycle if cycle > 0 else 0.0
            elif normalized == "off":
                percent = 100.0
                remain = "状态正常"
                current_daily = price / cycle if cycle > 0 else 0.0
            else:
                try:
                    percent = max(0.0, min(100.0, float(state.state)))
                    remain = "实体同步"
                    consumed_value = price * ((100.0 - percent) / 100.0)
                    current_daily = consumed_value / days_elapsed
                except (TypeError, ValueError):
                    percent = None
                    remain = "状态无法解析"
                    available = False
    else:
        cycle = max(1, cycle)
        remaining_days = max(0, cycle - days_elapsed)
        percent = max(0.0, min(100.0, round(remaining_days / cycle * 100)))
        remain = f"{remaining_days} 天"
        current_daily = price / cycle

    return {
        "id": item.get("id", ""),
        "name": item.get("name", "耗材"),
        "price": price,
        "image": item.get("image", ""),
        "remain": remain,
        "percent": percent,
        "daily_cost": round(current_daily, 2),
        "current_daily_cost": round(current_daily, 4),
        "is_smart": is_smart,
        "tracking_available": available,
        "source_state": source_state,
        "replacement_due": percent is not None and percent <= 10,
        "auto_record_replacement": item.get(CONF_AUTO_RECORD_REPLACEMENT, False),
        "last_replace": str(last_replace),
        "accumulated_cost": max(0.0, safe_float(item.get("accumulated_cost", price))),
    }


class DeviceCompanionSensor(SensorEntity):
    """Main lifecycle and financial summary sensor."""

    _attr_icon = "mdi:calendar-heart"
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._replacement_reset_inflight: set[str] = set()
        self._attr_name = f"{entry.data.get(CONF_DEVICE_NAME, '未知')} 陪伴"
        self._attr_unique_id = f"companion_{entry.entry_id}"
        self._device_name = entry.data.get(CONF_DEVICE_NAME, "未知")

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=self._device_name,
            manufacturer="HomeAsset Companion",
            model=self._entry.data.get(CONF_CATEGORY, "未分类"),
        )

    @property
    def entity_picture(self) -> str | None:
        image = str(self._entry.data.get(CONF_DEVICE_IMAGE, "")).strip()
        return image or None

    async def async_added_to_hass(self) -> None:
        """Subscribe to linked entities and the local midnight boundary."""
        linked_entities = {
            item.get(CONF_LINKED_ENTITY)
            for item in self._entry.options.get(CONF_CONSUMABLES_LIST, [])
            if item.get(CONF_LINKED_ENTITY)
        }
        linked_price = self._entry.options.get(CONF_LINKED_PRICE_ENTITY)
        if linked_price:
            linked_entities.add(linked_price)

        if linked_entities:
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass,
                    list(linked_entities),
                    self._async_linked_state_changed,
                )
            )

        self.async_on_remove(
            async_track_time_change(
                self.hass,
                self._async_midnight_update,
                hour=0,
                minute=0,
                second=5,
            )
        )

    @callback
    def _async_midnight_update(self, now: datetime) -> None:
        self.async_write_ha_state()

    @callback
    def _async_linked_state_changed(self, event) -> None:
        old_state = event.data.get("old_state")
        new_state = event.data.get("new_state")
        self.async_write_ha_state()
        if old_state is None or new_state is None:
            return

        linked_entity = event.data.get("entity_id")
        for item in self._entry.options.get(CONF_CONSUMABLES_LIST, []):
            if item.get(CONF_LINKED_ENTITY) != linked_entity:
                continue
            if not self._is_replacement_reset(old_state.state, new_state.state):
                continue
            self.hass.async_create_task(self._async_handle_detected_reset(item))

    @staticmethod
    def _is_replacement_reset(old_value: str, new_value: str) -> bool:
        old_normalized = str(old_value).lower()
        new_normalized = str(new_value).lower()
        if old_normalized in UNAVAILABLE_STATES or new_normalized in UNAVAILABLE_STATES:
            return False
        if old_normalized == "on" and new_normalized == "off":
            return True
        try:
            return float(old_value) <= 20.0 and float(new_value) >= 90.0
        except (TypeError, ValueError):
            return False

    async def _async_handle_detected_reset(self, item: dict[str, Any]) -> None:
        cons_id = item.get("id", "")
        if not cons_id or cons_id in self._replacement_reset_inflight:
            return

        latest = self.hass.config_entries.async_get_entry(self._entry.entry_id)
        latest_item = next(
            (candidate for candidate in (latest.options.get(CONF_CONSUMABLES_LIST, []) if latest else [])
             if candidate.get("id") == cons_id),
            item,
        )
        if latest_item.get("last_detected_reset") == str(today_local()):
            return

        self._replacement_reset_inflight.add(cons_id)
        name = latest_item.get("name", "耗材")
        price = max(0.0, safe_float(latest_item.get("price")))
        if latest_item.get(CONF_AUTO_RECORD_REPLACEMENT, False):
            try:
                await self.hass.services.async_call(
                    DOMAIN,
                    "replace_consumable",
                    {
                        "entity_id": self.entity_id,
                        "cons_id": cons_id,
                        "cost": price,
                    },
                    blocking=True,
                )
            finally:
                self._replacement_reset_inflight.discard(cons_id)
            return

        self.hass.bus.async_fire(
            "device_companion_consumable_replacement_detected",
            {
                "entity_id": self.entity_id,
                "cons_id": cons_id,
                "name": name,
                "suggested_cost": price,
            },
        )
        await self.hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "notification_id": f"device_companion_{self._entry.entry_id}_{cons_id}",
                "title": "检测到耗材可能已更换",
                "message": (
                    f"{self._device_name} 的“{name}”状态从低余量恢复到高余量。"
                    "为避免状态抖动造成重复记账，本次未自动增加费用；请在陪伴卡片中确认。"
                ),
            },
            blocking=False,
        )
        self.async_on_remove(
            async_call_later(
                self.hass,
                300,
                lambda now: self._replacement_reset_inflight.discard(cons_id),
            )
        )

    def _compute(self) -> tuple[int, dict[str, Any]]:
        today = today_local()
        data = dict(self._entry.data)
        options = dict(self._entry.options)
        kind = infer_kind(data)
        category = data.get(CONF_CATEGORY, "其他类别")
        purchase_date = safe_date(data.get(CONF_PURCHASE_DATE), today)
        expiration_date = safe_date(options.get(CONF_EXPIRATION_DATE))

        stored_status = legacy_status(options)
        status = _effective_status(stored_status, kind, expiration_date, today)
        end_date = _record_end_date(
            options,
            status,
            expiration_date=expiration_date,
            today=today,
        )
        actual_days = max(0, (end_date - purchase_date).days)
        divisor_days = max(1, actual_days)

        base_purchase = max(0.0, safe_float(data.get(CONF_TOTAL_PRICE)))
        accumulated_service_cost = max(0.0, safe_float(options.get("accumulated_cost")))
        main_cash_cost = base_purchase + accumulated_service_cost

        is_installment = bool(data.get(CONF_IS_INSTALLMENT, False))
        interest = (
            max(0.0, safe_float(data.get(CONF_INSTALLMENT_INTEREST)))
            if is_installment
            else 0.0
        )
        early_payoff = bool(options.get(CONF_EARLY_PAYOFF, False))
        early_fee = (
            max(0.0, safe_float(options.get(CONF_EARLY_PAYOFF_FEE)))
            if is_installment and early_payoff
            else 0.0
        )
        main_recovery = (
            max(0.0, safe_float(options.get(CONF_RECOVERY_AMOUNT)))
            if stored_status == STATUS_SOLD
            else 0.0
        )
        net_main_investment = main_cash_cost + interest + early_fee - main_recovery

        current_reference_value = base_purchase
        linked_price_entity = options.get(CONF_LINKED_PRICE_ENTITY, "")
        if kind == KIND_MEMORIAL and linked_price_entity:
            linked_state = self.hass.states.get(linked_price_entity)
            if linked_state and linked_state.state.lower() not in UNAVAILABLE_STATES:
                current_reference_value = safe_float(
                    linked_state.state, 1.0
                ) * base_purchase

        processed_consumables: list[dict[str, Any]] = []
        total_consumable_cost = 0.0
        current_consumable_daily = 0.0
        for source in options.get(CONF_CONSUMABLES_LIST, []):
            metrics = _consumable_metrics(self.hass, source, today)
            processed_consumables.append(metrics)
            total_consumable_cost += metrics["accumulated_cost"]
            current_consumable_daily += metrics["current_daily_cost"]

        processed_accessories: list[dict[str, Any]] = []
        total_accessory_net = 0.0
        total_accessory_recovery = 0.0
        accessory_historical_daily = 0.0
        total_saved_value = 0.0

        for source in options.get(CONF_ACCESSORIES_LIST, []):
            item = deepcopy(source)
            purchase = safe_date(item.get("purchase_date"), today)
            item_expiration = safe_date(item.get(CONF_EXPIRATION_DATE))
            stored_item_status = legacy_status(item)
            item_status = (
                STATUS_EXPIRED
                if kind == KIND_SERVICE
                and stored_item_status == STATUS_ACTIVE
                and item_expiration is not None
                and item_expiration < today
                else stored_item_status
            )
            item_end = _record_end_date(
                item,
                item_status,
                expiration_date=item_expiration,
                today=today,
            )
            item_days = max(0, (item_end - purchase).days)
            item_divisor = max(1, item_days)
            item_price = max(0.0, safe_float(item.get("price")))
            item_recovery = (
                max(0.0, safe_float(item.get(CONF_RECOVERY_AMOUNT)))
                if stored_item_status == STATUS_SOLD
                else 0.0
            )
            total_accessory_recovery += item_recovery

            item_is_installment = bool(item.get(CONF_IS_INSTALLMENT, False))
            item_interest = (
                max(0.0, safe_float(item.get(CONF_INSTALLMENT_INTEREST)))
                if item_is_installment
                else 0.0
            )
            item_early = bool(item.get(CONF_EARLY_PAYOFF, False))
            item_early_fee = (
                max(0.0, safe_float(item.get(CONF_EARLY_PAYOFF_FEE)))
                if item_early
                else 0.0
            )
            item_net = item_price + item_interest + item_early_fee - item_recovery

            if kind == KIND_SERVICE:
                total_saved_value += item_price
                item_daily = 0.0
            else:
                total_accessory_net += item_net
                item_daily = item_net / item_divisor
                accessory_historical_daily += item_daily

            item_installment_months = safe_int(item.get(CONF_INSTALLMENT_MONTHS))
            installment = _installment_state(
                item_price,
                item_interest,
                item_installment_months,
                purchase,
                item_end,
                item_early,
            )
            processed_accessories.append(
                {
                    "id": item.get("id", ""),
                    "name": item.get("name", "附属项目"),
                    "price": item_price,
                    "image": item.get("image", ""),
                    "daily_cost": round(item_daily, 2),
                    "days": item_days,
                    "status": item_status,
                    "status_label": status_label(item_status),
                    "is_retired": is_terminal_status(item_status)
                    or item_status == STATUS_EXPIRED,
                    "reason": status_label(item_status),
                    "is_wearing": item.get("is_wearing", False),
                    "purchase_date": str(purchase),
                    "expiration_date": str(item_expiration) if item_expiration else "",
                    "is_installment": item_is_installment,
                    "installment_months": item_installment_months,
                    "months_paid": installment["months_paid"],
                    "outstanding_balance": installment["outstanding_balance"],
                    "is_paid_off": installment["is_paid_off"],
                    "early_payoff": item_early,
                    "installment_interest": item_interest,
                    "net_investment": round(item_net, 2),
                }
            )

        gross_investment = (
            main_cash_cost
            + interest
            + early_fee
            + total_accessory_net
            + total_accessory_recovery
            + total_consumable_cost
        )
        total_recovery = main_recovery + total_accessory_recovery
        net_investment = gross_investment - total_recovery

        historical_daily_base = net_main_investment / divisor_days
        historical_daily_consumable = total_consumable_cost / divisor_days
        historical_daily_total = (
            historical_daily_base
            + historical_daily_consumable
            + accessory_historical_daily
        )
        historical_monthly_cost = historical_daily_total * DAYS_PER_MONTH

        service_monthly_cost = 0.0
        current_period_cost = base_purchase
        if kind == KIND_SERVICE:
            current_period_cost = max(
                0.0,
                safe_float(options.get(CONF_CURRENT_PERIOD_COST), base_purchase),
            )
        if kind == KIND_SERVICE and status == STATUS_ACTIVE:
            period = options.get(CONF_SUB_PERIOD, "1个月")
            months = {"1个月": 1, "3个月": 3, "半年": 6, "1年": 12}.get(period)
            if months:
                service_monthly_cost = current_period_cost / months
            else:
                period_days = max(1, safe_int(options.get("service_period_days"), 30))
                service_monthly_cost = current_period_cost / period_days * DAYS_PER_MONTH

        current_monthly_cost = 0.0
        if status == STATUS_ACTIVE:
            current_monthly_cost = service_monthly_cost + (
                current_consumable_daily * DAYS_PER_MONTH
            )

        service_percent: int | None = None
        service_remain_days: str | int = "未知"
        if kind == KIND_SERVICE and expiration_date:
            period_start = safe_date(options.get("service_period_start"), purchase_date)
            total_service_days = max(1, safe_int(options.get("service_period_days"), (expiration_date - period_start).days))
            remaining_days = max(0, (expiration_date - today).days)
            service_percent = max(
                0, min(100, round(remaining_days / total_service_days * 100))
            )
            service_remain_days = remaining_days

        attrs: dict[str, Any] = {
            "integration_domain": DOMAIN,
            "friendly_name": self._device_name,
            "kind": kind,
            "is_event": kind == KIND_EVENT,
            "category": category,
            "purchase_date": str(purchase_date),
            "expiration_date": str(expiration_date) if expiration_date else "",
            "status": status,
            "stored_status": stored_status,
            "status_label": status_label(status),
            "status_changed_at": options.get(CONF_STATUS_CHANGED_AT, ""),
            "is_terminal": is_terminal_status(status) or status == STATUS_EXPIRED,
            "is_active": status in (STATUS_ACTIVE, STATUS_IDLE),
            "retire_reason": status_label(status)
            if status not in (STATUS_ACTIVE, STATUS_IDLE)
            else "",
            "recovery_amount": round(main_recovery, 2),
            "total_recovery": round(total_recovery, 2),
            "gross_investment": round(gross_investment, 2),
            "net_investment": round(net_investment, 2),
            "main_net_investment": round(net_main_investment, 2),
            "renewal_price": round(
                current_period_cost if kind == KIND_SERVICE else base_purchase, 2
            ),
            "current_period_cost": round(current_period_cost, 2),
            "current_reference_value": round(current_reference_value, 2),
            "total_price": round(main_cash_cost + interest + early_fee, 2),
            "net_price": round(net_main_investment, 2),
            "historical_daily_cost": round(historical_daily_total, 2),
            "historical_monthly_cost": round(historical_monthly_cost, 2),
            "current_monthly_cost": round(current_monthly_cost, 2),
            "current_daily_consumable": round(current_consumable_daily, 4),
            "daily_cost": round(historical_daily_total, 2),
            "daily_base": round(historical_daily_base, 2),
            "daily_consumable": round(historical_daily_consumable, 2),
            "daily_accessory": round(accessory_historical_daily, 2),
            "total_consumable_cost": round(total_consumable_cost, 2),
            "total_accessory_net": round(total_accessory_net, 2),
            "service_percent": service_percent,
            "service_remain_days": service_remain_days,
            "service_monthly_cost": round(service_monthly_cost, 2),
            "consumables_list": processed_consumables,
            "accessories_list": processed_accessories,
            "installment_interest": interest,
            "early_payoff_fee": early_fee,
            "story": options.get(CONF_STORY, ""),
            "location": options.get(CONF_LOCATION, ""),
            "is_wearing": options.get("is_wearing", False),
            "total_saved_value": round(total_saved_value, 2),
        }

        badges: list[dict[str, str]] = []
        if kind == KIND_SERVICE and service_percent is not None and service_percent < 20:
            badges.append(
                {"icon": "mdi:clock-alert", "label": "即将到期", "color": "#E53935"}
            )
        if status == STATUS_IDLE:
            badges.append(
                {"icon": "mdi:archive-clock", "label": "闲置持有", "color": "#9E9E9E"}
            )
        if linked_price_entity and kind == KIND_MEMORIAL:
            badges.append(
                {"icon": "mdi:chart-line", "label": "参考价值联动", "color": "#FFC107"}
            )
        if any(item["is_smart"] for item in processed_consumables):
            badges.append(
                {"icon": "mdi:link-variant", "label": "耗材实体联动", "color": "#2196F3"}
            )

        installment_months = safe_int(data.get(CONF_INSTALLMENT_MONTHS))
        if is_installment and installment_months > 0:
            installment = _installment_state(
                main_cash_cost,
                interest,
                installment_months,
                purchase_date,
                end_date,
                early_payoff,
            )
            attrs.update(
                {
                    "installment_months": installment_months,
                    "months_paid": installment["months_paid"],
                    "outstanding_balance": installment["outstanding_balance"],
                    "is_paid_off": installment["is_paid_off"],
                    "early_payoff": early_payoff,
                }
            )
            if installment["is_paid_off"]:
                badges.append(
                    {"icon": "mdi:check-decagram", "label": "分期已结清", "color": "#4CAF50"}
                )
            elif interest <= 0:
                badges.append(
                    {"icon": "mdi:sale", "label": "免息分期", "color": "#4CAF50"}
                )

        if actual_days >= 3650:
            companion_label = f"十年相伴 · {actual_days}天"
        elif actual_days >= 365:
            companion_label = f"长期相伴 · {actual_days}天"
        elif actual_days >= 100:
            companion_label = f"百日相伴 · {actual_days}天"
        else:
            companion_label = f"已记录 {actual_days}天"
        badges.append(
            {"icon": "mdi:calendar-heart", "label": companion_label, "color": "#C4A484"}
        )
        attrs["badges"] = badges
        return actual_days, attrs

    @property
    def native_value(self) -> int:
        return self._compute()[0]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self._compute()[1]


class ConsumableSensor(SensorEntity):
    """Consumable remaining percentage sensor."""

    _attr_icon = "mdi:filter-outline"
    _attr_native_unit_of_measurement = "%"
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry, item: dict[str, Any]) -> None:
        self._entry = entry
        self._item = item
        self._attr_name = (
            f"{entry.data.get(CONF_DEVICE_NAME, '未知')} 耗材 ({item.get('name', '')})"
        )
        self._attr_unique_id = f"cons_{entry.entry_id}_{item.get('id', '')}"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(identifiers={(DOMAIN, self._entry.entry_id)})

    async def async_added_to_hass(self) -> None:
        linked = self._item.get(CONF_LINKED_ENTITY)
        if linked:
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass, [linked], lambda event: self.async_write_ha_state()
                )
            )
        self.async_on_remove(
            async_track_time_change(
                self.hass,
                lambda now: self.async_write_ha_state(),
                hour=0,
                minute=0,
                second=10,
            )
        )

    @property
    def available(self) -> bool:
        return _consumable_metrics(self.hass, self._item, today_local())[
            "tracking_available"
        ]

    @property
    def native_value(self) -> float | None:
        return _consumable_metrics(self.hass, self._item, today_local())["percent"]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return _consumable_metrics(self.hass, self._item, today_local())


class AccessorySensor(SensorEntity):
    """Accessory lifecycle-day sensor."""

    _attr_icon = "mdi:puzzle-outline"
    _attr_native_unit_of_measurement = "天"
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry, item: dict[str, Any]) -> None:
        self._entry = entry
        self._item = item
        self._attr_name = (
            f"{entry.data.get(CONF_DEVICE_NAME, '未知')} 附属项目 ({item.get('name', '')})"
        )
        self._attr_unique_id = f"acc_{entry.entry_id}_{item.get('id', '')}"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(identifiers={(DOMAIN, self._entry.entry_id)})

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_track_time_change(
                self.hass,
                lambda now: self.async_write_ha_state(),
                hour=0,
                minute=0,
                second=15,
            )
        )

    @property
    def native_value(self) -> int:
        today = today_local()
        purchase = safe_date(self._item.get("purchase_date"), today)
        status = legacy_status(self._item)
        expiration = safe_date(self._item.get(CONF_EXPIRATION_DATE))
        if (
            infer_kind(dict(self._entry.data)) == KIND_SERVICE
            and status == STATUS_ACTIVE
            and expiration
            and expiration < today
        ):
            status = STATUS_EXPIRED
        end = _record_end_date(
            self._item, status, expiration_date=expiration, today=today
        )
        return max(0, (end - purchase).days)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        today = today_local()
        stored_status = legacy_status(self._item)
        expiration = safe_date(self._item.get(CONF_EXPIRATION_DATE))
        status = _effective_status(
            stored_status, infer_kind(dict(self._entry.data)), expiration, today
        )
        return {
            "status": status,
            "stored_status": stored_status,
            "status_label": status_label(status),
            "net_investment": round(
                safe_float(self._item.get("price"))
                + safe_float(self._item.get(CONF_INSTALLMENT_INTEREST))
                + safe_float(self._item.get(CONF_EARLY_PAYOFF_FEE))
                - (
                    safe_float(self._item.get(CONF_RECOVERY_AMOUNT))
                    if status == STATUS_SOLD
                    else 0.0
                ),
                2,
            ),
        }
