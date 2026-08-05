"""Calendar platform for HomeAsset Companion."""

from __future__ import annotations

from datetime import date, datetime, timedelta
import logging

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_ACCESSORIES_LIST,
    CONF_CATEGORY,
    CONF_DEVICE_NAME,
    CONF_EXPIRATION_DATE,
    CONF_PURCHASE_DATE,
    CONF_SYNC_TO_CALENDAR,
    DOMAIN,
    KIND_EVENT,
    KIND_MEMORIAL,
    KIND_SERVICE,
)
from .helpers import infer_kind, is_terminal_status, legacy_status, safe_date, today_local

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up one optional calendar entity per record."""
    if entry.options.get(CONF_SYNC_TO_CALENDAR, True):
        async_add_entities([DeviceCompanionCalendar(entry)])
        return

    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        "calendar", DOMAIN, f"calendar_{entry.entry_id}"
    )
    if entity_id:
        registry.async_remove(entity_id)
        _LOGGER.debug("Removed disabled HomeAsset calendar entity %s", entity_id)


class DeviceCompanionCalendar(CalendarEntity):
    """Expose anniversaries and expiry dates as calendar events."""

    _attr_icon = "mdi:calendar-heart"

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._device_name = entry.data.get(CONF_DEVICE_NAME, "未知")
        self._category = entry.data.get(CONF_CATEGORY, "其他类别")
        self._kind = infer_kind(dict(entry.data))
        self._attr_name = f"{self._device_name} 陪伴日历"
        self._attr_unique_id = f"calendar_{entry.entry_id}"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=self._device_name,
            manufacturer="HomeAsset Companion",
            model=self._category,
        )

    def _is_record_active(self) -> bool:
        status = legacy_status(dict(self._entry.options))
        return not is_terminal_status(status)

    @staticmethod
    def _in_window(event_date: date, view_start: date, view_end: date) -> bool:
        """Calendar upper bound is exclusive."""
        return view_start <= event_date < view_end

    def _build_events(self, view_start: date, view_end: date) -> list[CalendarEvent]:
        if not self._entry.options.get(CONF_SYNC_TO_CALENDAR, True):
            return []

        events: list[CalendarEvent] = []
        purchase_date = safe_date(self._entry.data.get(CONF_PURCHASE_DATE))
        custom_name = str(self._entry.options.get("anniversary_name", "")).strip()
        record_active = self._is_record_active()

        if purchase_date and record_active:
            for year in range(view_start.year, view_end.year + 1):
                try:
                    anniversary = purchase_date.replace(year=year)
                except ValueError:
                    anniversary = date(year, 3, 1)
                if anniversary <= purchase_date or not self._in_window(
                    anniversary, view_start, view_end
                ):
                    continue

                years = year - purchase_date.year
                if self._kind == KIND_EVENT:
                    name = custom_name or self._device_name
                    summary = f"✨ {name}（{years}周年）"
                    description = f"{name}已经过去 {years} 年。"
                elif self._kind == KIND_MEMORIAL and custom_name:
                    summary = f"💍 {custom_name}（{years}周年）"
                    description = f"今天是{custom_name}，已走过 {years} 年。"
                else:
                    prefix = "🚗" if self._category == "交通出行" else "🎂"
                    summary = f"{prefix} {self._device_name}（{years}周年）"
                    description = f"自 {purchase_date} 起，已记录 {years} 年。"

                events.append(
                    CalendarEvent(
                        start=anniversary,
                        end=anniversary + timedelta(days=1),
                        summary=summary,
                        description=description,
                    )
                )

        if self._kind == KIND_SERVICE and record_active:
            expiration = safe_date(self._entry.options.get(CONF_EXPIRATION_DATE))
            if expiration and self._in_window(expiration, view_start, view_end):
                events.append(
                    CalendarEvent(
                        start=expiration,
                        end=expiration + timedelta(days=1),
                        summary=f"🔄 {self._device_name} 订阅到期",
                        description="请确认是否续订、取消或调整下一周期费用。",
                    )
                )

        for accessory in self._entry.options.get(CONF_ACCESSORIES_LIST, []):
            if is_terminal_status(legacy_status(accessory)):
                continue
            expiration = safe_date(accessory.get(CONF_EXPIRATION_DATE))
            if expiration and self._in_window(expiration, view_start, view_end):
                name = accessory.get("name", "附加项目")
                events.append(
                    CalendarEvent(
                        start=expiration,
                        end=expiration + timedelta(days=1),
                        summary=f"⏳ {self._device_name} · {name} 到期",
                        description="此附加权益或服务在今天到期。",
                    )
                )

        return sorted(events, key=lambda event: (event.start, event.summary))

    @property
    def event(self) -> CalendarEvent | None:
        today = today_local()
        events = self._build_events(today, today + timedelta(days=731))
        return events[0] if events else None

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        return self._build_events(start_date.date(), end_date.date())
