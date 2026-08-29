"""Config flow for HomeAsset Companion."""

from __future__ import annotations

from copy import deepcopy
from typing import Any
import uuid

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_ACCESSORIES_LIST,
    CONF_AUTO_RECORD_REPLACEMENT,
    CONF_CATEGORY,
    CONF_CONSUMABLE_CYCLE,
    CONF_CONSUMABLE_IMAGE,
    CONF_CONSUMABLE_NAME,
    CONF_CONSUMABLE_PRICE,
    CONF_CONSUMABLE_START_DATE,
    CONF_CONSUMABLES_LIST,
    CONF_CURRENT_PERIOD_COST,
    CONF_DEVICE_IMAGE,
    CONF_DEVICE_NAME,
    CONF_EARLY_PAYOFF,
    CONF_EARLY_PAYOFF_FEE,
    CONF_EXPIRATION_DATE,
    CONF_INSTALLMENT_INTEREST,
    CONF_INSTALLMENT_MONTHS,
    CONF_IS_EVENT,
    CONF_IS_INSTALLMENT,
    CONF_KIND,
    CONF_LINKED_ENTITY,
    CONF_LINKED_PRICE_ENTITY,
    CONF_LOCATION,
    CONF_PURCHASE_DATE,
    CONF_SCHEMA_VERSION,
    CONF_STATUS,
    CONF_STORY,
    CONF_SUB_PERIOD,
    CONF_SYNC_TO_CALENDAR,
    CONF_TOTAL_PRICE,
    DOMAIN,
    KIND_ASSET,
    KIND_EVENT,
    KIND_MEMORIAL,
    KIND_SERVICE,
    STATUS_ACTIVE,
    STATUS_SOLD,
    TRACKING_MODE_MANUAL,
    TRACKING_MODE_SMART,
)
from .helpers import (
    add_months_to_date,
    infer_kind,
    legacy_status,
    normalize_status_record,
    safe_date,
    safe_float,
    status_label,
    status_selector_options,
    today_local,
)

ASSET_CATEGORIES = ["数码产品", "生活家电", "交通出行", "其他类别"]
CATEGORY_OPTIONS = [*ASSET_CATEGORIES, "虚拟服务", "纪念珍藏", "纪念事件"]
TRACKING_OPTIONS = [
    {"value": TRACKING_MODE_MANUAL, "label": "手动周期"},
    {"value": TRACKING_MODE_SMART, "label": "关联实体"},
]
SUB_PERIODS = ["1个月", "3个月", "半年", "1年", "自定义"]


def _default_options() -> dict[str, Any]:
    options: dict[str, Any] = {
        CONF_SCHEMA_VERSION: 2,
        CONF_SYNC_TO_CALENDAR: True,
        CONF_CONSUMABLES_LIST: [],
        CONF_ACCESSORIES_LIST: [],
    }
    options.update(normalize_status_record({}, STATUS_ACTIVE))
    return options


def _new_consumable(user_input: dict[str, Any], *, prefix: str = "") -> dict[str, Any]:
    return {
        "id": f"cons_{uuid.uuid4().hex[:12]}",
        "name": user_input[f"{prefix}name"],
        "tracking_mode": user_input["tracking_mode"],
        CONF_LINKED_ENTITY: user_input.get(CONF_LINKED_ENTITY, ""),
        "price": max(0.0, safe_float(user_input[f"{prefix}price"])),
        "cycle": max(0, int(safe_float(user_input.get(f"{prefix}cycle", 0)))),
        "image": user_input.get(f"{prefix}image", ""),
        "last_replace": str(user_input.get(f"{prefix}start_date", today_local())),
        "accumulated_cost": max(0.0, safe_float(user_input[f"{prefix}price"])),
        CONF_AUTO_RECORD_REPLACEMENT: user_input.get(
            CONF_AUTO_RECORD_REPLACEMENT, False
        ),
        "last_detected_reset": "",
    }


def _validate_consumable_input(
    user_input: dict[str, Any], *, prefix: str = ""
) -> dict[str, str]:
    errors: dict[str, str] = {}
    mode = user_input.get("tracking_mode", TRACKING_MODE_MANUAL)
    if mode == TRACKING_MODE_SMART and not user_input.get(CONF_LINKED_ENTITY):
        errors[CONF_LINKED_ENTITY] = "linked_entity_required"
    if mode == TRACKING_MODE_MANUAL and int(
        safe_float(user_input.get(f"{prefix}cycle", 0))
    ) <= 0:
        errors[f"{prefix}cycle"] = "cycle_required"
    return errors


class DeviceCompanionConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a HomeAsset Companion config flow."""

    VERSION = 2
    MINOR_VERSION = 0

    def __init__(self) -> None:
        self._init_data: dict[str, Any] = {}
        self._has_consumable = False

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select the stable record kind."""
        if user_input is not None:
            category = user_input[CONF_CATEGORY]
            self._init_data[CONF_CATEGORY] = category
            if category == "虚拟服务":
                self._init_data[CONF_KIND] = KIND_SERVICE
                return await self.async_step_setup_service()
            if category == "纪念珍藏":
                self._init_data[CONF_KIND] = KIND_MEMORIAL
                return await self.async_step_setup_memorial()
            if category == "纪念事件":
                self._init_data[CONF_KIND] = KIND_EVENT
                return await self.async_step_setup_event()
            self._init_data[CONF_KIND] = KIND_ASSET
            return await self.async_step_setup_device()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_CATEGORY, default="数码产品"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=CATEGORY_OPTIONS,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
        )

    async def async_step_setup_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create a physical asset record."""
        if user_input is not None:
            self._init_data.update(user_input)
            self._has_consumable = user_input.get("has_consumable", False)
            has_installment = user_input.get("has_installment", False)
            self._init_data.pop("has_consumable", None)
            self._init_data.pop("has_installment", None)
            if has_installment:
                return await self.async_step_installment_step()
            self._init_data[CONF_IS_INSTALLMENT] = False
            if self._has_consumable:
                return await self.async_step_consumable_step()
            return self.async_create_entry(
                title=self._init_data[CONF_DEVICE_NAME],
                data=self._init_data,
                options=_default_options(),
            )

        return self.async_show_form(
            step_id="setup_device",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE_NAME): str,
                    vol.Required(
                        CONF_PURCHASE_DATE, default=str(today_local())
                    ): selector.DateSelector(),
                    vol.Required(CONF_TOTAL_PRICE, default=0.0): vol.All(
                        vol.Coerce(float), vol.Range(min=0)
                    ),
                    vol.Optional(CONF_DEVICE_IMAGE, default=""): str,
                    vol.Optional("has_installment", default=False): bool,
                    vol.Optional("has_consumable", default=False): bool,
                }
            ),
        )

    async def async_step_setup_service(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create a subscription/service record."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._init_data.update(user_input)
            start_date = safe_date(user_input[CONF_PURCHASE_DATE], today_local())
            period = user_input[CONF_SUB_PERIOD]
            expiration = safe_date(user_input.get(CONF_EXPIRATION_DATE))
            if period == "自定义" and expiration is None:
                errors[CONF_EXPIRATION_DATE] = "expiration_required"
            else:
                if expiration is None:
                    expiration = add_months_to_date(
                        start_date,
                        {"1个月": 1, "3个月": 3, "半年": 6, "1年": 12}.get(
                            period, 1
                        ),
                    )
                if expiration < start_date:
                    errors[CONF_EXPIRATION_DATE] = "expiration_before_start"
                else:
                    self._init_data[CONF_IS_INSTALLMENT] = False
                    self._init_data.pop(CONF_SUB_PERIOD, None)
                    self._init_data.pop(CONF_EXPIRATION_DATE, None)
                    options = _default_options()
                    options[CONF_SUB_PERIOD] = period
                    options[CONF_CURRENT_PERIOD_COST] = max(
                        0.0, safe_float(self._init_data.get(CONF_TOTAL_PRICE))
                    )
                    options[CONF_EXPIRATION_DATE] = str(expiration)
                    options["service_period_start"] = str(start_date)
                    options["service_period_days"] = max(1, (expiration - start_date).days)
                    return self.async_create_entry(
                        title=self._init_data[CONF_DEVICE_NAME],
                        data=self._init_data,
                        options=options,
                    )

        return self.async_show_form(
            step_id="setup_service",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE_NAME): str,
                    vol.Required(
                        CONF_PURCHASE_DATE, default=str(today_local())
                    ): selector.DateSelector(),
                    vol.Required(CONF_TOTAL_PRICE, default=0.0): vol.All(
                        vol.Coerce(float), vol.Range(min=0)
                    ),
                    vol.Required(
                        CONF_SUB_PERIOD, default="1个月"
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=SUB_PERIODS,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Optional(CONF_EXPIRATION_DATE): selector.DateSelector(),
                }
            ),
            errors=errors,
        )

    async def async_step_setup_memorial(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create a memorial object record."""
        if user_input is not None:
            self._init_data.update(user_input)
            self._init_data.pop("anniversary_name", None)
            self._init_data.pop("is_wearing", None)
            options = _default_options()
            options.update(
                {
                    "anniversary_name": user_input.get("anniversary_name", ""),
                    "is_wearing": user_input.get("is_wearing", False),
                }
            )
            return self.async_create_entry(
                title=self._init_data[CONF_DEVICE_NAME],
                data=self._init_data,
                options=options,
            )

        return self.async_show_form(
            step_id="setup_memorial",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE_NAME): str,
                    vol.Required(
                        CONF_PURCHASE_DATE, default=str(today_local())
                    ): selector.DateSelector(),
                    vol.Optional(CONF_TOTAL_PRICE, default=0.0): vol.All(
                        vol.Coerce(float), vol.Range(min=0)
                    ),
                    vol.Optional("anniversary_name", default=""): str,
                    vol.Optional("is_wearing", default=False): bool,
                    vol.Optional(CONF_DEVICE_IMAGE, default=""): str,
                }
            ),
        )

    async def async_step_setup_event(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create a pure anniversary/event record."""
        if user_input is not None:
            self._init_data.update(user_input)
            anniversary_name = user_input.get("anniversary_name", "")
            self._init_data.pop("anniversary_name", None)
            self._init_data[CONF_IS_EVENT] = True
            self._init_data[CONF_TOTAL_PRICE] = 0.0
            options = _default_options()
            options["anniversary_name"] = anniversary_name
            return self.async_create_entry(
                title=f"💝 {self._init_data[CONF_DEVICE_NAME]}",
                data=self._init_data,
                options=options,
            )

        return self.async_show_form(
            step_id="setup_event",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE_NAME): str,
                    vol.Required(
                        CONF_PURCHASE_DATE, default=str(today_local())
                    ): selector.DateSelector(),
                    vol.Optional("anniversary_name", default=""): str,
                }
            ),
        )

    async def async_step_installment_step(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect installment details."""
        if user_input is not None:
            self._init_data[CONF_IS_INSTALLMENT] = True
            self._init_data[CONF_INSTALLMENT_MONTHS] = user_input[
                CONF_INSTALLMENT_MONTHS
            ]
            self._init_data[CONF_INSTALLMENT_INTEREST] = user_input.get(
                CONF_INSTALLMENT_INTEREST, 0.0
            )
            if self._has_consumable:
                return await self.async_step_consumable_step()
            return self.async_create_entry(
                title=self._init_data[CONF_DEVICE_NAME],
                data=self._init_data,
                options=_default_options(),
            )

        return self.async_show_form(
            step_id="installment_step",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_INSTALLMENT_MONTHS, default=1): vol.All(
                        vol.Coerce(int), vol.Range(min=1, max=240)
                    ),
                    vol.Optional(CONF_INSTALLMENT_INTEREST, default=0.0): vol.All(
                        vol.Coerce(float), vol.Range(min=0)
                    ),
                }
            ),
        )

    async def async_step_consumable_step(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Optionally create the first consumable."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input.get(CONF_CONSUMABLE_NAME):
                return self.async_create_entry(
                    title=self._init_data[CONF_DEVICE_NAME],
                    data=self._init_data,
                    options=_default_options(),
                )
            normalized = {
                "name": user_input[CONF_CONSUMABLE_NAME],
                "price": user_input.get(CONF_CONSUMABLE_PRICE, 0.0),
                "cycle": user_input.get(CONF_CONSUMABLE_CYCLE, 0),
                "image": user_input.get(CONF_CONSUMABLE_IMAGE, ""),
                "start_date": user_input.get(
                    CONF_CONSUMABLE_START_DATE, str(today_local())
                ),
                "tracking_mode": user_input["tracking_mode"],
                CONF_LINKED_ENTITY: user_input.get(CONF_LINKED_ENTITY, ""),
                CONF_AUTO_RECORD_REPLACEMENT: user_input.get(
                    CONF_AUTO_RECORD_REPLACEMENT, False
                ),
            }
            errors = _validate_consumable_input(normalized)
            if not errors:
                options = _default_options()
                options[CONF_CONSUMABLES_LIST] = [_new_consumable(normalized)]
                return self.async_create_entry(
                    title=self._init_data[CONF_DEVICE_NAME],
                    data=self._init_data,
                    options=options,
                )

        return self.async_show_form(
            step_id="consumable_step",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_CONSUMABLE_NAME, default=""): str,
                    vol.Required(
                        "tracking_mode", default=TRACKING_MODE_MANUAL
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=TRACKING_OPTIONS,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Optional(CONF_LINKED_ENTITY): selector.EntitySelector(),
                    vol.Optional(CONF_CONSUMABLE_PRICE, default=0.0): vol.All(
                        vol.Coerce(float), vol.Range(min=0)
                    ),
                    vol.Optional(CONF_CONSUMABLE_CYCLE, default=0): vol.All(
                        vol.Coerce(int), vol.Range(min=0)
                    ),
                    vol.Optional(
                        CONF_CONSUMABLE_START_DATE, default=str(today_local())
                    ): selector.DateSelector(),
                    vol.Optional(CONF_AUTO_RECORD_REPLACEMENT, default=False): bool,
                    vol.Optional(CONF_CONSUMABLE_IMAGE, default=""): str,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry):
        """Create the options flow."""
        return DeviceCompanionOptionsFlowHandler()


class DeviceCompanionOptionsFlowHandler(config_entries.OptionsFlow):
    """Manage an existing HomeAsset Companion record."""

    def __init__(self) -> None:
        self._edit_cons_id: str | None = None
        self._edit_acc_id: str | None = None

    def _latest_options(self) -> dict[str, Any]:
        current = self.hass.config_entries.async_get_entry(self.config_entry.entry_id)
        return deepcopy(dict(current.options if current else self.config_entry.options))

    @property
    def _kind(self) -> str:
        return infer_kind(dict(self.config_entry.data))

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the context-aware management menu."""
        if self._kind == KIND_EVENT:
            return await self.async_step_edit_basic()

        menu = ["edit_basic"]
        if self._kind == KIND_SERVICE:
            menu.append("manage_perk_select")
        elif self._kind == KIND_MEMORIAL:
            menu.append("manage_mem_select")
        else:
            menu.append("manage_acc_select")
        if self._kind == KIND_ASSET:
            menu.extend(["edit_consumable_select", "manage_consumable"])
        menu.append("manage_lifecycle")
        return self.async_show_menu(step_id="init", menu_options=menu)

    async def async_step_edit_basic(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit stable record fields without changing its business kind."""
        data = deepcopy(dict(self.config_entry.data))
        options = self._latest_options()
        kind = self._kind
        errors: dict[str, str] = {}

        if user_input is not None:
            data[CONF_DEVICE_NAME] = user_input[CONF_DEVICE_NAME]
            data[CONF_PURCHASE_DATE] = user_input[CONF_PURCHASE_DATE]
            if kind == KIND_ASSET:
                data[CONF_CATEGORY] = user_input[CONF_CATEGORY]
            data[CONF_TOTAL_PRICE] = max(
                0.0, safe_float(user_input.get(CONF_TOTAL_PRICE, 0.0))
            )

            if kind not in (KIND_EVENT, KIND_SERVICE):
                data[CONF_IS_INSTALLMENT] = user_input.get(
                    CONF_IS_INSTALLMENT, False
                )
                data[CONF_INSTALLMENT_MONTHS] = user_input.get(
                    CONF_INSTALLMENT_MONTHS, 1
                )
                data[CONF_INSTALLMENT_INTEREST] = user_input.get(
                    CONF_INSTALLMENT_INTEREST, 0.0
                )

            options[CONF_SYNC_TO_CALENDAR] = user_input.get(
                CONF_SYNC_TO_CALENDAR, True
            )
            for key in (
                CONF_SUB_PERIOD,
                CONF_EXPIRATION_DATE,
                "anniversary_name",
                CONF_STORY,
                CONF_LOCATION,
                "is_wearing",
                CONF_LINKED_PRICE_ENTITY,
                CONF_EARLY_PAYOFF,
                CONF_EARLY_PAYOFF_FEE,
            ):
                if key in user_input:
                    options[key] = user_input[key]

            if kind == KIND_SERVICE:
                period_start = safe_date(data.get(CONF_PURCHASE_DATE), today_local())
                new_expiration = safe_date(options.get(CONF_EXPIRATION_DATE))
                old_expiration = safe_date(self.config_entry.options.get(CONF_EXPIRATION_DATE))
                period_changed = options.get(CONF_SUB_PERIOD) != self.config_entry.options.get(CONF_SUB_PERIOD)
                if options.get(CONF_SUB_PERIOD) == "自定义" and new_expiration is None:
                    errors[CONF_EXPIRATION_DATE] = "expiration_required"
                elif new_expiration and new_expiration < period_start:
                    errors[CONF_EXPIRATION_DATE] = "expiration_before_start"
                elif new_expiration and (new_expiration != old_expiration or period_changed):
                    options["service_period_start"] = str(period_start)
                    options["service_period_days"] = max(1, (new_expiration - period_start).days)

            if not errors:
                title_prefix = "💝 " if kind == KIND_EVENT else ""
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data=data,
                    options=options,
                    title=f"{title_prefix}{user_input[CONF_DEVICE_NAME]}",
                )
                return self.async_abort(reason="settings_saved")

        schema: dict[Any, Any] = {
            vol.Required(
                CONF_DEVICE_NAME, default=data.get(CONF_DEVICE_NAME, "")
            ): str,
            vol.Required(
                CONF_PURCHASE_DATE, default=data.get(CONF_PURCHASE_DATE)
            ): selector.DateSelector(),
            vol.Optional(
                CONF_SYNC_TO_CALENDAR,
                default=options.get(CONF_SYNC_TO_CALENDAR, True),
            ): bool,
        }
        if kind == KIND_ASSET:
            schema[
                vol.Required(
                    CONF_CATEGORY, default=data.get(CONF_CATEGORY, "其他类别")
                )
            ] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=ASSET_CATEGORIES,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )

        if kind != KIND_EVENT:
            schema[
                vol.Required(
                    CONF_TOTAL_PRICE,
                    default=safe_float(data.get(CONF_TOTAL_PRICE)),
                )
            ] = vol.All(vol.Coerce(float), vol.Range(min=0))

        if kind == KIND_SERVICE:
            schema[
                vol.Required(
                    CONF_SUB_PERIOD,
                    default=options.get(CONF_SUB_PERIOD, "1个月"),
                )
            ] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=SUB_PERIODS,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )
            schema[
                vol.Optional(
                    CONF_EXPIRATION_DATE,
                    default=options.get(CONF_EXPIRATION_DATE, ""),
                )
            ] = selector.DateSelector()
        elif kind in (KIND_MEMORIAL, KIND_EVENT):
            schema[
                vol.Optional(
                    "anniversary_name", default=options.get("anniversary_name", "")
                )
            ] = str

        if kind == KIND_MEMORIAL:
            schema[
                vol.Optional(CONF_STORY, default=options.get(CONF_STORY, ""))
            ] = selector.TextSelector(selector.TextSelectorConfig(multiline=True))
            schema[
                vol.Optional(CONF_LOCATION, default=options.get(CONF_LOCATION, ""))
            ] = str
            schema[
                vol.Optional("is_wearing", default=options.get("is_wearing", False))
            ] = bool
            schema[
                vol.Optional(
                    CONF_LINKED_PRICE_ENTITY,
                    default=options.get(CONF_LINKED_PRICE_ENTITY, ""),
                )
            ] = selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            )

        if kind not in (KIND_EVENT, KIND_SERVICE):
            schema[
                vol.Optional(
                    CONF_IS_INSTALLMENT,
                    default=data.get(CONF_IS_INSTALLMENT, False),
                )
            ] = bool
            schema[
                vol.Optional(
                    CONF_INSTALLMENT_MONTHS,
                    default=int(data.get(CONF_INSTALLMENT_MONTHS, 1)),
                )
            ] = vol.All(vol.Coerce(int), vol.Range(min=1, max=240))
            schema[
                vol.Optional(
                    CONF_INSTALLMENT_INTEREST,
                    default=safe_float(data.get(CONF_INSTALLMENT_INTEREST)),
                )
            ] = vol.All(vol.Coerce(float), vol.Range(min=0))
            schema[
                vol.Optional(
                    CONF_EARLY_PAYOFF,
                    default=options.get(CONF_EARLY_PAYOFF, False),
                )
            ] = bool
            schema[
                vol.Optional(
                    CONF_EARLY_PAYOFF_FEE,
                    default=safe_float(options.get(CONF_EARLY_PAYOFF_FEE)),
                )
            ] = vol.All(vol.Coerce(float), vol.Range(min=0))

        return self.async_show_form(
            step_id="edit_basic", data_schema=vol.Schema(schema), errors=errors
        )

    async def async_step_manage_acc_select(self, user_input=None):
        return await self._select_accessory(
            user_input, add_step="manage_acc_add", edit_step="manage_acc_edit", add_label="录入新配件"
        )

    async def async_step_manage_perk_select(self, user_input=None):
        return await self._select_accessory(
            user_input, add_step="manage_perk_add", edit_step="manage_perk_edit", add_label="录入新权益"
        )

    async def async_step_manage_mem_select(self, user_input=None):
        return await self._select_accessory(
            user_input, add_step="manage_mem_add", edit_step="manage_mem_edit", add_label="录入新纪念单品"
        )

    async def _select_accessory(self, user_input, *, add_step, edit_step, add_label):
        accessories = self._latest_options().get(CONF_ACCESSORIES_LIST, [])
        if user_input is not None:
            if user_input["selected_item"] == "ADD_NEW":
                return await getattr(self, f"async_step_{add_step}")()
            self._edit_acc_id = user_input["selected_item"]
            return await getattr(self, f"async_step_{edit_step}")()
        select_options = [{"value": "ADD_NEW", "label": f"➕ {add_label}"}]
        select_options.extend(
            {
                "value": item["id"],
                "label": f"{item.get('name', '未命名')} · {status_label(legacy_status(item))}",
            }
            for item in accessories
        )
        return self.async_show_form(
            step_id=add_step.replace("_add", "_select"),
            data_schema=vol.Schema(
                {
                    vol.Required("selected_item", default="ADD_NEW"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=select_options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
        )

    async def async_step_manage_acc_add(self, user_input=None):
        return await self._accessory_form("manage_acc_add", KIND_ASSET, user_input, add=True)

    async def async_step_manage_acc_edit(self, user_input=None):
        return await self._accessory_form("manage_acc_edit", KIND_ASSET, user_input, add=False)

    async def async_step_manage_perk_add(self, user_input=None):
        return await self._accessory_form("manage_perk_add", KIND_SERVICE, user_input, add=True)

    async def async_step_manage_perk_edit(self, user_input=None):
        return await self._accessory_form("manage_perk_edit", KIND_SERVICE, user_input, add=False)

    async def async_step_manage_mem_add(self, user_input=None):
        return await self._accessory_form("manage_mem_add", KIND_MEMORIAL, user_input, add=True)

    async def async_step_manage_mem_edit(self, user_input=None):
        return await self._accessory_form("manage_mem_edit", KIND_MEMORIAL, user_input, add=False)

    async def _accessory_form(self, step_id: str, kind: str, user_input, *, add: bool):
        options = self._latest_options()
        accessories = deepcopy(options.get(CONF_ACCESSORIES_LIST, []))
        current: dict[str, Any] = {}
        target_idx: int | None = None
        if not add:
            target_idx = next(
                (index for index, item in enumerate(accessories) if item.get("id") == self._edit_acc_id),
                None,
            )
            if target_idx is None:
                return self.async_abort(reason="item_not_found")
            current = accessories[target_idx]

        if user_input is not None:
            if user_input.get("delete_this", False) and target_idx is not None:
                accessories.pop(target_idx)
            else:
                item = deepcopy(current) if current else {"id": f"acc_{uuid.uuid4().hex[:12]}"}
                item.update(
                    {
                        "name": user_input["name"],
                        "price": max(0.0, safe_float(user_input.get("price"))),
                        "purchase_date": str(user_input["purchase_date"]),
                        "image": user_input.get("image", "").strip() or item.get("image", ""),
                    }
                )
                if kind == KIND_SERVICE:
                    item[CONF_EXPIRATION_DATE] = str(user_input.get(CONF_EXPIRATION_DATE, ""))
                elif kind == KIND_MEMORIAL:
                    item["is_wearing"] = user_input.get("is_wearing", False)
                else:
                    item.update(
                        {
                            CONF_IS_INSTALLMENT: user_input.get(CONF_IS_INSTALLMENT, False),
                            CONF_INSTALLMENT_MONTHS: user_input.get(CONF_INSTALLMENT_MONTHS, 1),
                            CONF_INSTALLMENT_INTEREST: user_input.get(CONF_INSTALLMENT_INTEREST, 0.0),
                            CONF_EARLY_PAYOFF: user_input.get(CONF_EARLY_PAYOFF, False),
                            CONF_EARLY_PAYOFF_FEE: user_input.get(CONF_EARLY_PAYOFF_FEE, 0.0),
                        }
                    )
                status = user_input.get(CONF_STATUS, legacy_status(item))
                item = normalize_status_record(
                    item,
                    status,
                    changed_at=today_local(),
                    recovery_amount=user_input.get("recovery_amount", 0.0),
                )
                if target_idx is None:
                    accessories.append(item)
                else:
                    accessories[target_idx] = item
            options[CONF_ACCESSORIES_LIST] = accessories
            return self.async_create_entry(data=options)

        schema: dict[Any, Any] = {
            vol.Required("name", default=current.get("name", "")): str,
            vol.Required("price", default=safe_float(current.get("price"))): vol.All(
                vol.Coerce(float), vol.Range(min=0)
            ),
            vol.Required(
                "purchase_date", default=current.get("purchase_date", str(today_local()))
            ): selector.DateSelector(),
            vol.Optional("image", default=current.get("image", "")): str,
        }
        if kind == KIND_SERVICE:
            schema[
                vol.Optional(
                    CONF_EXPIRATION_DATE,
                    default=current.get(CONF_EXPIRATION_DATE, ""),
                )
            ] = selector.DateSelector()
        elif kind == KIND_MEMORIAL:
            schema[
                vol.Optional("is_wearing", default=current.get("is_wearing", False))
            ] = bool
        else:
            schema[
                vol.Optional(
                    CONF_IS_INSTALLMENT,
                    default=current.get(CONF_IS_INSTALLMENT, False),
                )
            ] = bool
            schema[
                vol.Optional(
                    CONF_INSTALLMENT_MONTHS,
                    default=int(current.get(CONF_INSTALLMENT_MONTHS, 1)),
                )
            ] = vol.All(vol.Coerce(int), vol.Range(min=1, max=240))
            schema[
                vol.Optional(
                    CONF_INSTALLMENT_INTEREST,
                    default=safe_float(current.get(CONF_INSTALLMENT_INTEREST)),
                )
            ] = vol.All(vol.Coerce(float), vol.Range(min=0))
            schema[
                vol.Optional(
                    CONF_EARLY_PAYOFF,
                    default=current.get(CONF_EARLY_PAYOFF, False),
                )
            ] = bool
            schema[
                vol.Optional(
                    CONF_EARLY_PAYOFF_FEE,
                    default=safe_float(current.get(CONF_EARLY_PAYOFF_FEE)),
                )
            ] = vol.All(vol.Coerce(float), vol.Range(min=0))

        schema[
            vol.Optional(CONF_STATUS, default=legacy_status(current))
        ] = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=status_selector_options(kind, child=True),
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        )
        schema[
            vol.Optional(
                "recovery_amount", default=safe_float(current.get("recovery_amount"))
            )
        ] = vol.All(vol.Coerce(float), vol.Range(min=0))
        if not add:
            schema[vol.Optional("delete_this", default=False)] = bool
        return self.async_show_form(step_id=step_id, data_schema=vol.Schema(schema))

    async def async_step_edit_consumable_select(self, user_input=None):
        consumables = self._latest_options().get(CONF_CONSUMABLES_LIST, [])
        if not consumables:
            return self.async_abort(reason="no_consumables")
        if user_input is not None:
            self._edit_cons_id = user_input["selected_consumable"]
            return await self.async_step_edit_consumable_form()
        return self.async_show_form(
            step_id="edit_consumable_select",
            data_schema=vol.Schema(
                {
                    vol.Required("selected_consumable"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                {
                                    "value": item["id"],
                                    "label": f"{item.get('name', '耗材')} · ￥{safe_float(item.get('price')):.2f}",
                                }
                                for item in consumables
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
        )

    async def async_step_edit_consumable_form(self, user_input=None):
        return await self._consumable_form("edit_consumable_form", user_input, add=False)

    async def async_step_manage_consumable(self, user_input=None):
        return await self._consumable_form("manage_consumable", user_input, add=True)

    async def _consumable_form(self, step_id: str, user_input, *, add: bool):
        options = self._latest_options()
        consumables = deepcopy(options.get(CONF_CONSUMABLES_LIST, []))
        current: dict[str, Any] = {}
        target_idx: int | None = None
        if not add:
            target_idx = next(
                (index for index, item in enumerate(consumables) if item.get("id") == self._edit_cons_id),
                None,
            )
            if target_idx is None:
                return self.async_abort(reason="item_not_found")
            current = consumables[target_idx]

        prefix = "new_" if add else "edit_"
        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input.get("delete_this", False) and target_idx is not None:
                consumables.pop(target_idx)
            else:
                normalized = {
                    f"{prefix}name": user_input[f"{prefix}name"],
                    f"{prefix}price": user_input[f"{prefix}price"],
                    f"{prefix}cycle": user_input.get(f"{prefix}cycle", 0),
                    f"{prefix}start_date": user_input[f"{prefix}start_date"],
                    f"{prefix}image": user_input.get(f"{prefix}image", ""),
                    "tracking_mode": user_input["tracking_mode"],
                    CONF_LINKED_ENTITY: user_input.get(CONF_LINKED_ENTITY, ""),
                    CONF_AUTO_RECORD_REPLACEMENT: user_input.get(
                        CONF_AUTO_RECORD_REPLACEMENT, False
                    ),
                }
                errors = _validate_consumable_input(normalized, prefix=prefix)
                if not errors:
                    if add:
                        consumables.append(_new_consumable(normalized, prefix=prefix))
                    else:
                        item = deepcopy(current)
                        item.update(
                            {
                                "name": user_input[f"{prefix}name"],
                                "tracking_mode": user_input["tracking_mode"],
                                CONF_LINKED_ENTITY: user_input.get(CONF_LINKED_ENTITY, ""),
                                "price": max(0.0, safe_float(user_input[f"{prefix}price"])),
                                "cycle": max(0, int(safe_float(user_input.get(f"{prefix}cycle", 0)))),
                                "last_replace": str(user_input[f"{prefix}start_date"]),
                                "image": user_input.get(f"{prefix}image", "").strip()
                                or item.get("image", ""),
                                CONF_AUTO_RECORD_REPLACEMENT: user_input.get(
                                    CONF_AUTO_RECORD_REPLACEMENT, False
                                ),
                            }
                        )
                        consumables[target_idx] = item
            if not errors:
                options[CONF_CONSUMABLES_LIST] = consumables
                return self.async_create_entry(data=options)

        schema: dict[Any, Any] = {
            vol.Required(
                f"{prefix}name", default=current.get("name", "")
            ): str,
            vol.Required(
                "tracking_mode",
                default=current.get("tracking_mode", TRACKING_MODE_MANUAL),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=TRACKING_OPTIONS,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                CONF_LINKED_ENTITY, default=current.get(CONF_LINKED_ENTITY, "")
            ): selector.EntitySelector(),
            vol.Required(
                f"{prefix}price", default=safe_float(current.get("price"))
            ): vol.All(vol.Coerce(float), vol.Range(min=0)),
            vol.Optional(
                f"{prefix}cycle", default=int(current.get("cycle", 0))
            ): vol.All(vol.Coerce(int), vol.Range(min=0)),
            vol.Optional(
                f"{prefix}start_date",
                default=current.get("last_replace", str(today_local())),
            ): selector.DateSelector(),
            vol.Optional(
                CONF_AUTO_RECORD_REPLACEMENT,
                default=current.get(CONF_AUTO_RECORD_REPLACEMENT, False),
            ): bool,
            vol.Optional(
                f"{prefix}image", default=current.get("image", "")
            ): str,
        }
        if not add:
            schema[vol.Optional("delete_this", default=False)] = bool
        return self.async_show_form(
            step_id=step_id, data_schema=vol.Schema(schema), errors=errors
        )

    async def async_step_manage_lifecycle(self, user_input=None):
        options = self._latest_options()
        current_status = legacy_status(options)
        if user_input is not None:
            options.update(
                normalize_status_record(
                    options,
                    user_input[CONF_STATUS],
                    changed_at=today_local(),
                    recovery_amount=user_input.get("recovery_amount", 0.0),
                )
            )
            return self.async_create_entry(data=options)

        return self.async_show_form(
            step_id="manage_lifecycle",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_STATUS, default=current_status
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=status_selector_options(self._kind),
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Optional(
                        "recovery_amount",
                        default=safe_float(options.get("recovery_amount"))
                        if current_status == STATUS_SOLD
                        else 0.0,
                    ): vol.All(vol.Coerce(float), vol.Range(min=0)),
                }
            ),
        )
