"""Opt-in local expiry reminders, deduplicated across reload and restart."""

from datetime import datetime

from homeassistant.components import persistent_notification
from homeassistant.core import callback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util import dt as dt_util

from .const import DOMAIN, KIND_SERVICE, STATUS_CANCELED
from .helpers import infer_kind, legacy_status, safe_date, today_local


async def async_check_expiry(hass, entry):
    """Send the nearest due threshold once; persist only after local delivery."""
    from . import _entry_lock

    async with _entry_lock(hass, entry.entry_id):
        latest = hass.config_entries.async_get_entry(entry.entry_id)
        if latest is None or not latest.options.get("expiry_reminders", False):
            return
        if infer_kind(dict(latest.data)) != KIND_SERVICE or legacy_status(dict(latest.options)) == STATUS_CANCELED:
            return
        expiration = safe_date(latest.options.get("expiration_date"))
        if expiration is None:
            return
        remaining = (expiration - today_local()).days
        if remaining < 0 or remaining > 7:
            return
        threshold = 0 if remaining == 0 else 3 if remaining <= 3 else 7
        options = dict(latest.options)
        sent = options.get("expiry_reminder_sent", {})
        if not isinstance(sent, dict) or sent.get("expiration") != str(expiration):
            sent = {"expiration": str(expiration), "thresholds": []}
        thresholds = sent.get("thresholds", [])
        if not isinstance(thresholds, list):
            thresholds = []
        if threshold in thresholds:
            return
        name = latest.data.get("device_name", "订阅服务")
        message = f"{name} 今天到期，请确认是否续订。" if remaining == 0 else f"{name} 将于 {expiration} 到期，剩余 {remaining} 天。请确认是否续订。"
        persistent_notification.async_create(hass, message, title="HomeAsset Companion · 到期提醒", notification_id=f"{DOMAIN}_expiry_{entry.entry_id}")
        options["expiry_reminder_sent"] = {"expiration": str(expiration), "thresholds": thresholds + [threshold]}
        hass.config_entries.async_update_entry(latest, options=options)


def async_setup_reminders(hass, entry):
    """Register a local 09:00 check with cancellable catch-up on startup."""
    if infer_kind(dict(entry.data)) != KIND_SERVICE or not entry.options.get("expiry_reminders", False):
        return
    tasks = set()

    @callback
    def check(_now: datetime | None = None):
        task = hass.async_create_task(async_check_expiry(hass, entry))
        tasks.add(task)
        task.add_done_callback(tasks.discard)

    @callback
    def cancel():
        for task in tasks:
            task.cancel()
        tasks.clear()

    entry.async_on_unload(async_track_time_change(hass, check, hour=9, minute=0, second=0))
    entry.async_on_unload(cancel)
    if dt_util.now().hour >= 9:
        check()
