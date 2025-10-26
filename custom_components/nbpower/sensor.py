from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, time
import asyncio
import logging
from typing import Any, Iterable

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components.recorder.statistics import async_add_external_statistics
from homeassistant.components.sensor import (
    PLATFORM_SCHEMA as SENSOR_PLATFORM_SCHEMA,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_PASSWORD,
    CONF_USERNAME,
    CURRENCY_DOLLAR,
    UnitOfEnergy,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import NBPowerDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = SENSOR_PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)

@dataclass
class NBSensorDescription(SensorEntityDescription):
    attr_key: str = ""
    attributes_key: str | None = None

@dataclass
class NBPowerUsageStatisticDescription(SensorEntityDescription):
    dataset_key: str = ""
    value_key: str = "value"
    has_mean: bool = False
    has_sum: bool = True
    unit_class: str | None = None


SENSORS: list[NBSensorDescription] = [
    NBSensorDescription(
        key="mtd_kwh",
        name="NB Power MTD Energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        attr_key="so_far_kwh",
        attributes_key="summary",
    ),
    NBSensorDescription(
        key="mtd_cost",
        name="NB Power MTD Cost",
        native_unit_of_measurement=CURRENCY_DOLLAR,
        state_class=SensorStateClass.TOTAL,
        attr_key="so_far_dollars",
        attributes_key="summary",
    ),
    NBSensorDescription(
        key="projected_bill",
        name="NB Power Projected Bill",
        native_unit_of_measurement=CURRENCY_DOLLAR,
        state_class=SensorStateClass.MEASUREMENT,
        attr_key="projected_dollars",
        attributes_key="summary",
    ),
    NBSensorDescription(
        key="projected_kwh",
        name="NB Power Projected kWh",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        attr_key="projected_kwh",
        attributes_key="summary",
    ),
]


USAGE_STATISTIC_SENSORS: list[NBPowerUsageStatisticDescription] = [
    NBPowerUsageStatisticDescription(
        key="usage_15min_kwh",
        name="NB Power 15 Minute Energy",
        dataset_key="usage_15min_kwh",
        value_key="usage_kwh",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.MEASUREMENT,
        unit_class="energy",
    ),
    NBPowerUsageStatisticDescription(
        key="usage_15min_dollars",
        name="NB Power 15 Minute Cost",
        dataset_key="usage_15min_dollars",
        value_key="cost",
        native_unit_of_measurement=CURRENCY_DOLLAR,
        state_class=SensorStateClass.MEASUREMENT,
        has_sum=True,
    ),
    NBPowerUsageStatisticDescription(
        key="usage_hourly_kwh",
        name="NB Power Hourly Energy",
        dataset_key="usage_hourly_kwh",
        value_key="usage_kwh",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.MEASUREMENT,
        unit_class="energy",
    ),
    NBPowerUsageStatisticDescription(
        key="usage_hourly_dollars",
        name="NB Power Hourly Cost",
        dataset_key="usage_hourly_dollars",
        value_key="cost",
        native_unit_of_measurement=CURRENCY_DOLLAR,
        state_class=SensorStateClass.MEASUREMENT,
        has_sum=True,
    ),
    NBPowerUsageStatisticDescription(
        key="usage_daily_kwh",
        name="NB Power Daily Energy",
        dataset_key="usage_daily_kwh",
        value_key="usage_kwh",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.MEASUREMENT,
        unit_class="energy",
    ),
    NBPowerUsageStatisticDescription(
        key="usage_daily_dollars",
        name="NB Power Daily Cost",
        dataset_key="usage_daily_dollars",
        value_key="cost",
        native_unit_of_measurement=CURRENCY_DOLLAR,
        state_class=SensorStateClass.MEASUREMENT,
        has_sum=True,
    ),
    NBPowerUsageStatisticDescription(
        key="usage_monthly_kwh",
        name="NB Power Monthly Energy",
        dataset_key="usage_monthly_kwh",
        value_key="usage_kwh",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.MEASUREMENT,
        unit_class="energy",
    ),
    NBPowerUsageStatisticDescription(
        key="usage_monthly_dollars",
        name="NB Power Monthly Cost",
        dataset_key="usage_monthly_dollars",
        value_key="cost",
        native_unit_of_measurement=CURRENCY_DOLLAR,
        state_class=SensorStateClass.MEASUREMENT,
        has_sum=True,
    ),
]

