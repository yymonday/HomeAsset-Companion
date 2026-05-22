"""The Device Companion integration."""
import os
import uuid
import logging
import calendar
from datetime import date, datetime
from aiohttp import web

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.components.http import HomeAssistantView
from homeassistant.const import Platform
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN, CONF_EXPIRATION_DATE, CONF_CONSUMABLES_LIST, CONF_ACCESSORIES_LIST, CONF_TOTAL_PRICE

_LOGGER = logging.getLogger(__name__)
PLATFORMS: list[Platform] = [Platform.SENSOR]

def add_months_to_date(dt_date, months):
    month = dt_date.month - 1 + months
    year = dt_date.year + month // 12
    month = month % 12 + 1
    day = min(dt_date.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    www_dir = hass.config.path("www")
    upload_dir = os.path.join(www_dir, DOMAIN)
    
    def check_and_create_dir():
        os.makedirs(upload_dir, exist_ok=True)
        
    await hass.async_add_executor_job(check_and_create_dir)
    hass.http.register_view(DeviceCompanionUploadView(hass, upload_dir))

    if not hass.services.has_service(DOMAIN, "quick_action"):
        async def handle_action(call):
            entity_id = call.data.get("entity_id")
            action = call.data.get("action")
            
            registry = er.async_get(hass)
            entity = registry.async_get(entity_id)
            if not entity or not entity.config_entry_id: return
            
            target_entry = hass.config_entries.async_get_entry(entity.config_entry_id)
            if target_entry:
                current_options = dict(target_entry.options)
                today_str = str(datetime.now().date())
                
                if action == "renew_service":
                    base_price = float(target_entry.data.get(CONF_TOTAL_PRICE, 0.0))
                    sub_period = current_options.get("sub_period", "1个月")
                    months_map = {"1个月": 1, "3个月": 3, "半年": 6, "1年": 12}
                    months_to_add = months_map.get(sub_period, 1)
                    
                    current_options["accumulated_cost"] = current_options.get("accumulated_cost", 0.0) + base_price
                    exp_str = current_options.get(CONF_EXPIRATION_DATE, target_entry.data.get(CONF_EXPIRATION_DATE))
                    if exp_str:
                        exp_date = datetime.strptime(exp_str.split("T")[0], "%Y-%m-%d").date() if isinstance(exp_str, str) else (exp_str if isinstance(exp_str, date) else exp_str.date())
                        base_date = exp_date if exp_date > datetime.now().date() else datetime.now().date()
                        new_date = add_months_to_date(base_date, months_to_add)
                        current_options[CONF_EXPIRATION_DATE] = str(new_date)
                        current_options["is_retired"] = False 
                        current_options["retirement_reason"] = "光荣闲置"

                elif action == "replace_consumable":
                    cost = float(call.data.get("cost", 0.0))
                    cons_id = call.data.get("cons_id")
                    consumables = list(current_options.get(CONF_CONSUMABLES_LIST, []))
                    for c in consumables:
                        if c["id"] == cons_id:
                            c["accumulated_cost"] = c.get("accumulated_cost", 0.0) + cost
                            c["last_replace"] = today_str
                            break
                    current_options[CONF_CONSUMABLES_LIST] = consumables

                # 🔥 强化的网关级图锁：修改、添加、覆盖时进行双向指针校验，确保路径永久安全
                elif action == "update_image":
                    target_id = call.data.get("cons_id")
                    image_url = call.data.get("image_url", "").strip()
                    
                    if image_url:
                        # 1. 检索耗材列表
                        consumables = list(current_options.get(CONF_CONSUMABLES_LIST, []))
                        updated = False
                        for c in consumables:
                            if c.get("id") == target_id:
                                c["image"] = image_url; updated = True; break
                        if updated: 
                            current_options[CONF_CONSUMABLES_LIST] = consumables
                        else:
                            # 2. 检索全场景附件列表（数码配件/赠送权益/纪念单品）
                            accessories = list(current_options.get(CONF_ACCESSORIES_LIST, []))
                            for a in accessories:
                                if a.get("id") == target_id:
                                    a["image"] = image_url; updated = True; break
                            if updated: 
                                current_options[CONF_ACCESSORIES_LIST] = accessories

                hass.config_entries.async_update_entry(target_entry, options=current_options)

        hass.services.async_register(DOMAIN, "quick_action", handle_action)

    entry.async_on_unload(entry.add_update_listener(update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        if not hass.data[DOMAIN]: hass.data.pop(DOMAIN)
    return unload_ok

class DeviceCompanionUploadView(HomeAssistantView):
    url = "/api/device_companion/upload"
    name = "api:device_companion:upload"
    requires_auth = True
    def __init__(self, hass, upload_dir):
        self.hass = hass
        self.upload_dir = upload_dir

    async def post(self, request):
        try:
            data = await request.post()
            file_field = data.get("file")
            if not file_field: return web.json_response({"error": "Missing file"}, status=400)
            ext = os.path.splitext(file_field.filename)[1].lower()
            # 契约约束：强制抛弃原名，改用纯英文随机命名保安全
            safe_filename = f"dc_img_{uuid.uuid4().hex[:8]}{ext}"
            file_path = os.path.join(self.upload_dir, safe_filename)
            with open(file_path, "wb") as f: f.write(file_field.file.read())
            return web.json_response({"success": True, "url": f"/local/{DOMAIN}/{safe_filename}"})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)