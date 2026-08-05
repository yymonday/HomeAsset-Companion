"""The HomeAsset Companion integration."""

from __future__ import annotations

import asyncio
from copy import deepcopy
import logging
from pathlib import Path
import uuid

from aiohttp import web
import voluptuous as vol

from homeassistant.components.http import HomeAssistantView, StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_ACCESSORIES_LIST,
    CONF_AUTO_RECORD_REPLACEMENT,
    CONF_CONSUMABLES_LIST,
    CONF_EXPIRATION_DATE,
    CONF_RECOVERY_AMOUNT,
    CONF_SCHEMA_VERSION,
    CONF_STATUS,
    CONF_STATUS_CHANGED_AT,
    CONF_SUB_PERIOD,
    CONF_TOTAL_PRICE,
    DATA_LOCKS,
    DOMAIN,
    INTEGRATION_VERSION,
    KIND_SERVICE,
    STATUS_ACTIVE,
    STATUS_LABELS,
)
from .helpers import (
    add_months_to_date,
    infer_kind,
    legacy_status,
    normalize_status_record,
    safe_date,
    safe_float,
    status_label,
    today_local,
    allowed_statuses,
)

_LOGGER = logging.getLogger(__name__)
PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.CALENDAR]
FRONTEND_DIR = Path(__file__).parent / "frontend"
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
ALLOWED_STATUS_VALUES = list(STATUS_LABELS)

SERVICE_RENEW = "renew_service"
SERVICE_REPLACE = "replace_consumable"
SERVICE_SET_LIFECYCLE = "set_lifecycle"
SERVICE_UPDATE_IMAGE = "update_item_image"
SERVICE_QUICK_ACTION = "quick_action"  # Backward compatibility for V153 cards.

TARGET_SCHEMA = vol.Schema({vol.Required(ATTR_ENTITY_ID): cv.entity_id})
RENEW_SCHEMA = TARGET_SCHEMA.extend(
    {
        vol.Optional("cost"): vol.Coerce(float),
        vol.Optional("months"): vol.All(vol.Coerce(int), vol.Range(min=1, max=120)),
        vol.Optional(CONF_EXPIRATION_DATE): cv.date,
    }
)
REPLACE_SCHEMA = TARGET_SCHEMA.extend(
    {
        vol.Required("cons_id"): cv.string,
        vol.Optional("cost"): vol.Coerce(float),
    }
)
LIFECYCLE_SCHEMA = TARGET_SCHEMA.extend(
    {
        vol.Required(CONF_STATUS): vol.In(ALLOWED_STATUS_VALUES),
        vol.Optional(CONF_RECOVERY_AMOUNT): vol.Coerce(float),
    }
)
IMAGE_SCHEMA = TARGET_SCHEMA.extend(
    {
        vol.Required("item_id"): cv.string,
        vol.Required("image_url"): vol.All(cv.string, vol.Length(min=1, max=1024)),
    }
)
QUICK_ACTION_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.entity_id,
        vol.Required("action"): cv.string,
        vol.Optional("cons_id"): cv.string,
        vol.Optional("cost"): vol.Coerce(float),
        vol.Optional("image_url"): cv.string,
        vol.Optional("status"): cv.string,
        vol.Optional(CONF_RECOVERY_AMOUNT, default=0.0): vol.Coerce(float),
    }
)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up shared HTTP routes, frontend assets, and service actions."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault(DATA_LOCKS, {})

    upload_dir = Path(hass.config.path("www", DOMAIN))
    await hass.async_add_executor_job(upload_dir.mkdir, parents=True, exist_ok=True)

    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                "/device_companion/device-companion-card.js",
                str(FRONTEND_DIR / "device-companion-card.js"),
                True,
            ),
            StaticPathConfig(
                "/device_companion/device-companion-summary.js",
                str(FRONTEND_DIR / "device-companion-summary.js"),
                True,
            ),
        ]
    )
    hass.http.register_view(DeviceCompanionUploadView(hass, upload_dir))
    _register_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up HomeAsset Companion from a config entry."""
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload an entry after its data or options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.get(DOMAIN, {}).get(DATA_LOCKS, {}).pop(entry.entry_id, None)
    return unload_ok


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate legacy V1 entries to the V2 lifecycle schema."""
    if entry.version >= 2:
        return True

    _LOGGER.info("Migrating HomeAsset Companion entry %s to schema V2", entry.entry_id)
    data = deepcopy(dict(entry.data))
    options = deepcopy(dict(entry.options))

    data[CONF_KIND] = infer_kind(data)
    options[CONF_SCHEMA_VERSION] = 2
    options.setdefault("sync_to_calendar", True)
    if data[CONF_KIND] == KIND_SERVICE and options.get(CONF_EXPIRATION_DATE):
        expiration = safe_date(options.get(CONF_EXPIRATION_DATE))
        months = {"1个月": 1, "3个月": 3, "半年": 6, "1年": 12}.get(options.get(CONF_SUB_PERIOD))
        if expiration:
            period_start = add_months_to_date(expiration, -months) if months else safe_date(data.get("purchase_date"), expiration)
            options.setdefault("service_period_start", str(period_start))
            options.setdefault("service_period_days", max(1, (expiration - period_start).days))

    main_status = legacy_status(options)
    options = normalize_status_record(
        options,
        main_status,
        changed_at=safe_date(
            options.get(CONF_STATUS_CHANGED_AT) or options.get("retirement_date")
        ),
        recovery_amount=safe_float(options.get(CONF_RECOVERY_AMOUNT)),
    )

    migrated_consumables: list[dict] = []
    for consumable in options.get(CONF_CONSUMABLES_LIST, []):
        item = deepcopy(consumable)
        item.setdefault(CONF_AUTO_RECORD_REPLACEMENT, False)
        item.setdefault("last_detected_reset", "")
        migrated_consumables.append(item)
    options[CONF_CONSUMABLES_LIST] = migrated_consumables

    migrated_accessories: list[dict] = []
    for accessory in options.get(CONF_ACCESSORIES_LIST, []):
        item = deepcopy(accessory)
        item_status = legacy_status(item)
        migrated_accessories.append(
            normalize_status_record(
                item,
                item_status,
                changed_at=safe_date(
                    item.get(CONF_STATUS_CHANGED_AT) or item.get("retirement_date")
                ),
                recovery_amount=safe_float(item.get(CONF_RECOVERY_AMOUNT)),
            )
        )
    options[CONF_ACCESSORIES_LIST] = migrated_accessories

    hass.config_entries.async_update_entry(
        entry,
        data=data,
        options=options,
        version=2,
        minor_version=0,
    )
    return True


