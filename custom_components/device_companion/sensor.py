"""Sensor platform for Device Companion."""
import logging
from datetime import datetime, date
from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_track_state_change_event

from .const import *

_LOGGER = logging.getLogger(__name__)

def safe_float(val, default=0.0):
    try: return float(val)
    except (ValueError, TypeError): return default

def safe_date(val, default_date=None):
    if not val: return default_date or date.today()
    if isinstance(val, date) and not isinstance(val, datetime): return val
    if isinstance(val, datetime): return val.date()
    try: return datetime.strptime(str(val).split("T")[0], "%Y-%m-%d").date()
    except: return default_date or date.today()

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    entities = [DeviceCompanionSensor(entry)]
    for cons in entry.options.get(CONF_CONSUMABLES_LIST, []): entities.append(ConsumableSensor(entry, cons))
    for acc in entry.options.get(CONF_ACCESSORIES_LIST, []): entities.append(AccessorySensor(entry, acc))
    async_add_entities(entities)

class DeviceCompanionSensor(SensorEntity):
    _attr_icon = "mdi:calendar-heart"
    _attr_should_poll = True

    def __init__(self, entry: ConfigEntry):
        self._entry = entry
        self._attr_name = f"{entry.data.get(CONF_DEVICE_NAME, '未知')} 陪伴"
        self._attr_unique_id = f"companion_{entry.entry_id}"
        self._device_name = entry.data.get(CONF_DEVICE_NAME, "未知")
        self._unsub_listeners = []
        
    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(identifiers={(DOMAIN, self._entry.entry_id)}, name=self._device_name, manufacturer="Device Companion", model=self._entry.data.get(CONF_CATEGORY, "未分类"))

    @property
    def entity_picture(self):
        img = self._entry.data.get(CONF_DEVICE_IMAGE, "")
        return img if img and img.strip() != "" else None

    async def async_added_to_hass(self):
        for cons in self._entry.options.get(CONF_CONSUMABLES_LIST, []):
            linked_id = cons.get(CONF_LINKED_ENTITY, "")
            if linked_id:
                cons_id, price = cons.get("id"), safe_float(cons.get("price"))
                @callback
                def _async_state_changed(event):
                    ns, os = event.data.get("new_state"), event.data.get("old_state")
                    if not ns or not os: return
                    trigger = False
                    try:
                        if safe_float(os.state) < 20.0 and safe_float(ns.state) >= 90.0: trigger = True
                    except:
                        if os.state.lower() == "on" and ns.state.lower() == "off": trigger = True
                    if trigger: 
                        self.hass.async_create_task(self.hass.services.async_call(DOMAIN, "quick_action", {"entity_id": self.entity_id, "action": "replace_consumable", "cons_id": cons_id, "cost": price}))
                self._unsub_listeners.append(async_track_state_change_event(self.hass, [linked_id], _async_state_changed))

    async def async_will_remove_from_hass(self):
        for unsub in self._unsub_listeners: unsub()

    @property
    def _computed_state(self):
        today = date.today()
        category = self._entry.data.get(CONF_CATEGORY, "其他类别")
        purchase_date = safe_date(self._entry.data.get(CONF_PURCHASE_DATE), today)
        exp_str = self._entry.options.get(CONF_EXPIRATION_DATE, self._entry.data.get(CONF_EXPIRATION_DATE))
        exp_date = safe_date(exp_str) if exp_str else None
        
        is_inst = self._entry.data.get(CONF_IS_INSTALLMENT, False)
        early_payoff = self._entry.options.get(CONF_EARLY_PAYOFF, False)
        is_retired = self._entry.options.get("is_retired", False)
        retire_reason = self._entry.options.get("retirement_reason", "光荣闲置")
        
        # 🔥 让后台认识新的占位符：带有“正常”或“光荣闲置”的主体，都不会停止时间流逝！
        if category == "虚拟服务" and exp_date: end_date = exp_date if today > exp_date else today
        elif is_retired and retire_reason not in ["光荣闲置", "✨ 正常服役", "✨ 正常陪伴/佩戴中", "✨ 正常生效"]: 
            end_date = safe_date(self._entry.options.get("retirement_date"), today)
        else: end_date = today

        days = max(1, (end_date - purchase_date).days)
        actual_days = max(0, (end_date - purchase_date).days)
        
        recovery_amount = safe_float(self._entry.options.get("recovery_amount")) if (is_retired and retire_reason == "二手回血") else 0.0
        base_price = safe_float(self._entry.data.get(CONF_TOTAL_PRICE)) + safe_float(self._entry.options.get("accumulated_cost"))
        interest = safe_float(self._entry.data.get(CONF_INSTALLMENT_INTEREST)) if is_inst else 0.0
        early_payoff_fee = safe_float(self._entry.options.get(CONF_EARLY_PAYOFF_FEE)) if (is_inst and early_payoff) else 0.0
        
        linked_price_entity = self._entry.options.get(CONF_LINKED_PRICE_ENTITY, "")
        dynamic_price = base_price
        if category == "纪念珍藏" and linked_price_entity:
            ha_price_state = self.hass.states.get(linked_price_entity)
            if ha_price_state: dynamic_price = safe_float(ha_price_state.state, base_price) * base_price

        net_main_price = dynamic_price + interest + early_payoff_fee - recovery_amount
        daily_base = round(net_main_price / days, 2)

        total_consumable_cost = 0.0
        processed_consumables = []
        for cons in self._entry.options.get(CONF_CONSUMABLES_LIST, []):
            acc_cost = safe_float(cons.get("accumulated_cost"))
            if acc_cost <= 0: acc_cost = safe_float(cons.get("price"))
            total_consumable_cost += acc_cost
            linked_id = cons.get(CONF_LINKED_ENTITY, "")
            is_smart = bool(linked_id)
            cons_price = safe_float(cons.get("price"))
            
            if is_smart:
                ha_state = self.hass.states.get(linked_id)
                if ha_state:
                    state_val = ha_state.state.lower()
                    if state_val == "on": percent, remain = 0.0, "已耗尽"
                    elif state_val == "off": percent, remain = 100.0, "良好"
                    else: percent, remain = max(0.0, min(100.0, safe_float(state_val, 100.0))), "智能"
                else: percent, remain = 100.0, "离线"
                last_rep_date = safe_date(cons.get("last_replace"), today)
                days_passed = max(1, (today - last_rep_date).days)
                
                if ha_state and ha_state.state.lower() not in ["on", "off"]:
                    used_percent = max(0.0, 100.0 - percent)
                    consumed_value = cons_price * (used_percent / 100.0)
                    theoretical_daily = round(consumed_value / days_passed, 2)
                else: theoretical_daily = round(cons_price / days_passed, 2)
            else:
                last_rep_date = safe_date(cons.get("last_replace"), today)
                days_passed = max(1, (today - last_rep_date).days)
                cycle_val = max(1, int(safe_float(cons.get("cycle", 1))))
                remain = str(max(0, cycle_val - days_passed))
                percent = max(0, min(100, round((max(0, cycle_val - days_passed) / cycle_val) * 100)))
                theoretical_daily = round(cons_price / cycle_val, 2)

            processed_consumables.append({ "id": cons.get("id", ""), "name": cons.get("name", "耗材"), "price": cons_price, "image": cons.get("image", ""), "remain": remain, "percent": percent, "daily_cost": theoretical_daily, "is_smart": is_smart })

        total_acc_daily = 0.0
        total_acc_net = 0.0
        total_saved_value = 0.0
        processed_accessories = []
        for acc in self._entry.options.get(CONF_ACCESSORIES_LIST, []):
            acc_buy_str = acc.get("purchase_date", str(today))
            acc_buy = safe_date(acc_buy_str, today)
            
            acc_exp_str = acc.get("expiration_date", "")
            if acc_exp_str:
                acc_end = safe_date(acc_exp_str, today)
                if acc.get("is_retired"): acc_end = min(acc_end, safe_date(acc.get("retirement_date"), today))
            else:
                acc_end = safe_date(acc.get("retirement_date"), today) if acc.get("is_retired") else today
                
            acc_days = max(1, (acc_end - acc_buy).days)
            acc_is_inst = acc.get("is_installment", False)
            acc_inst_months = int(safe_float(acc.get("installment_months", 0)))
            acc_early = acc.get("early_payoff", False)
            acc_interest = safe_float(acc.get("installment_interest"))
            acc_early_fee = safe_float(acc.get("early_payoff_fee")) if acc_early else 0.0
            acc_recovery = safe_float(acc.get("recovery_amount")) if acc.get("is_retired") and acc.get("retirement_reason") == "二手回血" else 0.0
            
            acc_price = safe_float(acc.get("price"))
            
            if category == "虚拟服务":
                total_saved_value += acc_price
                acc_net = acc_price
                acc_daily = 0.0
            else:
                acc_net = acc_price + acc_interest + acc_early_fee - acc_recovery
                acc_daily = round(acc_net / acc_days, 2)
                total_acc_daily += acc_daily
                total_acc_net += acc_net
            
            acc_months_paid, acc_outstanding, acc_paid_off = 0, 0.0, False
            if acc_is_inst and acc_inst_months > 0:
                calc_date = datetime.combine(acc_end, datetime.min.time())
                months_passed = (calc_date.year - acc_buy.year) * 12 + calc_date.month - acc_buy.month
                acc_months_paid = min(acc_inst_months, max(0, months_passed))
                total_with_int = acc_price + acc_interest
                if acc_early: acc_outstanding, acc_paid_off = 0.0, True
                else:
                    acc_outstanding = round(total_with_int - (total_with_int / acc_inst_months * acc_months_paid), 2)
                    acc_paid_off = acc_outstanding <= 0

            processed_accessories.append({
                "id": acc.get("id", ""), "name": acc.get("name", "配件"), "price": acc_price, "image": acc.get("image", ""),
                "daily_cost": acc_daily, "days": acc_days, "is_retired": acc.get("is_retired", False), "reason": acc.get("retirement_reason", ""),
                "is_wearing": acc.get("is_wearing", False),
                "purchase_date": acc_buy_str, "expiration_date": acc_exp_str, 
                "is_installment": acc_is_inst, "installment_months": acc_inst_months,
                "months_paid": acc_months_paid, "outstanding_balance": max(0, acc_outstanding),
                "is_paid_off": acc_paid_off, "early_payoff": acc_early, "installment_interest": acc_interest
            })

        service_percent = None
        service_remain_days = "未知"
        if category == "虚拟服务" and exp_date:
            total_service = max(1, (exp_date - purchase_date).days)
            rem_service = max(0, (exp_date - today).days)
            service_percent = max(0, min(100, round((rem_service/total_service)*100)))
            service_remain_days = str(rem_service)

        attrs = {
            "friendly_name": self._device_name, "category": category, "purchase_date": str(purchase_date),
            "expiration_date": str(exp_date) if exp_date else "", "total_price": round(dynamic_price + interest + early_payoff_fee, 2),
            "net_price": round(net_main_price, 2), "daily_cost": round(daily_base + (total_consumable_cost / days) + total_acc_daily, 2),
            "daily_base": daily_base, "daily_consumable": round(total_consumable_cost/days, 2), "daily_accessory": round(total_acc_daily, 2),
            "total_consumable_cost": round(total_consumable_cost, 2), "total_accessory_net": round(total_acc_net, 2),
            "service_percent": service_percent, "service_remain_days": service_remain_days,
            "status": "retired" if is_retired else "active", "retire_reason": retire_reason if is_retired else "",
            "recovery_amount": recovery_amount, "consumables_list": processed_consumables, "accessories_list": processed_accessories,
            "installment_interest": interest, "early_payoff_fee": early_payoff_fee,
            "story": self._entry.options.get(CONF_STORY, ""), "location": self._entry.options.get(CONF_LOCATION, ""),
            "is_wearing": self._entry.options.get("is_wearing", False),
            "total_saved_value": round(total_saved_value, 2)
        }

        inst_months = int(safe_float(self._entry.data.get(CONF_INSTALLMENT_MONTHS, 0)))
        badges = []
        if category == "虚拟服务" and service_percent is not None and service_percent < 20 and service_remain_days != "未知": badges.append({"icon": "mdi:clock-alert", "label": "即将到期", "color": "#E53935"})
        if is_inst and inst_months > 0:
            calc_date = datetime.combine(end_date, datetime.min.time())
            months_passed = (calc_date.year - purchase_date.year) * 12 + calc_date.month - purchase_date.month
            months_paid_actual = min(inst_months, max(0, months_passed))
            total_with_interest = dynamic_price + interest
            if early_payoff: outstanding, is_paid_off = 0.0, True; badges.append({"icon": "mdi:rocket-launch", "label": "霸气提前结清", "color": "#E91E63"})
            else: outstanding = round(total_with_interest - (total_with_interest / inst_months * months_paid_actual), 2); is_paid_off = outstanding <= 0
            if is_paid_off and not early_payoff: badges.append({"icon": "mdi:check-decagram", "label": "无债一身轻", "color": "#7DA27E"})
            if interest <= 0: badges.append({"icon": "mdi:sale", "label": "免息分期", "color": "#4CAF50"})
            attrs.update({"installment_months": inst_months, "months_paid": months_paid_actual, "outstanding_balance": max(0, outstanding), "is_paid_off": is_paid_off, "early_payoff": early_payoff})
        elif category != "虚拟服务" and category != "纪念珍藏": badges.append({"icon": "mdi:cash-check", "label": "全款大户", "color": "#4CAF50"})

        if len(processed_accessories) > 0 and category != "虚拟服务": badges.append({"icon": "mdi:layers-triple", "label": "典藏完全体", "color": "#FF9800"})
        if any(c["is_smart"] for c in processed_consumables): badges.append({"icon": "mdi:robot-outline", "label": "AI智能托管", "color": "#2196F3"})
        if category == "纪念珍藏" and linked_price_entity: badges.append({"icon": "mdi:chart-line", "label": "价值实时计算", "color": "#FFC107"})

        if actual_days >= 3650: badges.append({"icon": "mdi:diamond-stone", "label": f"十载真情 ({round(actual_days/365.25, 1)}年)", "color": "#00BFFF"})
        elif actual_days >= 1500: badges.append({"icon": "mdi:shield-sun", "label": f"传世珍藏 ({actual_days}天)", "color": "#9C27B0"})
        elif actual_days >= 365: badges.append({"icon": "mdi:crown", "label": f"年度相伴 ({round(actual_days/365.25, 1)}年)", "color": "#FFD700"})
        elif actual_days >= 100: badges.append({"icon": "mdi:heart-pulse", "label": f"百日羁绊 ({actual_days}天)", "color": "#E91E63"})
        else: badges.append({"icon": "mdi:star-four-points", "label": f"新晋宠儿 ({actual_days}天)", "color": "#CD7F32"})

        attrs["badges"] = badges
        return actual_days, attrs

    @property
    def native_value(self): return self._computed_state[0]
    @property
    def extra_state_attributes(self): return self._computed_state[1]

