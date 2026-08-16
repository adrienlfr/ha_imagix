"""The iMagi-x integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_IP_ADDRESS, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ImagixApiClient
from .const import DOMAIN
from .coordinator import ImagixDataUpdateCoordinator
from .services import async_register_services, async_unregister_services

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.CLIMATE,
    Platform.LIGHT,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up iMagi-x from a config entry."""
    _LOGGER.debug("Setting up iMagi-x integration")
    
    session = async_get_clientsession(hass)
    client = ImagixApiClient(entry.data[CONF_IP_ADDRESS], session)
    coordinator = ImagixDataUpdateCoordinator(hass, client)
    
    await coordinator.async_config_entry_first_refresh()
    coordinator.async_start_expert_program_sync()
    
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator
    async_register_services(hass)
    
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading iMagi-x integration")
    
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN][entry.entry_id].async_stop_expert_program_sync()
        hass.data[DOMAIN].pop(entry.entry_id)
        if not hass.data[DOMAIN]:
            async_unregister_services(hass)
    
    return unload_ok
