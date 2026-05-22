"""Config flow for Device Companion."""
from typing import Any
import voluptuous as vol
import uuid
import calendar
from datetime import datetime, date
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector
from .const import *

CATEGORY_OPTIONS = ["数码产品", "生活家电", "交通出行", "虚拟服务", "纪念珍藏", "其他类别"]
TRACKING_OPTIONS = [{"value": TRACKING_MODE_MANUAL, "label": "⏳ 手动天数计算"}, {"value": TRACKING_MODE_SMART, "label": "⚡ 智能实体同步"}]
SUB_PERIODS = ["1个月", "3个月", "半年", "1年", "自定义"]

def add_months_to_date(dt_date, months):
    month = dt_date.month - 1 + months
    year = dt_date.year + month // 12
    month = month % 12 + 1
    day = min(dt_date.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)

class DeviceCompanionConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    def __init__(self):
        super().__init__()
        self._init_data = {}
        self._has_consumable = False

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            self._init_data.update(user_input)
            category = self._init_data[CONF_CATEGORY]
            if category == "虚拟服务": return await self.async_step_service_step()
            elif category == "纪念珍藏": return self.async_create_entry(title=self._init_data[CONF_DEVICE_NAME], data=self._init_data, options={CONF_CONSUMABLES_LIST: [], CONF_ACCESSORIES_LIST: []})
            else: return await self.async_step_device_features()
        return self.async_show_form(step_id="user", data_schema=vol.Schema({ vol.Required(CONF_DEVICE_NAME): str, vol.Required(CONF_CATEGORY, default="数码产品"): selector.SelectSelector(selector.SelectSelectorConfig(options=CATEGORY_OPTIONS, mode=selector.SelectSelectorMode.DROPDOWN)), vol.Required(CONF_PURCHASE_DATE): selector.DateSelector(), vol.Required(CONF_TOTAL_PRICE): vol.Coerce(float), vol.Optional(CONF_DEVICE_IMAGE, default=""): str }))

    async def async_step_device_features(self, user_input=None):
        if user_input is not None:
            self._init_data[CONF_IS_INSTALLMENT] = user_input.get("has_installment", False)
            self._has_consumable = user_input.get("has_consumable", False)
            if self._init_data[CONF_IS_INSTALLMENT]: return await self.async_step_installment_step()
            elif self._has_consumable: return await self.async_step_consumable_step()
            return self.async_create_entry(title=self._init_data[CONF_DEVICE_NAME], data=self._init_data, options={CONF_CONSUMABLES_LIST: [], CONF_ACCESSORIES_LIST: []})
        return self.async_show_form(step_id="device_features", data_schema=vol.Schema({ vol.Optional("has_installment", default=False): bool, vol.Optional("has_consumable", default=False): bool }))

    async def async_step_service_step(self, user_input=None):
        if user_input is not None:
            sub_period = user_input["sub_period"]
            purchase_date_str = self._init_data[CONF_PURCHASE_DATE]
            start_date = datetime.strptime(purchase_date_str.split("T")[0], "%Y-%m-%d").date() if isinstance(purchase_date_str, str) else purchase_date_str
            if sub_period == "自定义": exp_date = user_input.get(CONF_EXPIRATION_DATE, start_date)
            else:
                months_to_add = {"1个月": 1, "3个月": 3, "半年": 6, "1年": 12}.get(sub_period, 1)
                exp_date = add_months_to_date(start_date, months_to_add)
            self._init_data[CONF_IS_INSTALLMENT] = False
            return self.async_create_entry(title=self._init_data[CONF_DEVICE_NAME], data=self._init_data, options={CONF_SUB_PERIOD: sub_period, CONF_EXPIRATION_DATE: str(exp_date), CONF_CONSUMABLES_LIST: [], CONF_ACCESSORIES_LIST: []})
        return self.async_show_form(step_id="service_step", data_schema=vol.Schema({ vol.Required("sub_period", default="1个月"): selector.SelectSelector(selector.SelectSelectorConfig(options=SUB_PERIODS, mode=selector.SelectSelectorMode.DROPDOWN)), vol.Optional(CONF_EXPIRATION_DATE): selector.DateSelector() }))

    async def async_step_installment_step(self, user_input=None):
        if user_input is not None:
            self._init_data.update(user_input)
            if self._has_consumable: return await self.async_step_consumable_step()
            return self.async_create_entry(title=self._init_data[CONF_DEVICE_NAME], data=self._init_data, options={CONF_CONSUMABLES_LIST: [], CONF_ACCESSORIES_LIST: []})
        return self.async_show_form(step_id="installment_step", data_schema=vol.Schema({ vol.Required(CONF_INSTALLMENT_MONTHS, default=1): vol.Coerce(int), vol.Optional(CONF_INSTALLMENT_INTEREST, default=0.0): vol.Coerce(float) }))

    async def async_step_consumable_step(self, user_input=None):
        if user_input is not None:
            price = user_input.get(CONF_CONSUMABLE_PRICE, 0.0)
            consumables = [{"id": uuid.uuid4().hex[:8], "name": user_input[CONF_CONSUMABLE_NAME], "tracking_mode": user_input[CONF_TRACKING_MODE], "linked_entity": user_input.get(CONF_LINKED_ENTITY, ""), "price": price, "cycle": user_input[CONF_CONSUMABLE_CYCLE], "image": user_input.get(CONF_CONSUMABLE_IMAGE, ""), "last_replace": user_input.get(CONF_CONSUMABLE_START_DATE, str(datetime.now().date())), "accumulated_cost": price }] if user_input.get(CONF_CONSUMABLE_NAME) else []
            return self.async_create_entry(title=self._init_data[CONF_DEVICE_NAME], data=self._init_data, options={CONF_CONSUMABLES_LIST: consumables, CONF_ACCESSORIES_LIST: []})
        return self.async_show_form(step_id="consumable_step", data_schema=vol.Schema({ vol.Optional(CONF_CONSUMABLE_NAME, default=""): str, vol.Required(CONF_TRACKING_MODE, default=TRACKING_MODE_MANUAL): selector.SelectSelector(selector.SelectSelectorConfig(options=TRACKING_OPTIONS, mode=selector.SelectSelectorMode.DROPDOWN)), vol.Optional(CONF_LINKED_ENTITY): selector.EntitySelector(), vol.Optional(CONF_CONSUMABLE_PRICE, default=0.0): vol.Coerce(float), vol.Optional(CONF_CONSUMABLE_CYCLE, default=0): vol.Coerce(int), vol.Optional(CONF_CONSUMABLE_START_DATE, default=str(datetime.now().date())): selector.DateSelector(), vol.Optional(CONF_CONSUMABLE_IMAGE, default=""): str }))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry): return DeviceCompanionOptionsFlowHandler(config_entry)


class DeviceCompanionOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self._my_config_entry = config_entry
        self._edit_cons_id, self._edit_acc_id = None, None

    async def async_step_init(self, user_input=None):
        category = self._my_config_entry.data.get(CONF_CATEGORY)
        menu = ["edit_basic"]
        if category == "虚拟服务": menu.append("manage_perk_select")
        elif category == "纪念珍藏": menu.append("manage_mem_select")
        else: menu.append("manage_acc_select")
        menu.extend(["edit_consumable_select", "manage_consumable", "manage_lifecycle"])
        return self.async_show_menu(step_id="init", menu_options=menu)

    async def async_step_edit_basic(self, user_input=None):
        category = self._my_config_entry.data.get(CONF_CATEGORY)
        if user_input is not None:
            new_data = {**self._my_config_entry.data, CONF_DEVICE_NAME: user_input[CONF_DEVICE_NAME], CONF_CATEGORY: user_input[CONF_CATEGORY], CONF_TOTAL_PRICE: user_input["total_price"], CONF_PURCHASE_DATE: user_input["purchase_date"], CONF_IS_INSTALLMENT: user_input.get("is_installment", False), CONF_INSTALLMENT_MONTHS: user_input.get("installment_months", 1), CONF_INSTALLMENT_INTEREST: user_input.get("installment_interest", 0.0)}
            self.hass.config_entries.async_update_entry(self._my_config_entry, data=new_data, title=user_input[CONF_DEVICE_NAME])
            new_options = {**self._my_config_entry.options, "early_payoff": user_input.get("early_payoff", False), "early_payoff_fee": user_input.get("early_payoff_fee", 0.0)}
            if CONF_SUB_PERIOD in user_input: new_options[CONF_SUB_PERIOD] = user_input[CONF_SUB_PERIOD]
            if CONF_EXPIRATION_DATE in user_input: new_options[CONF_EXPIRATION_DATE] = user_input[CONF_EXPIRATION_DATE]
            if "story" in user_input: new_options["story"] = user_input["story"]
            if "location" in user_input: new_options["location"] = user_input["location"]
            if "is_wearing" in user_input: new_options["is_wearing"] = user_input["is_wearing"]
            if "linked_price_entity" in user_input: new_options["linked_price_entity"] = user_input["linked_price_entity"]
            return self.async_create_entry(title="", data=new_options)

        schema = {
            vol.Required(CONF_DEVICE_NAME, default=self._my_config_entry.data.get(CONF_DEVICE_NAME)): str,
            vol.Required(CONF_CATEGORY, default=category): selector.SelectSelector(selector.SelectSelectorConfig(options=CATEGORY_OPTIONS, mode=selector.SelectSelectorMode.DROPDOWN)),
            vol.Required("total_price", default=float(self._my_config_entry.data.get(CONF_TOTAL_PRICE, 0))): vol.Coerce(float),
            vol.Required("purchase_date", default=self._my_config_entry.data.get(CONF_PURCHASE_DATE)): selector.DateSelector(),
        }
        
        if category == "虚拟服务":
            schema[vol.Required(CONF_SUB_PERIOD, default=self._my_config_entry.options.get(CONF_SUB_PERIOD, "1个月"))] = selector.SelectSelector(selector.SelectSelectorConfig(options=SUB_PERIODS, mode=selector.SelectSelectorMode.DROPDOWN))
            schema[vol.Optional(CONF_EXPIRATION_DATE, default=self._my_config_entry.options.get(CONF_EXPIRATION_DATE, ""))] = selector.DateSelector()
        elif category == "纪念珍藏":
            schema[vol.Optional("story", default=self._my_config_entry.options.get("story", ""))] = selector.TextSelector(selector.TextSelectorConfig(multiline=True))
            schema[vol.Optional("location", default=self._my_config_entry.options.get("location", ""))] = str
            schema[vol.Optional("is_wearing", default=self._my_config_entry.options.get("is_wearing", False))] = bool
            schema[vol.Optional("linked_price_entity", default=self._my_config_entry.options.get("linked_price_entity", ""))] = str

        schema[vol.Optional("is_installment", default=self._my_config_entry.data.get(CONF_IS_INSTALLMENT, False))] = bool
        schema[vol.Optional("installment_months", default=int(self._my_config_entry.data.get(CONF_INSTALLMENT_MONTHS, 1)))] = vol.Coerce(int)
        schema[vol.Optional("installment_interest", default=float(self._my_config_entry.data.get(CONF_INSTALLMENT_INTEREST, 0.0)))] = vol.Coerce(float)
        schema[vol.Optional("early_payoff", default=self._my_config_entry.options.get("early_payoff", False))] = bool
        schema[vol.Optional("early_payoff_fee", default=float(self._my_config_entry.options.get("early_payoff_fee", 0.0)))] = vol.Coerce(float)
        return self.async_show_form(step_id="edit_basic", data_schema=vol.Schema(schema))

    # ==========================
    # 🎯 数码配件分支
    # ==========================
    async def async_step_manage_acc_select(self, user_input=None):
        accessories = self._my_config_entry.options.get(CONF_ACCESSORIES_LIST, [])
        if user_input is not None:
            if user_input["selected_item"] == "ADD_NEW": return await self.async_step_manage_acc_add()
            else: self._edit_acc_id = user_input["selected_item"]; return await self.async_step_manage_acc_edit()
        options = [{"value": "ADD_NEW", "label": "➕ [录入新配件]"}]
        for a in accessories: options.append({"value": a["id"], "label": f"{a['name']} {'(退役)' if a.get('is_retired') else ''}"})
        return self.async_show_form(step_id="manage_acc_select", data_schema=vol.Schema({vol.Required("selected_item", default="ADD_NEW"): selector.SelectSelector(selector.SelectSelectorConfig(options=options, mode=selector.SelectSelectorMode.DROPDOWN))}))

    async def async_step_manage_acc_add(self, user_input=None):
        if user_input is not None:
            new_options = dict(self._my_config_entry.options)
            accessories = list(new_options.get(CONF_ACCESSORIES_LIST, []))
            accessories.append({ "id": f"acc_{uuid.uuid4().hex[:8]}", "name": user_input["name"], "price": user_input["price"], "purchase_date": user_input["purchase_date"], "is_installment": user_input.get("is_installment", False), "installment_months": user_input.get("installment_months", 1), "installment_interest": user_input.get("installment_interest", 0.0), "image": user_input.get("image", ""), "is_retired": False, "retirement_reason": "✨ 正常服役", "recovery_amount": 0.0 })
            new_options[CONF_ACCESSORIES_LIST] = accessories
            return self.async_create_entry(title="", data=new_options)
        return self.async_show_form(step_id="manage_acc_add", data_schema=vol.Schema({ vol.Required("name"): str, vol.Required("price"): vol.Coerce(float), vol.Required("purchase_date", default=str(datetime.now().date())): selector.DateSelector(), vol.Optional("is_installment", default=False): bool, vol.Optional("installment_months", default=1): vol.Coerce(int), vol.Optional("installment_interest", default=0.0): vol.Coerce(float), vol.Optional("image", default=""): str }))

    async def async_step_manage_acc_edit(self, user_input=None):
        accessories = list(self._my_config_entry.options.get(CONF_ACCESSORIES_LIST, []))
        target_idx = next((i for i, a in enumerate(accessories) if a["id"] == self._edit_acc_id), None)
        current_acc = accessories[target_idx]
        if user_input is not None:
            if user_input.get("delete_this", False): accessories.pop(target_idx)
            else:
                new_img = user_input.get("image", "").strip() or current_acc.get("image", "")
                current_acc.update({ "name": user_input["name"], "price": user_input["price"], "purchase_date": user_input["purchase_date"], "is_installment": user_input.get("is_installment", False), "installment_months": user_input.get("installment_months", 1), "installment_interest": user_input.get("installment_interest", 0.0), "early_payoff": user_input.get("early_payoff", False), "early_payoff_fee": user_input.get("early_payoff_fee", 0.0), "is_retired": user_input.get("is_retired", False), "retirement_reason": user_input.get("retirement_reason", "✨ 正常服役"), "recovery_amount": user_input.get("recovery_amount", 0.0), "image": new_img })
            new_options = dict(self._my_config_entry.options)
            new_options[CONF_ACCESSORIES_LIST] = accessories
            return self.async_create_entry(title="", data=new_options)
            
        reason_opts = ["✨ 正常服役", "光荣闲置", "二手回血", "光荣报废", "意外遗失", "馈赠他人"]
        default_r = current_acc.get("retirement_reason", reason_opts[0])
        if default_r not in reason_opts: default_r = reason_opts[0]
        
        return self.async_show_form(step_id="manage_acc_edit", data_schema=vol.Schema({ vol.Required("name", default=current_acc["name"]): str, vol.Required("price", default=float(current_acc["price"])): vol.Coerce(float), vol.Required("purchase_date", default=current_acc["purchase_date"]): selector.DateSelector(), vol.Optional("is_installment", default=current_acc.get("is_installment", False)): bool, vol.Optional("installment_months", default=int(current_acc.get("installment_months", 1))): vol.Coerce(int), vol.Optional("installment_interest", default=float(current_acc.get("installment_interest", 0.0))): vol.Coerce(float), vol.Optional("early_payoff", default=current_acc.get("early_payoff", False)): bool, vol.Optional("early_payoff_fee", default=float(current_acc.get("early_payoff_fee", 0.0))): vol.Coerce(float), vol.Optional("is_retired", default=current_acc.get("is_retired", False)): bool, vol.Optional("retirement_reason", default=default_r): selector.SelectSelector(selector.SelectSelectorConfig(options=reason_opts, mode=selector.SelectSelectorMode.DROPDOWN)), vol.Optional("recovery_amount", default=float(current_acc.get("recovery_amount", 0.0))): vol.Coerce(float), vol.Optional("image", default=current_acc.get("image", "")): str, vol.Optional("delete_this", default=False): bool }))

    # ==========================
    # 🎯 虚拟服务权益分支
    # ==========================
    async def async_step_manage_perk_select(self, user_input=None):
        accessories = self._my_config_entry.options.get(CONF_ACCESSORIES_LIST, [])
        if user_input is not None:
            if user_input["selected_item"] == "ADD_NEW": return await self.async_step_manage_perk_add()
            else: self._edit_acc_id = user_input["selected_item"]; return await self.async_step_manage_perk_edit()
        options = [{"value": "ADD_NEW", "label": "➕ [录入新赠送权益]"}]
        for a in accessories: options.append({"value": a["id"], "label": f"{a['name']} {'(失效)' if a.get('is_retired') else ''}"})
        return self.async_show_form(step_id="manage_perk_select", data_schema=vol.Schema({vol.Required("selected_item", default="ADD_NEW"): selector.SelectSelector(selector.SelectSelectorConfig(options=options, mode=selector.SelectSelectorMode.DROPDOWN))}))

    async def async_step_manage_perk_add(self, user_input=None):
        if user_input is not None:
            new_options = dict(self._my_config_entry.options)
            accessories = list(new_options.get(CONF_ACCESSORIES_LIST, []))
            accessories.append({ "id": f"acc_{uuid.uuid4().hex[:8]}", "name": user_input["name"], "price": user_input["price"], "purchase_date": user_input["purchase_date"], "expiration_date": user_input.get("expiration_date", ""), "image": user_input.get("image", ""), "is_retired": False, "retirement_reason": "✨ 正常生效" })
            new_options[CONF_ACCESSORIES_LIST] = accessories
            return self.async_create_entry(title="", data=new_options)
        return self.async_show_form(step_id="manage_perk_add", data_schema=vol.Schema({ vol.Required("name"): str, vol.Required("price", default=0.0): vol.Coerce(float), vol.Required("purchase_date", default=str(datetime.now().date())): selector.DateSelector(), vol.Optional("expiration_date", default=""): selector.DateSelector(), vol.Optional("image", default=""): str }))

    async def async_step_manage_perk_edit(self, user_input=None):
        accessories = list(self._my_config_entry.options.get(CONF_ACCESSORIES_LIST, []))
        target_idx = next((i for i, a in enumerate(accessories) if a["id"] == self._edit_acc_id), None)
        current_acc = accessories[target_idx]
        if user_input is not None:
            if user_input.get("delete_this", False): accessories.pop(target_idx)
            else:
                new_img = user_input.get("image", "").strip() or current_acc.get("image", "")
                current_acc.update({ "name": user_input["name"], "price": user_input["price"], "purchase_date": user_input["purchase_date"], "expiration_date": user_input.get("expiration_date", ""), "is_retired": user_input.get("is_retired", False), "retirement_reason": user_input.get("retirement_reason", "✨ 正常生效"), "image": new_img })
            new_options = dict(self._my_config_entry.options)
            new_options[CONF_ACCESSORIES_LIST] = accessories
            return self.async_create_entry(title="", data=new_options)
            
        reason_opts = ["✨ 正常生效", "已失效", "光荣闲置"]
        default_r = current_acc.get("retirement_reason", reason_opts[0])
        if default_r not in reason_opts: default_r = reason_opts[0]
        
        return self.async_show_form(step_id="manage_perk_edit", data_schema=vol.Schema({ vol.Required("name", default=current_acc["name"]): str, vol.Required("price", default=float(current_acc["price"])): vol.Coerce(float), vol.Required("purchase_date", default=current_acc["purchase_date"]): selector.DateSelector(), vol.Optional("expiration_date", default=current_acc.get("expiration_date", "")): selector.DateSelector(), vol.Optional("is_retired", default=current_acc.get("is_retired", False)): bool, vol.Optional("retirement_reason", default=default_r): selector.SelectSelector(selector.SelectSelectorConfig(options=reason_opts, mode=selector.SelectSelectorMode.DROPDOWN)), vol.Optional("image", default=current_acc.get("image", "")): str, vol.Optional("delete_this", default=False): bool }))

    # ==========================
    # 🎯 纪念单品分支
    # ==========================
    async def async_step_manage_mem_select(self, user_input=None):
        accessories = self._my_config_entry.options.get(CONF_ACCESSORIES_LIST, [])
        if user_input is not None:
            if user_input["selected_item"] == "ADD_NEW": return await self.async_step_manage_mem_add()
            else: self._edit_acc_id = user_input["selected_item"]; return await self.async_step_manage_mem_edit()
        options = [{"value": "ADD_NEW", "label": "➕ [录入新对戒/单品]"}]
        for a in accessories: options.append({"value": a["id"], "label": f"{a['name']} {'(封存)' if a.get('is_retired') else ''}"})
        return self.async_show_form(step_id="manage_mem_select", data_schema=vol.Schema({vol.Required("selected_item", default="ADD_NEW"): selector.SelectSelector(selector.SelectSelectorConfig(options=options, mode=selector.SelectSelectorMode.DROPDOWN))}))

    async def async_step_manage_mem_add(self, user_input=None):
        if user_input is not None:
            new_options = dict(self._my_config_entry.options)
            accessories = list(new_options.get(CONF_ACCESSORIES_LIST, []))
            accessories.append({ "id": f"acc_{uuid.uuid4().hex[:8]}", "name": user_input["name"], "price": user_input["price"], "purchase_date": user_input["purchase_date"], "is_wearing": user_input.get("is_wearing", False), "image": user_input.get("image", ""), "is_retired": False, "retirement_reason": "✨ 正常陪伴/佩戴中" })
            new_options[CONF_ACCESSORIES_LIST] = accessories
            return self.async_create_entry(title="", data=new_options)
        return self.async_show_form(step_id="manage_mem_add", data_schema=vol.Schema({ vol.Required("name"): str, vol.Required("price", default=0.0): vol.Coerce(float), vol.Required("purchase_date", default=str(datetime.now().date())): selector.DateSelector(), vol.Optional("is_wearing", default=False): bool, vol.Optional("image", default=""): str }))

    async def async_step_manage_mem_edit(self, user_input=None):
        accessories = list(self._my_config_entry.options.get(CONF_ACCESSORIES_LIST, []))
        target_idx = next((i for i, a in enumerate(accessories) if a["id"] == self._edit_acc_id), None)
        current_acc = accessories[target_idx]
        if user_input is not None:
            if user_input.get("delete_this", False): accessories.pop(target_idx)
            else:
                new_img = user_input.get("image", "").strip() or current_acc.get("image", "")
                current_acc.update({ "name": user_input["name"], "price": user_input["price"], "purchase_date": user_input["purchase_date"], "is_wearing": user_input.get("is_wearing", False), "is_retired": user_input.get("is_retired", False), "retirement_reason": user_input.get("retirement_reason", "✨ 正常陪伴/佩戴中"), "recovery_amount": user_input.get("recovery_amount", 0.0), "image": new_img })
            new_options = dict(self._my_config_entry.options)
            new_options[CONF_ACCESSORIES_LIST] = accessories
            return self.async_create_entry(title="", data=new_options)
            
        reason_opts = ["✨ 正常陪伴/佩戴中", "光荣闲置", "意外遗失", "二手回血", "馈赠他人"]
        default_r = current_acc.get("retirement_reason", reason_opts[0])
        if default_r not in reason_opts: default_r = reason_opts[0]
        
        return self.async_show_form(step_id="manage_mem_edit", data_schema=vol.Schema({ vol.Required("name", default=current_acc["name"]): str, vol.Required("price", default=float(current_acc["price"])): vol.Coerce(float), vol.Required("purchase_date", default=current_acc["purchase_date"]): selector.DateSelector(), vol.Optional("is_wearing", default=current_acc.get("is_wearing", False)): bool, vol.Optional("is_retired", default=current_acc.get("is_retired", False)): bool, vol.Optional("retirement_reason", default=default_r): selector.SelectSelector(selector.SelectSelectorConfig(options=reason_opts, mode=selector.SelectSelectorMode.DROPDOWN)), vol.Optional("recovery_amount", default=float(current_acc.get("recovery_amount", 0.0))): vol.Coerce(float), vol.Optional("image", default=current_acc.get("image", "")): str, vol.Optional("delete_this", default=False): bool }))

    # ==========================
    # 耗材与生命周期
    # ==========================
    async def async_step_edit_consumable_select(self, user_input=None):
        consumables = self._my_config_entry.options.get(CONF_CONSUMABLES_LIST, [])
        if not consumables: return self.async_abort(reason="no_consumables")
        if user_input is not None: self._edit_cons_id = user_input["selected_consumable"]; return await self.async_step_edit_consumable_form()
        return self.async_show_form(step_id="edit_consumable_select", data_schema=vol.Schema({vol.Required("selected_consumable"): selector.SelectSelector(selector.SelectSelectorConfig(options=[{"value": c["id"], "label": f"{c['name']} (￥{c['price']})"} for c in consumables], mode=selector.SelectSelectorMode.DROPDOWN))}))
    
    async def async_step_edit_consumable_form(self, user_input=None):
        consumables = list(self._my_config_entry.options.get(CONF_CONSUMABLES_LIST, []))
        target_idx = next((i for i, c in enumerate(consumables) if c["id"] == self._edit_cons_id), None)
        current_cons = consumables[target_idx]
        if user_input is not None:
            if user_input.get("delete_this", False): consumables.pop(target_idx)
            else: 
                new_img = user_input.get("edit_image", "").strip() or current_cons.get("image", "")
                current_cons.update({"name": user_input["edit_name"], "tracking_mode": user_input["tracking_mode"], "linked_entity": user_input.get("linked_entity", ""), "price": user_input["edit_price"], "cycle": user_input.get("edit_cycle", 0), "last_replace": user_input["edit_start_date"], "image": new_img})
            new_options = dict(self._my_config_entry.options)
            new_options[CONF_CONSUMABLES_LIST] = consumables
            return self.async_create_entry(title="", data=new_options)
        return self.async_show_form(step_id="edit_consumable_form", data_schema=vol.Schema({ vol.Required("edit_name", default=current_cons["name"]): str, vol.Required("tracking_mode", default=current_cons.get("tracking_mode", TRACKING_MODE_MANUAL)): selector.SelectSelector(selector.SelectSelectorConfig(options=TRACKING_OPTIONS, mode=selector.SelectSelectorMode.DROPDOWN)), vol.Optional("linked_entity", default=current_cons.get("linked_entity", "")): selector.EntitySelector(), vol.Required("edit_price", default=float(current_cons["price"])): vol.Coerce(float), vol.Optional("edit_cycle", default=int(current_cons.get("cycle", 0))): vol.Coerce(int), vol.Optional("edit_start_date", default=current_cons["last_replace"]): selector.DateSelector(), vol.Optional("edit_image", default=current_cons.get("image", "")): str, vol.Optional("delete_this", default=False): bool }))
    
    async def async_step_manage_consumable(self, user_input=None):
        if user_input is not None:
            new_options = dict(self._my_config_entry.options)
            consumables = list(new_options.get(CONF_CONSUMABLES_LIST, []))
            consumables.append({ "id": uuid.uuid4().hex[:8], "name": user_input["new_name"], "tracking_mode": user_input["tracking_mode"], "linked_entity": user_input.get("linked_entity", ""), "price": user_input["new_price"], "cycle": user_input.get("new_cycle", 0), "image": user_input.get("new_image", ""), "last_replace": user_input.get("new_start_date", str(datetime.now().date())), "accumulated_cost": user_input["new_price"] })
            new_options[CONF_CONSUMABLES_LIST] = consumables
            return self.async_create_entry(title="", data=new_options)
        return self.async_show_form(step_id="manage_consumable", data_schema=vol.Schema({ vol.Required("new_name"): str, vol.Required("tracking_mode", default=TRACKING_MODE_MANUAL): selector.SelectSelector(selector.SelectSelectorConfig(options=TRACKING_OPTIONS, mode=selector.SelectSelectorMode.DROPDOWN)), vol.Optional("linked_entity"): selector.EntitySelector(), vol.Required("new_price"): vol.Coerce(float), vol.Optional("new_cycle", default=0): vol.Coerce(int), vol.Optional("new_start_date", default=str(datetime.now().date())): selector.DateSelector(), vol.Optional("new_image", default=""): str }))
    
    async def async_step_manage_lifecycle(self, user_input=None):
        current = self._my_config_entry.options
        if user_input is not None:
            self._temp_options = dict(current)
            self._temp_options["is_retired"] = user_input["is_retired"]
            self._temp_options["retirement_reason"] = user_input["retirement_reason"]
            self._temp_options["retirement_date"] = str(datetime.now().date())
            if user_input["is_retired"] and user_input["retirement_reason"] == "二手回血": return await self.async_step_lifecycle_sub()
            return self.async_create_entry(title="", data=self._temp_options)
            
        reason_opts = ["✨ 正常服役", "光荣闲置", "二手回血", "光荣报废", "意外遗失", "馈赠他人", "已取消/未续订"]
        default_r = current.get("retirement_reason", reason_opts[0])
        if default_r not in reason_opts: default_r = reason_opts[0]
            
        return self.async_show_form(step_id="manage_lifecycle", data_schema=vol.Schema({ vol.Optional("is_retired", default=current.get("is_retired", False)): bool, vol.Required("retirement_reason", default=default_r): selector.SelectSelector(selector.SelectSelectorConfig(options=reason_opts, mode=selector.SelectSelectorMode.DROPDOWN)) }))
    
    async def async_step_lifecycle_sub(self, user_input=None):
        if user_input is not None: self._temp_options["recovery_amount"] = user_input["recovery_amount"]; return self.async_create_entry(title="", data=self._temp_options)
        return self.async_show_form(step_id="lifecycle_sub", data_schema=vol.Schema({vol.Required("recovery_amount", default=0.0): vol.Coerce(float)}))