class ConsumableSensor(SensorEntity):
    _attr_icon = "mdi:filter-outline"
    _attr_native_unit_of_measurement = "%"
    def __init__(self, entry: ConfigEntry, cons: dict): 
        self._entry, self._cons = entry, cons
        self._attr_name = f"{entry.data.get(CONF_DEVICE_NAME, '未知')} 耗材 ({cons.get('name', '')})"
        self._attr_unique_id = f"cons_{entry.entry_id}_{cons.get('id', '')}"
    @property
    def device_info(self) -> DeviceInfo: return DeviceInfo(identifiers={(DOMAIN, self._entry.entry_id)})
    @property
    def native_value(self):
        linked_id = self._cons.get(CONF_LINKED_ENTITY, "")
        if linked_id:
            ha_state = self.hass.states.get(linked_id)
            if ha_state:
                state_val = ha_state.state.lower()
                if state_val == "on": return 0.0
                elif state_val == "off": return 100.0
                try: return max(0.0, min(100.0, float(state_val)))
                except: return 100.0
            return 100.0
        last_rep = safe_date(self._cons.get("last_replace"), date.today())
        days_passed = (date.today() - last_rep).days
        cycle = max(1, int(safe_float(self._cons.get("cycle", 1))))
        remain = max(0, cycle - days_passed)
        return max(0, min(100, round((remain / cycle) * 100)))

class AccessorySensor(SensorEntity):
    _attr_icon = "mdi:puzzle-outline"
    _attr_native_unit_of_measurement = "天"
    def __init__(self, entry: ConfigEntry, acc: dict): 
        self._entry, self._acc = entry, acc
        self._attr_name = f"{entry.data.get(CONF_DEVICE_NAME, '未知')} 配件 ({acc.get('name', '')})"
        self._attr_unique_id = f"acc_{entry.entry_id}_{acc.get('id', '')}"
    @property
    def device_info(self) -> DeviceInfo: return DeviceInfo(identifiers={(DOMAIN, self._entry.entry_id)})
    @property
    def native_value(self): 
        acc_buy = safe_date(self._acc.get("purchase_date"), date.today())
        acc_end = safe_date(self._acc.get("retirement_date"), date.today()) if self._acc.get("is_retired") else date.today()
        return max(0, (acc_end - acc_buy).days)