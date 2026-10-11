"""Shared helpers for HomeAsset Companion."""

from __future__ import annotations

import calendar
import math
from copy import deepcopy
from datetime import date, datetime
from typing import Any

from homeassistant.util import dt as dt_util

from .const import (
    CONF_CATEGORY,
    CONF_EXPIRATION_DATE,
    CONF_FOLLOW_MAIN_RENEWAL,
    CONF_IS_EVENT,
    CONF_KIND,
    CONF_RECOVERY_AMOUNT,
    CONF_STATUS,
    CONF_STATUS_CHANGED_AT,
    KIND_ASSET,
    KIND_EVENT,
    KIND_MEMORIAL,
    KIND_SERVICE,
    LEGACY_REASON_TO_STATUS,
    STATUS_ACTIVE,
    STATUS_CANCELED,
    STATUS_IDLE,
    STATUS_LABELS,
    STATUS_SOLD,
    STATUS_TO_LEGACY_REASON,
    TERMINAL_STATUSES,
)


def today_local() -> date:
    """Return the Home Assistant local date."""
    return dt_util.now().date()


def safe_float(value: Any, default: float = 0.0) -> float:
    """Convert a value to float without raising."""
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError, OverflowError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    """Convert a value to int without raising."""
    try:
        return int(float(value))
    except (TypeError, ValueError, OverflowError):
        return default


def safe_record_list(value: Any) -> list[dict[str, Any]]:
    """Return only mapping records from a persisted list-like value."""
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def safe_date(value: Any, default: date | None = None) -> date | None:
    """Parse a date-like value."""
    if value in (None, ""):
        return default
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value).split("T", maxsplit=1)[0], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return default


def add_months_to_date(value: date, months: int) -> date:
    """Add calendar months while preserving the last valid day."""
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def effective_service_records(options: dict[str, Any], field: str) -> list[dict[str, Any]]:
    """Apply the latest linked date revision without overwriting audit sources."""
    revisions = {}
    for adjustment in safe_record_list(options.get("service_adjustments")):
        bill_id = adjustment.get("bill_id")
        correction = adjustment.get("date_correction")
        if not isinstance(bill_id, str) or adjustment.get("operation") != "correction" or not isinstance(correction, dict):
            continue
        after = correction.get("after")
        if not isinstance(after, dict):
            continue
        dates = {key: safe_date(after.get(key)) for key in ("paid_at", "period_start", "period_end")}
        if any(value is None for value in dates.values()) or dates["period_end"] < dates["period_start"]:
            continue
        revisions[bill_id] = {key: str(value) for key, value in dates.items()}
    records = []
    for source in safe_record_list(options.get(field)):
        record = dict(source)
        if isinstance(source.get("id"), str) and source["id"] in revisions:
            record.update(revisions[source["id"]])
        records.append(record)
    return records


def infer_kind(data: dict[str, Any]) -> str:
    """Infer the stable business kind from legacy entry data."""
    if data.get(CONF_KIND):
        return str(data[CONF_KIND])
    if data.get(CONF_IS_EVENT) or data.get(CONF_CATEGORY) == "纪念事件":
        return KIND_EVENT
    category = data.get(CONF_CATEGORY)
    if category == "虚拟服务":
        return KIND_SERVICE
    if category == "纪念珍藏":
        return KIND_MEMORIAL
    return KIND_ASSET


def legacy_status(record: dict[str, Any], *, default: str = STATUS_ACTIVE) -> str:
    """Read canonical status from current or legacy fields."""
    raw_status = record.get(CONF_STATUS)
    if raw_status:
        return str(raw_status)
    reason = str(record.get("retirement_reason", "")).strip()
    if reason in LEGACY_REASON_TO_STATUS:
        return LEGACY_REASON_TO_STATUS[reason]
    if record.get("is_retired"):
        return STATUS_CANCELED if "取消" in reason or "失效" in reason else "archived"
    return default


def status_label(status: str) -> str:
    """Return localized label for a lifecycle status."""
    return STATUS_LABELS.get(status, status)


def is_terminal_status(status: str) -> bool:
    """Return whether a status freezes lifecycle time and active costs."""
    return status in TERMINAL_STATUSES


