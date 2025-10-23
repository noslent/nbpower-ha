"""Config flow for the NB Power integration."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import NBPowerClient
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class NBPowerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for NB Power."""

    VERSION = 1

    _reauth_entry: ConfigEntry | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                await self._async_validate_credentials(user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception validating NB Power credentials")
                errors["base"] = "unknown"
            else:
                unique_id = user_input[CONF_USERNAME].lower()
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=user_input[CONF_USERNAME], data=user_input)

        return self.async_show_form(step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors)

    async def async_step_import(self, user_input: dict[str, Any]) -> FlowResult:
        """Handle YAML import."""
        try:
            await self._async_validate_credentials(user_input)
        except CannotConnect:
            return self.async_abort(reason="cannot_connect")
        except InvalidAuth:
            return self.async_abort(reason="invalid_auth")

        unique_id = user_input[CONF_USERNAME].lower()
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()

        return self.async_create_entry(title=user_input[CONF_USERNAME], data=user_input)

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> FlowResult:
        """Handle re-authentication with new credentials."""
        entry_id = self.context.get("entry_id")
        if entry_id:
            self._reauth_entry = self.hass.config_entries.async_get_entry(entry_id)
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm re-authentication step."""
        errors: dict[str, str] = {}
        placeholders: dict[str, str] | None = None
        if self._reauth_entry:
            placeholders = {"username": self._reauth_entry.data.get(CONF_USERNAME, "")}

        if user_input is not None:
            try:
                await self._async_validate_credentials(user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            else:
                if self._reauth_entry:
                    self.hass.config_entries.async_update_entry(self._reauth_entry, data=user_input)
                    await self.hass.config_entries.async_reload(self._reauth_entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            description_placeholders=placeholders,
        )

    async def _async_validate_credentials(self, data: dict[str, Any]) -> None:
        """Validate the user credentials by performing a login."""
        session = async_get_clientsession(self.hass)
        client = NBPowerClient(session)
        try:
            await client.ensure_bootstrap(data[CONF_USERNAME], data[CONF_PASSWORD])
        except RuntimeError as err:
            if "login" in str(err).lower():
                raise InvalidAuth from err
            raise CannotConnect from err
        except aiohttp.ClientError as err:
            raise CannotConnect from err


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