#@dataclass
#class NBSensorDesc:
#    key: str
#    name: str
#    unit: str | None
#    device_class: SensorDeviceClass | None
#    state_class: SensorStateClass | None
#    attr_key: str
#    suggested_unit_of_measurement: str | None = None

#SENSORS: list[NBSensorDesc] = [
#    NBSensorDesc("mtd_kwh", "NB Power MTD Energy", UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, SensorStateClass.TOTAL, "so_far_kwh"),
#    NBSensorDesc("mtd_cost", "NB Power MTD Cost", CURRENCY_DOLLAR, None, SensorStateClass.TOTAL, "so_far_dollars"),
#    NBSensorDesc("projected_bill", "NB Power Projected Bill", CURRENCY_DOLLAR, None, SensorStateClass.MEASUREMENT, "projected_dollars"),
    # Optional extras — uncomment to enable more entities:
    # NBSensorDesc("projected_kwh", "NB Power Projected kWh", UnitOfEnergy.KILO_WATT_HOUR, SensorDeviceClass.ENERGY, SensorStateClass.MEASUREMENT, "projected_kwh"),
    # NBSensorDesc("peak_load_kw", "NB Power Peak Load", "kW", SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT, "peak_load_kw"),
    # NBSensorDesc("average_kw", "NB Power Average kW", "kW", SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT, "average_kw"),
    # NBSensorDesc("highest_kw", "NB Power Highest kW", "kW", SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT, "highest_kw"),
#]

async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Handle YAML configuration by importing it into the config flow."""
    _LOGGER.warning(
        "Configuring NB Power via YAML is deprecated; please use the UI "
        "(Settings → Devices & Services) instead."
    )
    hass.async_create_task(
        hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_IMPORT},
            data={
                CONF_USERNAME: config[CONF_USERNAME],
                CONF_PASSWORD: config[CONF_PASSWORD],
            },
        )
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up NB Power sensors for a config entry."""
    coordinator: NBPowerDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = [
        NBPowerSensor(coordinator, entry, description) for description in SENSORS
    ]
    entities.extend(
        NBPowerUsageStatisticSensor(coordinator, entry, description)
        for description in USAGE_STATISTIC_SENSORS
    )
    async_add_entities(entities)


class NBPowerSensor(CoordinatorEntity[NBPowerDataUpdateCoordinator], SensorEntity):
    """Representation of an NB Power sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: NBPowerDataUpdateCoordinator,
        entry: ConfigEntry,
        description: NBSensorDescription,
    ) -> None:
        """Initialize the NB Power sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title or "NB Power",
            manufacturer="NB Power",
        )

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        value = data.get(self.entity_description.attr_key)
        if isinstance(value, dict):
            return value.get("latest")
        return value

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data or {}
        attrs_key = getattr(self.entity_description, "attributes_key", None)
        if attrs_key:
            attrs_value = data.get(attrs_key)
            if isinstance(attrs_value, dict):
                return attrs_value
        return None