def _register_services(hass: HomeAssistant) -> None:
    """Register integration service actions once."""
    if hass.services.has_service(DOMAIN, SERVICE_RENEW):
        return

    async def handle_renew(call: ServiceCall) -> None:
        await _handle_renew_service(hass, call)

    async def handle_replace(call: ServiceCall) -> None:
        await _handle_replace_consumable(hass, call)

    async def handle_lifecycle(call: ServiceCall) -> None:
        await _handle_set_lifecycle(hass, call)

    async def handle_image(call: ServiceCall) -> None:
        await _handle_update_item_image(hass, call)

    async def handle_legacy(call: ServiceCall) -> None:
        await _handle_legacy_quick_action(hass, call)

    hass.services.async_register(DOMAIN, SERVICE_RENEW, handle_renew, schema=RENEW_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_REPLACE, handle_replace, schema=REPLACE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SET_LIFECYCLE, handle_lifecycle, schema=LIFECYCLE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_UPDATE_IMAGE, handle_image, schema=IMAGE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_QUICK_ACTION, handle_legacy, schema=QUICK_ACTION_SCHEMA)


async def _resolve_target_entry(
    hass: HomeAssistant, entity_id: str
) -> ConfigEntry:
    """Resolve and validate a HomeAsset Companion entity target."""
    registry = er.async_get(hass)
    entity = registry.async_get(entity_id)
    if entity is None or entity.config_entry_id is None:
        raise ServiceValidationError(f"找不到实体或配置条目：{entity_id}")

    entry = hass.config_entries.async_get_entry(entity.config_entry_id)
    if entry is None or entry.domain != DOMAIN:
        raise ServiceValidationError(f"实体不属于 HomeAsset Companion：{entity_id}")
    return entry


