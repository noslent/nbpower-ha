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
            credentials = {
                CONF_USERNAME: user_input[CONF_USERNAME].strip(),
                CONF_PASSWORD: user_input[CONF_PASSWORD],
            }

            if not credentials[CONF_USERNAME]:
                errors["base"] = "invalid_auth"
            else:
                try:
                    account_number = await self._async_validate_credentials(credentials)
                except CannotConnect:
                    errors["base"] = "cannot_connect"
                except InvalidAuth:
                    errors["base"] = "invalid_auth"
                except Exception:  # pylint: disable=broad-except
                    _LOGGER.exception(
                        "Unexpected exception validating NB Power credentials"
                    )
                    errors["base"] = "unknown"
                else:
                    self._async_update_existing_entry(account_number, credentials)
                    await self.async_set_unique_id(account_number)
                    self._abort_if_unique_id_configured(updates=credentials)
                    return self.async_create_entry(
                        title=credentials[CONF_USERNAME],
                        data=credentials,
                    )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_import(self, user_input: dict[str, Any]) -> FlowResult:
        """Handle YAML import."""
        credentials = {
            CONF_USERNAME: user_input[CONF_USERNAME].strip(),
            CONF_PASSWORD: user_input[CONF_PASSWORD],
        }

        if not credentials[CONF_USERNAME]:
            return self.async_abort(reason="invalid_auth")

        try:
            account_number = await self._async_validate_credentials(credentials)
        except CannotConnect:
            return self.async_abort(reason="cannot_connect")
        except InvalidAuth:
            return self.async_abort(reason="invalid_auth")

        self._async_update_existing_entry(account_number, credentials)
        await self.async_set_unique_id(account_number)
        self._abort_if_unique_id_configured(updates=credentials)

        return self.async_create_entry(title=credentials[CONF_USERNAME], data=credentials)

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
            credentials = {
                CONF_USERNAME: user_input[CONF_USERNAME].strip(),
                CONF_PASSWORD: user_input[CONF_PASSWORD],
            }

            if not credentials[CONF_USERNAME]:
                errors["base"] = "invalid_auth"
            else:
                try:
                    account_number = await self._async_validate_credentials(credentials)
                except CannotConnect:
                    errors["base"] = "cannot_connect"
                except InvalidAuth:
                    errors["base"] = "invalid_auth"
                else:
                    if self._reauth_entry:
                        self.hass.config_entries.async_update_entry(
                            self._reauth_entry,
                            data=credentials,
                            unique_id=account_number,
                        )
                        await self.hass.config_entries.async_reload(
                            self._reauth_entry.entry_id
                        )
                    return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            description_placeholders=placeholders,
        )

    def _async_update_existing_entry(
        self, account_number: str, credentials: dict[str, Any]
    ) -> None:
        username_key = credentials[CONF_USERNAME].lower()
        lowered_account = account_number.lower()

        for entry in self._async_current_entries():
            entry_username = str(entry.data.get(CONF_USERNAME, "")).strip().lower()
            entry_unique = (entry.unique_id or "").strip().lower()

            if entry_unique in {lowered_account, username_key} or entry_username == username_key:
                update_kwargs: dict[str, Any] = {}
                if entry.data != credentials:
                    update_kwargs["data"] = credentials
                if entry.unique_id != account_number:
                    update_kwargs["unique_id"] = account_number
                if update_kwargs:
                    self.hass.config_entries.async_update_entry(entry, **update_kwargs)
                return

    async def _async_validate_credentials(self, data: dict[str, Any]) -> str:
        """Validate the user credentials by performing a login."""
        session = async_get_clientsession(self.hass)
        client = NBPowerClient(session)
        username = data[CONF_USERNAME]
        password = data[CONF_PASSWORD]

        try:
            await client.ensure_bootstrap(username, password)
        except RuntimeError as err:
            client.reset_bootstrap()
            if "login" in str(err).lower():
                raise InvalidAuth from err
            raise CannotConnect from err
        except aiohttp.ClientError as err:
            client.reset_bootstrap()
            raise CannotConnect from err

        account_number = (client.account_number or "").strip()
        client.reset_bootstrap()

        if not account_number:
            raise CannotConnect

        return account_number


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
