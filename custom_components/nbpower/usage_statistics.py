"""Import NB Power daily usage into Home Assistant's long-term statistics.

The portal publishes whole-day totals, a day or so late. Exposed only as a
month-to-date sensor, the Energy dashboard attributes each jump to whenever
Home Assistant happened to poll. Importing the daily totals as external
statistics, stamped with the day they belong to, gives correct per-day bars.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
import logging
import re
from typing import Any

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
)
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import EnergyConverter

from .const import DOMAIN

try:  # Home Assistant 2025.11+ replaced ``has_mean`` with ``mean_type``
    from homeassistant.components.recorder.models import StatisticMeanType

    _MEAN_FIELDS: dict[str, Any] = {"mean_type": StatisticMeanType.NONE}
except ImportError:  # pragma: no cover - older Home Assistant
    _MEAN_FIELDS = {"has_mean": False}

_LOGGER = logging.getLogger(__name__)

# Days the portal marks "Validated" are final. Anything else may still be
# revised, so it is held back until it is validated or old enough to be stable.
IMPORT_STATUSES = {"validated"}
STALE_DAYS = 7


def _slug(value: Any) -> str:
    """Make a string safe for use in a statistic id."""
    return re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_") or "account"


def _day_start_utc(day: date) -> datetime:
    """Midnight at the start of ``day`` in the HA time zone, as UTC on the hour."""
    start = dt_util.as_utc(dt_util.start_of_local_day(day))
    return start.replace(minute=0, second=0, microsecond=0)


def _usable_value(row: dict, key: str, today: date) -> float | None:
    """Return the value to import for ``row``, or None if it is not final yet."""
    stale = row["date"] < today - timedelta(days=STALE_DAYS)
    final = str(row.get("status") or "").strip().lower() in IMPORT_STATUSES
    if not (final or stale):
        return None
    value = row.get(key)
    if value is None:
        return 0.0 if stale else None
    return float(value)


def build_statistics(
    rows: list[dict],
    key: str,
    *,
    today: date,
    last_start: datetime | None,
    base_sum: float,
) -> list[StatisticData]:
    """Turn daily rows into cumulative statistics newer than ``last_start``.

    Stops at the first day that is not final yet, so a day is never skipped
    and later imported out of order.
    """
    stats: list[StatisticData] = []
    running = base_sum
    for row in sorted(rows, key=lambda r: r["date"]):
        start = _day_start_utc(row["date"])
        if last_start is not None and start <= last_start:
            continue  # already imported
        value = _usable_value(row, key, today)
        if value is None:
            break
        running += value
        stats.append(StatisticData(start=start, state=value, sum=running))
    return stats


async def _async_import(
    hass: HomeAssistant,
    *,
    statistic_id: str,
    name: str,
    unit: str,
    unit_class: str | None,
    rows: list[dict],
    key: str,
    today: date,
) -> int:
    """Append any new daily rows to one statistic. Returns how many were added."""
    last = await get_instance(hass).async_add_executor_job(
        get_last_statistics, hass, 1, statistic_id, False, {"sum"}
    )
    last_start: datetime | None = None
    base_sum = 0.0
    if last.get(statistic_id):
        newest = last[statistic_id][0]
        base_sum = float(newest.get("sum") or 0.0)
        start = newest["start"]
        last_start = (
            start if isinstance(start, datetime) else dt_util.utc_from_timestamp(start)
        )

    stats = build_statistics(
        rows, key, today=today, last_start=last_start, base_sum=base_sum
    )
    if not stats:
        return 0

    metadata = StatisticMetaData(
        has_sum=True,
        name=name,
        source=DOMAIN,
        statistic_id=statistic_id,
        unit_of_measurement=unit,
        unit_class=unit_class,
        **_MEAN_FIELDS,
    )
    async_add_external_statistics(hass, metadata, stats)
    return len(stats)


async def async_import_daily_statistics(
    hass: HomeAssistant, account: Any, rows: list[dict], today: date
) -> None:
    """Import daily kWh and cost as external statistics for the Energy dashboard."""
    if not rows:
        _LOGGER.debug("NB Power returned no daily rows; nothing to import")
        return
    _LOGGER.debug(
        "NB Power daily rows: %d (%s to %s), statuses=%s",
        len(rows),
        rows[0]["date"],
        rows[-1]["date"],
        sorted({str(r.get("status")) for r in rows}),
    )
    slug = _slug(account)
    added_energy = await _async_import(
        hass,
        statistic_id=f"{DOMAIN}:{slug}_energy",
        name="NB Power energy",
        unit=UnitOfEnergy.KILO_WATT_HOUR,
        unit_class=EnergyConverter.UNIT_CLASS,
        rows=rows,
        key="kwh",
        today=today,
    )
    added_cost = await _async_import(
        hass,
        statistic_id=f"{DOMAIN}:{slug}_cost",
        name="NB Power cost",
        unit=hass.config.currency,
        unit_class=None,
        rows=rows,
        key="cost",
        today=today,
    )
    _LOGGER.debug(
        "NB Power statistics imported: %d energy days, %d cost days",
        added_energy,
        added_cost,
    )
