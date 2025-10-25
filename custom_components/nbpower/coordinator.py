"""DataUpdateCoordinator for the NB Power integration."""
from __future__ import annotations

from datetime import date, timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
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
    USAGE_SENSOR_KEYS,
)
from .usage import UsageStore

_LOGGER = logging.getLogger(__name__)


class NBPowerDataUpdateCoordinator(DataUpdateCoordinator[dict]):
    """Class to manage fetching NB Power data."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
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
        self.client = NBPowerClient(async_get_clientsession(hass))
        self._store = UsageStore(hass, entry.entry_id)
        self._store_loaded = False

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
            if not self._store_loaded:
                await self._store.async_load()
                self._store_loaded = True
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
        """Fetch monthly summary and refresh cached usage datasets."""

        if not self._store_loaded:
            await self._store.async_load()
            self._store_loaded = True

        today = date.today()
        summary = await self.client.fetch_mtd(today)

        if not self._account_number or not self._utility_account_number:
            raise UpdateFailed("Missing account identifiers for usage refresh")

        store_changed = False
        datasets_to_process = list(USAGE_SENSOR_KEYS.keys())

        for mode, rtype in datasets_to_process:
            ranges = self._store.determine_fetch_ranges(mode, rtype, today)
            for start, end in ranges:
                payload = await self.client.get_usage_data(
                    self.client._token,  # pylint: disable=protected-access
                    self._account_number,
                    self._utility_account_number,
                    self._meter_number or "",
                    mode=mode,
                    rtype=rtype,
                    date_from=start.isoformat(),
                    date_to=end.isoformat(),
                )
                if self._store.add_payload(mode, rtype, payload):
                    store_changed = True

        if store_changed:
            await self._store.async_save()

        usage_payloads = {}
        for key, data in self._store.datasets_for_sensors().items():
            sensor_key = USAGE_SENSOR_KEYS.get(key)
            if sensor_key:
                usage_payloads[sensor_key] = data

        previous_day = self._store.latest_daily_summary()

        combined: dict = {**summary}
        combined["summary"] = summary
        combined.update(usage_payloads)
        combined["previous_day"] = previous_day
        if previous_day.get("usage_kwh") is not None:
            combined["previous_day_kwh"] = previous_day["usage_kwh"]
        if previous_day.get("cost") is not None:
            combined["previous_day_cost"] = previous_day["cost"]
        if previous_day.get("date"):
            combined["previous_day_date"] = previous_day["date"]

        return combined
