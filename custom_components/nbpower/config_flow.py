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
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import NBPowerClient
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate the credentials are invalid."""


async def validate_input(hass: HomeAssistant, data: dict) -> dict:
    """Validate the user input allows us to connect."""
    session = async_get_clientsession(hass)
    client = NBPowerClient(session)

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
    account_number = getattr(client, "_account_number", None)  # pylint: disable=protected-access
    title = account_number or data[CONF_USERNAME]

    return {
        "title": str(title),
        "unique_id": unique_id,
    }


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for NB Power."""

    VERSION = 1

    def __init__(self) -> None:
        self._reauth_entry: ConfigEntry | None = None

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
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
            data_schema=DATA_SCHEMA,
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

        placeholders = {}
        if self._reauth_entry:
            placeholders["username"] = self._reauth_entry.data.get(CONF_USERNAME, "")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=DATA_SCHEMA,
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

        if self._reauth_entry:
            assert self._reauth_entry is not None
            self.hass.config_entries.async_update_entry(
                self._reauth_entry,
                data=user_input,
            )
            await self.hass.config_entries.async_reload(self._reauth_entry.entry_id)
            return self.async_abort(reason="reauth_successful")

        await self.async_set_unique_id(info["unique_id"])
        self._abort_if_unique_id_configured(updates=updates)
        return self.async_create_entry(title=info["title"], data=user_input)