def _entry_lock(hass: HomeAssistant, entry_id: str) -> asyncio.Lock:
    """Return a per-entry write lock."""
    locks: dict[str, asyncio.Lock] = hass.data[DOMAIN][DATA_LOCKS]
    return locks.setdefault(entry_id, asyncio.Lock())


async def _update_options(
    hass: HomeAssistant,
    entry: ConfigEntry,
    mutator,
) -> None:
    """Safely mutate a fresh options snapshot under a per-entry lock."""
    async with _entry_lock(hass, entry.entry_id):
        latest = hass.config_entries.async_get_entry(entry.entry_id)
        if latest is None:
            raise ServiceValidationError("目标配置条目已经不存在")
        options = deepcopy(dict(latest.options))
        changed = mutator(options)
        if changed is False:
            return
        hass.config_entries.async_update_entry(latest, options=options)


async def _handle_renew_service(hass: HomeAssistant, call: ServiceCall) -> None:
    entry = await _resolve_target_entry(hass, call.data[ATTR_ENTITY_ID])
    if infer_kind(dict(entry.data)) != KIND_SERVICE:
        raise ServiceValidationError("只有虚拟服务记录可以续订")

    def mutate(options: dict) -> None:
        today = today_local()
        price = max(
            0.0,
            safe_float(call.data.get("cost"), safe_float(entry.data.get(CONF_TOTAL_PRICE))),
        )
        options["accumulated_cost"] = safe_float(options.get("accumulated_cost")) + price

        explicit_expiration = safe_date(call.data.get(CONF_EXPIRATION_DATE))
        if explicit_expiration:
            new_expiration = explicit_expiration
        else:
            months = call.data.get("months")
            if months is None:
                months = {
                    "1个月": 1,
                    "3个月": 3,
                    "半年": 6,
                    "1年": 12,
                }.get(options.get(CONF_SUB_PERIOD, "1个月"), 1)
            current_expiration = safe_date(options.get(CONF_EXPIRATION_DATE), today)
            base_date = current_expiration if current_expiration and current_expiration > today else today
            new_expiration = add_months_to_date(base_date, int(months))

        options[CONF_EXPIRATION_DATE] = str(new_expiration)
        options["service_period_start"] = str(base_date if not explicit_expiration else today)
        options["service_period_days"] = max(1, (new_expiration - (base_date if not explicit_expiration else today)).days)
        options.update(normalize_status_record(options, STATUS_ACTIVE, changed_at=today))

    await _update_options(hass, entry, mutate)


async def _handle_replace_consumable(hass: HomeAssistant, call: ServiceCall) -> None:
    entry = await _resolve_target_entry(hass, call.data[ATTR_ENTITY_ID])
    cons_id = call.data["cons_id"]
    requested_cost = max(0.0, safe_float(call.data.get("cost")))

    def mutate(options: dict) -> None:
        consumables = deepcopy(options.get(CONF_CONSUMABLES_LIST, []))
        target = next((item for item in consumables if item.get("id") == cons_id), None)
        if target is None:
            raise ServiceValidationError(f"找不到耗材：{cons_id}")
        cost = requested_cost if "cost" in call.data else safe_float(target.get("price"))
        target["accumulated_cost"] = safe_float(target.get("accumulated_cost")) + cost
        target["last_replace"] = str(today_local())
        target["last_detected_reset"] = str(today_local())
        options[CONF_CONSUMABLES_LIST] = consumables

    await _update_options(hass, entry, mutate)


async def _handle_set_lifecycle(hass: HomeAssistant, call: ServiceCall) -> None:
    entry = await _resolve_target_entry(hass, call.data[ATTR_ENTITY_ID])
    status = call.data[CONF_STATUS]
    kind = infer_kind(dict(entry.data))
    if status not in allowed_statuses(kind):
        raise ServiceValidationError(f"{status_label(status)} 不适用于当前记录类型")
    recovery = max(0.0, safe_float(call.data.get(CONF_RECOVERY_AMOUNT)))

    def mutate(options: dict) -> None:
        options.update(
            normalize_status_record(
                options,
                status,
                changed_at=today_local(),
                recovery_amount=recovery,
            )
        )

    await _update_options(hass, entry, mutate)


