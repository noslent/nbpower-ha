"""DataUpdateCoordinator for the NB Power integration."""
from __future__ import annotations

from datetime import date, timedelta
import logging

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import NBPowerClient
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class NBPowerDataUpdateCoordinator(DataUpdateCoordinator[dict]):
    """Class to manage fetching NB Power data."""

    def __init__(self, hass: HomeAssistant, username: str, password: str) -> None:
        """Initialize coordinator."""
        self._username = username
        self._password = password
        self.client = NBPowerClient(async_get_clientsession(hass))

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_coordinator",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )

    async def _async_bootstrap(self) -> None:
        """Ensure the API client is authenticated and ready."""
        try:
            await self.client.ensure_bootstrap(self._username, self._password)
        except RuntimeError as err:
            if "Login failed" in str(err):
                raise ConfigEntryAuthFailed("Invalid credentials") from err
            raise UpdateFailed(f"Failed to bootstrap NB Power client: {err}") from err
        except Exception as err:  # pylint: disable=broad-except
            raise UpdateFailed(f"Unexpected error during NB Power bootstrap: {err}") from err

    async def _async_update_data(self) -> dict:
        """Fetch the latest data from NB Power."""
        try:
            if self.client._token is None:  # pylint: disable=protected-access
                await self._async_bootstrap()

            return await self.client.fetch_mtd(date.today())
        except ConfigEntryAuthFailed:
            self.client._token = None  # pylint: disable=protected-access
            raise
        except UpdateFailed:
            self.client._token = None  # pylint: disable=protected-access
            raise
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.debug("NB Power update failed, retrying bootstrap: %s", err)
            self.client._token = None  # pylint: disable=protected-access
            try:
                await self._async_bootstrap()
                return await self.client.fetch_mtd(date.today())
            except ConfigEntryAuthFailed:
                raise
            except Exception as err2:  # pylint: disable=broad-except
                raise UpdateFailed(f"Error updating NB Power data: {err2}") from err2
