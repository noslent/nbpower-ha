"""DataUpdateCoordinator for the NB Power integration."""
from __future__ import annotations

from datetime import date, timedelta
import logging
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .const import (
    CONF_ACCOUNT_NUMBER,
    CONF_METER_NUMBER,
    CONF_SCAN_INTERVAL,
    CONF_UTILITY_ACCOUNT_NUMBER,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)

if TYPE_CHECKING:
    from .api import NBPowerClient

_LOGGER = logging.getLogger(__name__)


class NBPowerDataUpdateCoordinator(DataUpdateCoordinator[dict]):
    """Class to manage fetching NB Power data."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: "NBPowerClient",
    ) -> None:
        """Initialize coordinator."""
        data = entry.data
        self._username = data[CONF_USERNAME]
        self._password = data[CONF_PASSWORD]
        self._scan_interval = max(
            data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            MIN_SCAN_INTERVAL,
        )
        self._account_number = data.get(CONF_ACCOUNT_NUMBER)
        self._utility_account_number = data.get(CONF_UTILITY_ACCOUNT_NUMBER)
        self._meter_number = data.get(CONF_METER_NUMBER)
        self.client = client
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_coordinator",
            update_interval=timedelta(seconds=self._scan_interval),
        )

    async def _async_bootstrap(self) -> None:
        """Ensure the API client is authenticated and ready."""
        try:
            await self.client.ensure_bootstrap(
                self._username,
                self._password,
                account_number=self._account_number,
                utility_account_number=self._utility_account_number,
                meter_number=self._meter_number,
            )
            if self._account_number is None:
                self._account_number = self.client.account_number
            if self._utility_account_number is None:
                self._utility_account_number = self.client.utility_account_number
            if self._meter_number is None:
                self._meter_number = self.client.meter_number
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

            return await self._async_fetch_all()
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
                return await self._async_fetch_all()
            except ConfigEntryAuthFailed:
                raise
            except Exception as err2:  # pylint: disable=broad-except
                raise UpdateFailed(f"Error updating NB Power data: {err2}") from err2

    async def _async_fetch_all(self) -> dict:
        """Fetch the latest monthly summary data."""

        today = date.today()
        summary = await self.client.fetch_mtd(today)
        combined: dict = {**summary}
        combined["summary"] = summary
        return combined
