"""NB Power integration setup."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import NBPowerClient
from .const import (
    CONF_ACCOUNT_NUMBER,
    CONF_METER_NUMBER,
    CONF_SCAN_INTERVAL,
    CONF_UTILITY_ACCOUNT_NUMBER,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)
from .coordinator import NBPowerDataUpdateCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the NB Power integration."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up NB Power from a config entry."""
    data = dict(entry.data)
    updated = False

    scan_interval = max(data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL), MIN_SCAN_INTERVAL)
    if scan_interval != data.get(CONF_SCAN_INTERVAL):
        data[CONF_SCAN_INTERVAL] = scan_interval
        updated = True

    if not data.get(CONF_ACCOUNT_NUMBER) or not data.get(CONF_UTILITY_ACCOUNT_NUMBER) or CONF_METER_NUMBER not in data:
        client = NBPowerClient(async_get_clientsession(hass))
        await client.ensure_bootstrap(data[CONF_USERNAME], data[CONF_PASSWORD])
        data[CONF_ACCOUNT_NUMBER] = client.account_number or ""
        data[CONF_UTILITY_ACCOUNT_NUMBER] = client.utility_account_number or ""
        data[CONF_METER_NUMBER] = client.meter_number or ""
        updated = True

    if updated:
        hass.config_entries.async_update_entry(entry, data=data)
        refreshed_entry = hass.config_entries.async_get_entry(entry.entry_id)
        if refreshed_entry is not None:
            entry = refreshed_entry

    coordinator = NBPowerDataUpdateCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload an NB Power config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
