from __future__ import annotations
from dataclasses import dataclass
import logging

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
    PLATFORM_SCHEMA as SENSOR_PLATFORM_SCHEMA,
)
from homeassistant.components.sensor import SensorEntityDescription
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

SENSORS: list[NBSensorDescription] = [
    NBSensorDescription(
        key="mtd_kwh",
        name="NB Power MTD Energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        attr_key="so_far_kwh",
    ),
    NBSensorDescription(
        key="mtd_cost",
        name="NB Power MTD Cost",
        native_unit_of_measurement=CURRENCY_DOLLAR,
        state_class=SensorStateClass.TOTAL,
        attr_key="so_far_dollars",
    ),
    NBSensorDescription(
        key="projected_bill",
        name="NB Power Projected Bill",
        native_unit_of_measurement=CURRENCY_DOLLAR,
        state_class=SensorStateClass.MEASUREMENT,
        attr_key="projected_dollars",
    ),
    # Optional extras:
    NBSensorDescription(
        key="projected_kwh",
        name="NB Power Projected kWh",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        attr_key="projected_kwh",
    ),
    NBSensorDescription(
        key="last_day_kwh",
        name="NB Power Previous Day Energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.MEASUREMENT,
        attr_key="mi_last_total_kwh",
    ),
    NBSensorDescription(
        key="last_day_cost",
        name="NB Power Previous Day Cost",
        native_unit_of_measurement=CURRENCY_DOLLAR,
        state_class=SensorStateClass.MEASUREMENT,
        attr_key="mi_last_total_cost",
    ),
    # NBSensorDescription(
    #     key="peak_load_kw",
    #     name="NB Power Peak Load",
    #     native_unit_of_measurement="kW",
    #     state_class=SensorStateClass.MEASUREMENT,
    #     attr_key="peak_load_kw",
    # ),
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
    entities = [NBPowerSensor(coordinator, entry, description) for description in SENSORS]
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
        return data.get(self.entity_description.attr_key)

    @property
    def extra_state_attributes(self):
        # expose the entire tentative block for debugging/graphs
        return self.coordinator.data or {}