def perk_period(item: dict[str, Any], options: dict[str, Any]) -> tuple[date | None, date | None]:
    """Read a gift's period; a missing end date retains legacy parent inheritance."""
    start = safe_date(item.get("service_period_start"), safe_date(item.get("purchase_date")))
    end = safe_date(item.get(CONF_EXPIRATION_DATE))
    if not item.get(CONF_EXPIRATION_DATE) and item.get(CONF_FOLLOW_MAIN_RENEWAL, True):
        start = safe_date(options.get("service_period_start"), start)
        end = safe_date(options.get(CONF_EXPIRATION_DATE))
        purchase = safe_date(item.get("purchase_date"))
        if purchase and start:
            start = max(start, purchase)
    return start, end


def renew_perk_record(item: dict[str, Any], start: date, end: date, *,
                      follow_main: bool, changed_at: date, source: str) -> dict[str, Any]:
    """Replace only the active gift period, retaining acquisition and date history."""
    result = normalize_status_record(item, STATUS_ACTIVE, changed_at=changed_at)
    before = {"period_start": item.get("service_period_start", item.get("purchase_date", "")),
              "period_end": item.get(CONF_EXPIRATION_DATE, "")}
    after = {"period_start": str(start), "period_end": str(end)}
    if before != after:
        history = deepcopy(safe_record_list(item.get("renewal_history")))
        history.append({"before": before, "after": after,
                        "recorded_at": str(changed_at), "source": source})
        result["renewal_history"] = history
    result["service_period_start"] = str(start)
    result[CONF_EXPIRATION_DATE] = str(end)
    result[CONF_FOLLOW_MAIN_RENEWAL] = follow_main
    return result


def normalize_status_record(
    record: dict[str, Any],
    status: str,
    *,
    changed_at: date | None = None,
    recovery_amount: float | None = None,
) -> dict[str, Any]:
    """Write canonical and legacy-compatible lifecycle fields."""
    normalized = deepcopy(record)
    previous = legacy_status(normalized)
    normalized[CONF_STATUS] = status

    if status != previous:
        normalized[CONF_STATUS_CHANGED_AT] = str(changed_at or today_local())
    elif CONF_STATUS_CHANGED_AT not in normalized and normalized.get("retirement_date"):
        normalized[CONF_STATUS_CHANGED_AT] = normalized.get("retirement_date")

    normalized["is_retired"] = is_terminal_status(status)
    normalized["retirement_reason"] = STATUS_TO_LEGACY_REASON.get(
        status, STATUS_TO_LEGACY_REASON[STATUS_ACTIVE]
    )

    if is_terminal_status(status):
        normalized["retirement_date"] = normalized.get(CONF_STATUS_CHANGED_AT) or str(
            changed_at or today_local()
        )
    else:
        normalized.pop("retirement_date", None)

    if status == STATUS_SOLD:
        normalized[CONF_RECOVERY_AMOUNT] = max(
            0.0,
            safe_float(
                recovery_amount
                if recovery_amount is not None
                else normalized.get(CONF_RECOVERY_AMOUNT, 0.0)
            ),
        )
    else:
        normalized[CONF_RECOVERY_AMOUNT] = 0.0

    return normalized


def allowed_statuses(kind: str, *, child: bool = False) -> list[str]:
    """Return lifecycle statuses allowed by business kind."""
    if kind == KIND_SERVICE:
        return [STATUS_ACTIVE, STATUS_CANCELED]
    if kind == KIND_EVENT:
        return [STATUS_ACTIVE, "archived"]
    if kind == KIND_MEMORIAL:
        return [
            STATUS_ACTIVE,
            STATUS_IDLE,
            "archived",
            STATUS_SOLD,
            "lost",
            "gifted",
        ]
    return [
        STATUS_ACTIVE,
        STATUS_IDLE,
        "archived",
        STATUS_SOLD,
        "scrapped",
        "lost",
        "gifted",
    ]


def status_selector_options(kind: str, *, child: bool = False) -> list[dict[str, str]]:
    """Return Home Assistant selector options for statuses."""
    return [
        {"value": status, "label": STATUS_LABELS[status]}
        for status in allowed_statuses(kind, child=child)
    ]