class NBPowerUsageStatisticSensor(
    CoordinatorEntity[NBPowerDataUpdateCoordinator], SensorEntity
):
    """Sensor that exposes usage statistics via Home Assistant's statistics API."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: NBPowerDataUpdateCoordinator,
        entry: ConfigEntry,
        description: NBPowerUsageStatisticDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title or "NB Power",
            manufacturer="NB Power",
        )
        self._imported: set[str] = set()
        self._metadata: dict[str, Any] | None = None
        self._import_lock = asyncio.Lock()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        await self._async_import_statistics()

    def _handle_coordinator_update(self) -> None:
        self.hass.async_create_task(self._async_import_statistics())
        super()._handle_coordinator_update()

    @property
    def _dataset(self) -> dict:
        data = self.coordinator.data or {}
        dataset = data.get(self.entity_description.dataset_key)
        if isinstance(dataset, dict):
            return dataset
        return {}

    @staticmethod
    def _coerce_float(value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            try:
                return float(text.replace(",", ""))
            except ValueError:
                return None
        return None

    def _extract_value(self, row: dict) -> float | None:
        value_keys: Iterable[str] = (
            self.entity_description.value_key,
            "value",
            "usage_kwh",
            "cost",
        )
        for key in value_keys:
            candidate = row.get(key)
            value = self._coerce_float(candidate)
            if value is not None:
                return value
        return None

    def _parse_start(self, row: dict) -> datetime | None:
        tzinfo = dt_util.get_time_zone(self.hass.config.time_zone)
        dt_text = row.get("datetime")
        if dt_text:
            parsed = dt_util.parse_datetime(dt_text)
            if parsed is None:
                try:
                    parsed = datetime.fromisoformat(dt_text)
                except (TypeError, ValueError):
                    return None
            if parsed.tzinfo is None:
                parsed = self._localize(parsed, tzinfo)
            return dt_util.as_utc(parsed)

        date_text = row.get("date")
        if not date_text:
            return None

        parsed_date = dt_util.parse_date(date_text)
        if parsed_date is None:
            try:
                parsed_date = datetime.fromisoformat(date_text).date()
            except (TypeError, ValueError):
                return None

        start_dt = datetime.combine(parsed_date, time.min)
        start_dt = self._localize(start_dt, tzinfo)
        return dt_util.as_utc(start_dt)

    def _current_row(self) -> dict | None:
        rows = self._dataset.get("rows") or []
        for row in reversed(rows):
            if self._extract_value(row) is not None:
                return row
        return None

    @property
    def native_value(self):
        row = self._current_row()
        if not row:
            return None
        return self._extract_value(row)

    @property
    def extra_state_attributes(self):
        row = self._current_row()
        if not row:
            return None
        attrs: dict[str, Any] = {}
        if row.get("datetime"):
            attrs["last_period_start"] = row["datetime"]
        elif row.get("date"):
            attrs["last_period_start"] = row["date"]
        if row.get("label"):
            attrs["last_period_label"] = row["label"]
        return attrs or None

    def _build_metadata(self) -> dict[str, Any]:
        if self._metadata is not None:
            return self._metadata
        if not self.entity_id:
            raise RuntimeError("Entity ID not assigned yet")
        description = self.entity_description
        metadata: dict[str, Any] = {
            "has_mean": description.has_mean,
            "has_sum": description.has_sum,
            "name": description.name,
            "source": DOMAIN,
            "statistic_id": self.entity_id,
            "unit_of_measurement": description.native_unit_of_measurement,
        }
        if description.unit_class:
            metadata["unit_class"] = description.unit_class
        self._metadata = metadata
        return metadata

    def _localize(self, dt_obj: datetime, tzinfo) -> datetime:
        if tzinfo is None:
            return dt_obj.replace(tzinfo=dt_util.UTC)
        localize = getattr(tzinfo, "localize", None)
        if callable(localize):
            return localize(dt_obj)
        return dt_obj.replace(tzinfo=tzinfo)

    async def _async_import_statistics(self) -> None:
        if not self.entity_id:
            return

        async with self._import_lock:
            dataset = self._dataset
            rows = dataset.get("rows") or []
            if not rows:
                return

            stats: list[dict[str, Any]] = []
            new_keys: set[str] = set()
            for row in rows:
                key = row.get("key") or ""
                marker = key or row.get("datetime") or row.get("date")
                if marker and marker in self._imported:
                    continue
                start = self._parse_start(row)
                if start is None:
                    continue
                value = self._extract_value(row)
                if value is None:
                    continue
                stats.append(
                    {
                        "start": start,
                        "sum": value,
                        "state": value,
                    }
                )
                if marker:
                    new_keys.add(marker)

            if not stats:
                return

            stats.sort(key=lambda item: item["start"])

            metadata = self._build_metadata()
            await async_add_external_statistics(self.hass, metadata, stats)
            self._imported.update(new_keys)
