"""Button platform for iMagi-x actions."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .adaptive_filtration.bootstrap import get_adaptive_filtration_manager
from .adaptive_filtration.entities.button import (
    AdaptiveFiltrationRecalculateButton,
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up iMagi-x buttons."""
    manager = get_adaptive_filtration_manager(hass, config_entry.entry_id)
    async_add_entities(
        [AdaptiveFiltrationRecalculateButton(manager, config_entry.entry_id)]
    )

