"""NB Power integration init."""

from __future__ import annotations

from datetime import date, timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import NBPowerClient
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


def _is_auth_error(error: Exception) -> bool:
    message = str(error)
    return "login" in message.lower() and "fail" in message.lower()


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the NB Power integration from YAML."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up NB Power from a config entry."""

    hass.data.setdefault(DOMAIN, {})

    session = async_get_clientsession(hass)
    client = NBPowerClient(session)
    username: str = entry.data[CONF_USERNAME]
    password: str = entry.data[CONF_PASSWORD]

    async def _async_update() -> dict:
        try:
            if client._token is None:  # pylint: disable=protected-access
                await client.ensure_bootstrap(username, password)
            return await client.fetch_mtd(date.today())
        except RuntimeError as err:
            if _is_auth_error(err):
                raise ConfigEntryAuthFailed from err
            raise UpdateFailed(str(err)) from err
        except Exception as err:  # pylint: disable=broad-except
            raise UpdateFailed(str(err)) from err

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"{DOMAIN}_coordinator_{entry.entry_id}",
        update_method=_async_update,
        update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "client": client,
        "username": username,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload entry when its data changes."""
    await hass.config_entries.async_reload(entry.entry_id)