async def _handle_update_item_image(hass: HomeAssistant, call: ServiceCall) -> None:
    entry = await _resolve_target_entry(hass, call.data[ATTR_ENTITY_ID])
    item_id = call.data["item_id"]
    image_url = call.data["image_url"].strip()
    if not image_url.startswith(("/local/", "http://", "https://")):
        raise ServiceValidationError("图片地址必须是 /local/、http:// 或 https://")

    def mutate(options: dict) -> None:
        for list_key in (CONF_CONSUMABLES_LIST, CONF_ACCESSORIES_LIST):
            items = deepcopy(options.get(list_key, []))
            for item in items:
                if item.get("id") == item_id:
                    item["image"] = image_url
                    options[list_key] = items
                    return
        raise ServiceValidationError(f"找不到耗材、配件或权益：{item_id}")

    await _update_options(hass, entry, mutate)


async def _handle_legacy_quick_action(hass: HomeAssistant, call: ServiceCall) -> None:
    """Translate V153 quick_action calls without leaking unrelated fields."""
    action = call.data["action"]
    entity_id = call.data[ATTR_ENTITY_ID]

    if action == "renew_service":
        payload: dict[str, object] = {ATTR_ENTITY_ID: entity_id}
        if "cost" in call.data:
            payload["cost"] = call.data["cost"]
        service = SERVICE_RENEW
    elif action == "replace_consumable":
        payload = {ATTR_ENTITY_ID: entity_id, "cons_id": call.data.get("cons_id", "")}
        if "cost" in call.data:
            payload["cost"] = call.data["cost"]
        service = SERVICE_REPLACE
    elif action == "update_image":
        payload = {
            ATTR_ENTITY_ID: entity_id,
            "item_id": call.data.get("cons_id", ""),
            "image_url": call.data.get("image_url", ""),
        }
        service = SERVICE_UPDATE_IMAGE
    elif action == "set_lifecycle":
        payload = {
            ATTR_ENTITY_ID: entity_id,
            CONF_STATUS: call.data.get(CONF_STATUS, STATUS_ACTIVE),
        }
        if CONF_RECOVERY_AMOUNT in call.data:
            payload[CONF_RECOVERY_AMOUNT] = call.data[CONF_RECOVERY_AMOUNT]
        service = SERVICE_SET_LIFECYCLE
    else:
        raise ServiceValidationError(f"不支持的旧版 quick_action：{action}")

    await hass.services.async_call(DOMAIN, service, payload, blocking=True)


class DeviceCompanionUploadView(HomeAssistantView):
    """Authenticated image upload endpoint."""

    url = "/api/device_companion/upload"
    name = "api:device_companion:upload"
    requires_auth = True

    def __init__(self, hass: HomeAssistant, upload_dir: Path) -> None:
        self._hass = hass
        self._upload_dir = upload_dir

    async def post(self, request: web.Request) -> web.Response:
        """Validate and store one supported image."""
        try:
            data = await request.post()
            file_field = data.get("file")
            if file_field is None or not getattr(file_field, "file", None):
                return web.json_response({"error": "missing_file"}, status=400)

            payload = await self._hass.async_add_executor_job(
                file_field.file.read, MAX_UPLOAD_BYTES + 1
            )
            if not payload:
                return web.json_response({"error": "empty_file"}, status=400)
            if len(payload) > MAX_UPLOAD_BYTES:
                return web.json_response({"error": "file_too_large"}, status=413)

            extension = _detect_image_extension(payload)
            if extension is None:
                return web.json_response({"error": "unsupported_image"}, status=415)

            filename = f"dc_img_{uuid.uuid4().hex}{extension}"
            file_path = self._upload_dir / filename
            await self._hass.async_add_executor_job(file_path.write_bytes, payload)
            return web.json_response(
                {
                    "success": True,
                    "url": f"/local/{DOMAIN}/{filename}",
                    "version": INTEGRATION_VERSION,
                }
            )
        except Exception:  # noqa: BLE001 - HTTP boundary must not expose internals.
            _LOGGER.exception("Unable to upload HomeAsset Companion image")
            return web.json_response({"error": "upload_failed"}, status=500)


def _detect_image_extension(payload: bytes) -> str | None:
    """Return an extension from trusted file signatures."""
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if payload.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if len(payload) >= 12 and payload[:4] == b"RIFF" and payload[8:12] == b"WEBP":
        return ".webp"
    return None
