"""Utilities for storing and normalizing NB Power usage data."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Dict, Iterable, List, Optional, Tuple

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

STORAGE_VERSION = 1
STORAGE_KEY_TEMPLATE = "nbpower_usage_{entry_id}"

MODE_SETTINGS: dict[str, dict[str, int]] = {
    "Mi": {
        "backfill_days": 7,
        "chunk_days": 1,
        "max_periods": 14,
    },
    "H": {
        "backfill_days": 60,
        "chunk_days": 7,
        "max_periods": 120,
    },
    "D": {
        "backfill_days": 400,
        "chunk_days": 30,
        "max_periods": 450,
    },
    "M": {
        "backfill_months": 48,
        "chunk_months": 12,
        "max_periods": 60,
    },
}

_NUMBER_FORMATS = [
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%B %d, %Y",
    "%b %d, %Y",
    "%d-%b-%Y",
    "%B %Y",
    "%b %Y",
    "%Y",
]

_TIME_FORMATS = [
    "%H:%M",
    "%H:%M:%S",
    "%I:%M %p",
    "%I %p",
    "%H",
]


def _to_float(value) -> Optional[float]:
    """Attempt to coerce a value to float."""

    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text.replace(",", ""))
    except (TypeError, ValueError):
        return None


def _first_day_of_month(day: date) -> date:
    return day.replace(day=1)


def _last_day_of_month(day: date) -> date:
    next_month = _add_months(_first_day_of_month(day), 1)
    return next_month - timedelta(days=1)


def _add_months(day: date, months: int) -> date:
    """Return ``day`` moved forward ``months`` months."""

    month = day.month - 1 + months
    year = day.year + month // 12
    month = month % 12 + 1
    day_num = min(
        day.day,
        [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][
            month - 1
        ],
    )
    return date(year, month, day_num)


def _parse_usage_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    text = value.strip()
    for fmt in _NUMBER_FORMATS:
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.date()
        except ValueError:
            continue
    return None


def _parse_usage_datetime(mode: str, row: dict) -> Tuple[Optional[datetime], Optional[str]]:
    usage_date = _parse_usage_date(row.get("UsageDate"))
    if usage_date is None:
        usage_date = _parse_usage_date(row.get("FromDate"))
    if usage_date is None:
        usage_date = _parse_usage_date(row.get("ToDate"))

    label = row.get("Hourly") or row.get("Hour") or row.get("UsageHour")
    label = label or row.get("UsageTime") or row.get("Time")

    if usage_date is None:
        return None, label

    if mode not in {"Mi", "H"}:
        return datetime.combine(usage_date, time()), label

    if not label:
        return datetime.combine(usage_date, time()), label

    for fmt in _TIME_FORMATS:
        try:
            parsed = datetime.strptime(label, fmt)
            return datetime.combine(usage_date, parsed.time()), label
        except ValueError:
            continue

    return datetime.combine(usage_date, time()), label


def _default_label(row: dict, fallback: Optional[str]) -> str:
    return (
        row.get("Hourly")
        or row.get("Hour")
        or row.get("UsageHour")
        or row.get("UsageTime")
        or row.get("Time")
        or row.get("UsageDate")
        or fallback
        or ""
    )


@dataclass
class NormalizedRow:
    key: str
    data: dict
    date_iso: Optional[str]


class UsageDataset:
    """Collection of normalized usage rows for a mode/type pair."""

    def __init__(self, mode: str, rtype: str, max_periods: int) -> None:
        self.mode = mode
        self.rtype = rtype
        self.max_periods = max_periods
        self._rows: Dict[str, dict] = {}
        self._date_map: Dict[str, set[str]] = {}
        self.updated_at: Optional[str] = None

    @property
    def is_empty(self) -> bool:
        return not self._rows

    def _ensure_date_entry(self, date_iso: str, key: str) -> None:
        self._date_map.setdefault(date_iso, set()).add(key)

    def add_rows(self, rows: Iterable[NormalizedRow]) -> bool:
        changed = False
        for item in rows:
            if not item.key:
                continue
            row = dict(item.data)
            existing = self._rows.get(item.key)
            if existing == row:
                continue
            self._rows[item.key] = row
            if item.date_iso:
                self._ensure_date_entry(item.date_iso, item.key)
            changed = True
        if changed:
            if self._trim_excess():
                changed = True
            self.updated_at = dt_util.utcnow().isoformat()
        return changed

    def _trim_excess(self) -> bool:
        if self.max_periods <= 0:
            return False
        changed = False
        while len(self._date_map) > self.max_periods:
            oldest = min(self._date_map)
            keys = self._date_map.pop(oldest, set())
            for key in keys:
                if key in self._rows:
                    self._rows.pop(key)
                    changed = True
        return changed

    def latest_date(self) -> Optional[date]:
        if not self._date_map:
            return None
        return date.fromisoformat(max(self._date_map))

    def next_start_date(self) -> Optional[date]:
        last = self.latest_date()
        if last is None:
            return None
        if self.mode == "M":
            return _add_months(last, 1).replace(day=1)
        return last + timedelta(days=1)

    def rows_for_date(self, date_iso: str) -> List[dict]:
        keys = self._date_map.get(date_iso, set())
        return [self._rows[k] for k in keys if k in self._rows]

    def first_row_for_date(self, date_iso: str) -> Optional[dict]:
        rows = self.rows_for_date(date_iso)
        if not rows:
            return None
        rows_sorted = sorted(rows, key=lambda r: r.get("sort_key") or "")
        return rows_sorted[0]

    def latest_row(self) -> Optional[dict]:
        if not self._rows:
            return None
        key = max(self._rows, key=lambda k: self._rows[k].get("sort_key") or k)
        return self._rows[key]

    def to_storage(self) -> dict:
        date_map = {k: sorted(v) for k, v in self._date_map.items()}
        rows = []
        for key, row in self._rows.items():
            payload = dict(row)
            payload["key"] = key
            rows.append(payload)
        return {
            "mode": self.mode,
            "type": self.rtype,
            "max_periods": self.max_periods,
            "rows": rows,
            "date_map": date_map,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_storage(cls, mode: str, rtype: str, data: dict, default_max: int) -> "UsageDataset":
        dataset = cls(mode, rtype, data.get("max_periods", default_max))
        dataset.updated_at = data.get("updated_at")
        rows = data.get("rows", [])
        for row in rows:
            key = row.get("key")
            if not key:
                continue
            stored = dict(row)
            stored.pop("key", None)
            if "sort_key" not in stored:
                if stored.get("datetime"):
                    stored["sort_key"] = stored["datetime"]
                elif stored.get("date"):
                    stored["sort_key"] = f"{stored['date']}T00:00:00"
            dataset._rows[key] = stored
        date_map = data.get("date_map", {})
        for date_iso, keys in date_map.items():
            dataset._date_map[date_iso] = set(keys)
        return dataset

    def as_dict(self) -> dict:
        rows = []
        for key in sorted(self._rows, key=lambda k: self._rows[k].get("sort_key") or k):
            row = {k: v for k, v in self._rows[key].items() if k != "sort_key"}
            row["key"] = key
            rows.append(row)
        dates = sorted(self._date_map)
        latest_row = rows[-1] if rows else None
        latest_marker = None
        if latest_row:
            latest_marker = latest_row.get("datetime") or latest_row.get("date")
        unit = "kWh" if self.rtype == "K" else "$"
        return {
            "mode": self.mode,
            "type": self.rtype,
            "unit": unit,
            "rows": rows,
            "dates": dates,
            "updated_at": self.updated_at,
            "latest": latest_marker,
        }


def _normalize_row(mode: str, rtype: str, row: dict) -> Optional[NormalizedRow]:
    dt_val, label = _parse_usage_datetime(mode, row)
    date_iso = dt_val.date().isoformat() if dt_val else None
    sort_key = dt_val.isoformat() if dt_val else None
    usage = _to_float(row.get("UsageValue"))
    if usage is None:
        usage = _to_float(row.get("Consumption"))
    demand = _to_float(row.get("DemandValue"))
    amount = _to_float(row.get("Amount"))
    billing_days = _to_float(row.get("BillingDays"))

    if rtype == "D":
        primary = _to_float(row.get("UsageValue"))
        if primary is None:
            primary = amount
        value = primary
        cost = primary
        usage_kwh = _to_float(row.get("Consumption"))
    else:
        value = usage
        cost = amount
        usage_kwh = usage

    key = None
    if sort_key:
        key = sort_key
    elif date_iso:
        suffix = _default_label(row, label).replace(" ", "_")
        key = f"{date_iso}|{suffix}"
    label_text = _default_label(row, label)

    normalized = {
        "date": date_iso,
        "datetime": sort_key,
        "label": label_text,
        "value": value,
        "usage_kwh": usage_kwh,
        "demand_kw": demand,
        "cost": cost,
        "billing_days": billing_days,
        "status": row.get("ValidationStatus"),
        "sort_key": sort_key or (f"{date_iso}T00:00:00" if date_iso else None),
    }

    if value is None and usage_kwh is None and cost is None:
        return None

    return NormalizedRow(key=key or "", data=normalized, date_iso=date_iso)


def normalize_payload(mode: str, rtype: str, payload: dict) -> List[NormalizedRow]:
    if not payload:
        return []
    data = payload.get("data") or {}
    rows = data.get("objUsageGenerationResultSetTwo") or []
    normalized: List[NormalizedRow] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        norm = _normalize_row(mode, rtype, row)
        if norm is not None:
            normalized.append(norm)
    return normalized


class UsageStore:
    """Persistent store for usage datasets."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._hass = hass
        self._entry_id = entry_id
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY_TEMPLATE.format(entry_id=entry_id))
        self._datasets: Dict[Tuple[str, str], UsageDataset] = {}
        self._loaded = False

    async def async_load(self) -> None:
        if self._loaded:
            return
        data = await self._store.async_load() or {}
        datasets = data.get("datasets", {})
        for key, stored in datasets.items():
            mode, rtype = key.split("|", 1)
            settings = MODE_SETTINGS.get(mode, {})
            dataset = UsageDataset.from_storage(mode, rtype, stored, settings.get("max_periods", 0))
            self._datasets[(mode, rtype)] = dataset
        self._loaded = True

    async def async_save(self) -> None:
        payload = {
            "datasets": {
                f"{mode}|{rtype}": dataset.to_storage()
                for (mode, rtype), dataset in self._datasets.items()
            }
        }
        await self._store.async_save(payload)

    def get_dataset(self, mode: str, rtype: str) -> UsageDataset:
        key = (mode, rtype)
        if key not in self._datasets:
            settings = MODE_SETTINGS.get(mode, {})
            dataset = UsageDataset(mode, rtype, settings.get("max_periods", 0))
            self._datasets[key] = dataset
        return self._datasets[key]

    def determine_fetch_ranges(self, mode: str, rtype: str, today: date) -> List[Tuple[date, date]]:
        dataset = self.get_dataset(mode, rtype)
        ranges: List[Tuple[date, date]] = []
        settings = MODE_SETTINGS.get(mode, {})

        if mode == "M":
            start = dataset.next_start_date()
            if start is None:
                months = max(settings.get("backfill_months", 1), 1)
                start = _add_months(_first_day_of_month(today), -(months - 1))
            start = _first_day_of_month(start)
            chunk_months = max(settings.get("chunk_months", 12), 1)
            current = start
            month_limit = _first_day_of_month(today)
            while current <= month_limit:
                chunk_end_month = _add_months(current, chunk_months)
                last_month = _add_months(current, chunk_months - 1)
                end_date = _last_day_of_month(last_month)
                if end_date > today:
                    end_date = today
                if end_date >= current:
                    ranges.append((current, end_date))
                current = chunk_end_month
            return ranges

        start = dataset.next_start_date()
        if start is None:
            backfill_days = max(settings.get("backfill_days", 1), 1)
            start = today - timedelta(days=backfill_days - 1)
        if start > today:
            return []
        chunk_days = max(settings.get("chunk_days", 7), 1)
        current = start
        while current <= today:
            end = min(current + timedelta(days=chunk_days - 1), today)
            ranges.append((current, end))
            current = end + timedelta(days=1)
        return ranges

    def add_payload(self, mode: str, rtype: str, payload: dict) -> bool:
        dataset = self.get_dataset(mode, rtype)
        rows = normalize_payload(mode, rtype, payload)
        if not rows:
            return False
        return dataset.add_rows(rows)

    def datasets_for_sensors(self) -> Dict[Tuple[str, str], dict]:
        return {
            key: dataset.as_dict()
            for key, dataset in self._datasets.items()
        }

    def latest_daily_summary(self) -> dict:
        dataset_k = self.get_dataset("D", "K")
        latest = dataset_k.latest_row()
        if not latest:
            return {}
        date_iso = latest.get("date")
        usage_kwh = latest.get("usage_kwh") or latest.get("value")
        cost = latest.get("cost")
        if cost is None and date_iso:
            dataset_d = self.get_dataset("D", "D")
            alt = dataset_d.first_row_for_date(date_iso)
            if alt:
                cost = alt.get("value") or alt.get("cost")
        summary = {
            "date": date_iso,
            "usage_kwh": usage_kwh,
            "cost": cost,
        }
        if latest.get("datetime"):
            summary["datetime"] = latest["datetime"]
        summary["status"] = latest.get("status")
        return summary
