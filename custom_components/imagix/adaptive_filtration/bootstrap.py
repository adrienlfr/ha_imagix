"""Set up and retrieve the adaptive filtration manager."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from ..const import DOMAIN
from ..coordinator import ImagixDataUpdateCoordinator
from .manager import AdaptiveFiltrationManager

DATA_ADAPTIVE_FILTRATION = f"{DOMAIN}_adaptive_filtration"


async def async_setup_adaptive_filtration(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: ImagixDataUpdateCoordinator,
) -> AdaptiveFiltrationManager:
    """Create and start one manager per config entry."""
    manager = AdaptiveFiltrationManager(hass, entry, coordinator)
    hass.data.setdefault(DATA_ADAPTIVE_FILTRATION, {})[entry.entry_id] = manager
    await manager.async_start()
    return manager


async def async_unload_adaptive_filtration(
    hass: HomeAssistant,
    entry_id: str,
) -> None:
    """Stop and remove one manager."""
    managers = hass.data.get(DATA_ADAPTIVE_FILTRATION, {})
    manager = managers.pop(entry_id, None)
    if manager is not None:
        await manager.async_stop()
    if not managers:
        hass.data.pop(DATA_ADAPTIVE_FILTRATION, None)


def get_adaptive_filtration_manager(
    hass: HomeAssistant,
    entry_id: str,
) -> AdaptiveFiltrationManager:
    """Return the manager for an existing entry."""
    return hass.data[DATA_ADAPTIVE_FILTRATION][entry_id]

