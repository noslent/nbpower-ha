"""Helper utilities for the NB Power integration."""
from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

if TYPE_CHECKING:
    from .api import NBPowerClient


async def async_create_nbpower_client(hass: HomeAssistant) -> "NBPowerClient":
    """Create an NB Power API client without blocking the event loop."""

    module = await hass.async_add_executor_job(import_module, f"{__package__}.api")
    client_class = module.NBPowerClient
    return client_class(async_get_clientsession(hass))
