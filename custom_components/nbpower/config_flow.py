"""Config flow for the NB Power integration."""
from __future__ import annotations

from datetime import date
import hashlib
import logging

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from .const import (
    CONF_ACCOUNT_NUMBER,
    CONF_METER_NUMBER,
    CONF_SCAN_INTERVAL,
    CONF_UTILITY_ACCOUNT_NUMBER,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)
from .helpers import async_create_nbpower_client

_LOGGER = logging.getLogger(__name__)

def _build_schema(*, default_interval: int = DEFAULT_SCAN_INTERVAL) -> vol.Schema:
    """Return the schema for user credentials and refresh interval."""

    bounded_default = max(default_interval, MIN_SCAN_INTERVAL)

    return vol.Schema(
        {
            vol.Required(CONF_USERNAME): str,
            vol.Required(CONF_PASSWORD): str,
            vol.Optional(
                CONF_SCAN_INTERVAL,
                default=bounded_default,
            ): vol.All(vol.Coerce(int), vol.Clamp(min=MIN_SCAN_INTERVAL)),
        }
    )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate the credentials are invalid."""


async def validate_input(hass: HomeAssistant, data: dict) -> dict:
    """Validate the user input allows us to connect."""
    client = await async_create_nbpower_client(hass)

    try:
        await client.ensure_bootstrap(data[CONF_USERNAME], data[CONF_PASSWORD])
        await client.fetch_mtd(date.today())
    except RuntimeError as err:
        message = str(err).lower()
        if "login failed" in message:
            raise InvalidAuth from err
        raise CannotConnect from err
    except aiohttp.ClientError as err:
        raise CannotConnect from err
    except Exception as err:  # pylint: disable=broad-except
        _LOGGER.exception("Unexpected error validating NB Power credentials")
        raise CannotConnect from err

    unique_source = data[CONF_USERNAME].lower().encode()
    unique_id = hashlib.sha256(unique_source).hexdigest()
    account_number = client.account_number
    title = account_number or data[CONF_USERNAME]

    return {
        "title": str(title),
        "unique_id": unique_id,
        CONF_ACCOUNT_NUMBER: account_number,
        CONF_UTILITY_ACCOUNT_NUMBER: client.utility_account_number,
        CONF_METER_NUMBER: client.meter_number,
    }


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for NB Power."""

    VERSION = 1

    def __init__(self) -> None:
        self._reauth_entry: ConfigEntry | None = None

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        schema = _build_schema(
            default_interval=(
                user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
                if user_input
                else DEFAULT_SCAN_INTERVAL
            )
        )
        if user_input is not None:
            try:
                return await self._async_finish_setup(user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected error creating NB Power entry")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_import(self, user_input: dict) -> FlowResult:
        """Handle import from YAML."""
        try:
            return await self._async_finish_setup(user_input, updates=user_input)
        except InvalidAuth:
            return self.async_abort(reason="invalid_auth")
        except CannotConnect:
            return self.async_abort(reason="cannot_connect")
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected error importing NB Power configuration")
            return self.async_abort(reason="unknown")

    async def async_step_reauth(self, user_input: dict | None = None) -> FlowResult:
        """Handle re-authentication when credentials fail."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        return await self.async_step_reauth_confirm(user_input)

    async def async_step_reauth_confirm(self, user_input: dict | None = None) -> FlowResult:
        """Handle the re-auth confirmation step."""
        errors: dict[str, str] = {}
        default_interval = DEFAULT_SCAN_INTERVAL
        if self._reauth_entry:
            default_interval = self._reauth_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        if user_input is not None:
            try:
                return await self._async_finish_setup(user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected error re-authenticating NB Power")
                errors["base"] = "unknown"
            default_interval = user_input.get(CONF_SCAN_INTERVAL, default_interval)

        placeholders = {}
        if self._reauth_entry:
            placeholders["username"] = self._reauth_entry.data.get(CONF_USERNAME, "")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=_build_schema(default_interval=default_interval),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def _async_finish_setup(
        self,
        user_input: dict,
        *,
        updates: dict | None = None,
    ) -> FlowResult:
        """Validate input and create or update the config entry."""
        info = await validate_input(self.hass, user_input)

        account_number = info.get(CONF_ACCOUNT_NUMBER)
        utility_account_number = info.get(CONF_UTILITY_ACCOUNT_NUMBER)
        meter_number = info.get(CONF_METER_NUMBER) or ""

        entry_data = {
            CONF_USERNAME: user_input[CONF_USERNAME],
            CONF_PASSWORD: user_input[CONF_PASSWORD],
            CONF_SCAN_INTERVAL: max(
                user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                MIN_SCAN_INTERVAL,
            ),
            CONF_ACCOUNT_NUMBER: account_number,
            CONF_UTILITY_ACCOUNT_NUMBER: utility_account_number,
            CONF_METER_NUMBER: meter_number,
        }

        updates_for_abort = entry_data if updates is None else {**updates, **entry_data}

        if self._reauth_entry:
            assert self._reauth_entry is not None
            self.hass.config_entries.async_update_entry(
                self._reauth_entry,
                data=entry_data,
            )
            await self.hass.config_entries.async_reload(self._reauth_entry.entry_id)
            return self.async_abort(reason="reauth_successful")

        await self.async_set_unique_id(info["unique_id"])
        self._abort_if_unique_id_configured(updates=updates_for_abort)
        return self.async_create_entry(title=info["title"], data=entry_data)
