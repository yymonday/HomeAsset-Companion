"""Constants for HomeAsset Companion."""

from __future__ import annotations

DOMAIN = "device_companion"
INTEGRATION_VERSION = "1.1.1"
DATA_LOCKS = "entry_locks"

CONF_DEVICE_NAME = "device_name"
CONF_PURCHASE_DATE = "purchase_date"
CONF_TOTAL_PRICE = "total_price"
CONF_IS_INSTALLMENT = "is_installment"
CONF_INSTALLMENT_MONTHS = "installment_months"
CONF_INSTALLMENT_INTEREST = "installment_interest"
CONF_EARLY_PAYOFF = "early_payoff"
CONF_EARLY_PAYOFF_FEE = "early_payoff_fee"
CONF_DEVICE_IMAGE = "device_image"
CONF_CATEGORY = "category"
CONF_KIND = "kind"
CONF_EXPIRATION_DATE = "expiration_date"
CONF_SUB_PERIOD = "sub_period"
CONF_CURRENT_PERIOD_COST = "current_period_cost"
CONF_SCHEMA_VERSION = "schema_version"

CONF_CONSUMABLE_NAME = "consumable_name"
CONF_CONSUMABLE_PRICE = "consumable_price"
CONF_CONSUMABLE_CYCLE = "consumable_cycle"
CONF_CONSUMABLE_IMAGE = "consumable_image"
CONF_CONSUMABLE_START_DATE = "consumable_start_date"
CONF_CONSUMABLES_LIST = "consumables_list"
CONF_TRACKING_MODE = "tracking_mode"
CONF_LINKED_ENTITY = "linked_entity"
CONF_AUTO_RECORD_REPLACEMENT = "auto_record_replacement"

TRACKING_MODE_MANUAL = "manual"
TRACKING_MODE_SMART = "smart_percent"

CONF_ACCESSORIES_LIST = "accessories_list"
CONF_STORY = "story"
CONF_LOCATION = "location"
CONF_LINKED_PRICE_ENTITY = "linked_price_entity"
CONF_IS_EVENT = "is_event"
CONF_SYNC_TO_CALENDAR = "sync_to_calendar"

CONF_STATUS = "status"
CONF_STATUS_CHANGED_AT = "status_changed_at"
CONF_RECOVERY_AMOUNT = "recovery_amount"

KIND_ASSET = "asset"
KIND_SERVICE = "service"
KIND_MEMORIAL = "memorial"
KIND_EVENT = "event"

STATUS_ACTIVE = "active"
STATUS_IDLE = "idle"
STATUS_ARCHIVED = "archived"
STATUS_SOLD = "sold"
STATUS_SCRAPPED = "scrapped"
STATUS_LOST = "lost"
STATUS_GIFTED = "gifted"
STATUS_CANCELED = "canceled"
STATUS_EXPIRED = "expired"  # Derived status; not normally persisted.

TERMINAL_STATUSES = {
    STATUS_ARCHIVED,
    STATUS_SOLD,
    STATUS_SCRAPPED,
    STATUS_LOST,
    STATUS_GIFTED,
    STATUS_CANCELED,
}

STATUS_LABELS = {
    STATUS_ACTIVE: "正常使用",
    STATUS_IDLE: "闲置持有",
    STATUS_ARCHIVED: "已封存",
    STATUS_SOLD: "二手售出",
    STATUS_SCRAPPED: "已报废",
    STATUS_LOST: "已遗失",
    STATUS_GIFTED: "已赠出",
    STATUS_CANCELED: "已取消",
    STATUS_EXPIRED: "已到期",
}

LEGACY_REASON_TO_STATUS = {
    "✨ 正常服役": STATUS_ACTIVE,
    "✨ 正常陪伴/佩戴中": STATUS_ACTIVE,
    "✨ 正常生效": STATUS_ACTIVE,
    "正常服役": STATUS_ACTIVE,
    "正常": STATUS_ACTIVE,
    "光荣闲置": STATUS_IDLE,
    "封存": STATUS_ARCHIVED,
    "已封存": STATUS_ARCHIVED,
    "二手回血": STATUS_SOLD,
    "光荣报废": STATUS_SCRAPPED,
    "报废": STATUS_SCRAPPED,
    "意外遗失": STATUS_LOST,
    "遗失": STATUS_LOST,
    "馈赠他人": STATUS_GIFTED,
    "赠出": STATUS_GIFTED,
    "已取消/未续订": STATUS_CANCELED,
    "已失效": STATUS_CANCELED,
}

STATUS_TO_LEGACY_REASON = {
    STATUS_ACTIVE: "✨ 正常服役",
    STATUS_IDLE: "光荣闲置",
    STATUS_ARCHIVED: "已封存",
    STATUS_SOLD: "二手回血",
    STATUS_SCRAPPED: "光荣报废",
    STATUS_LOST: "意外遗失",
    STATUS_GIFTED: "馈赠他人",
    STATUS_CANCELED: "已取消/未续订",
    STATUS_EXPIRED: "已失效",
}
