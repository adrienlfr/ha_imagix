"""Shared entity base for adaptive filtration."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from ...const import DOMAIN
from ..manager import AdaptiveFiltrationManager


class AdaptiveFiltrationEntity(Entity):
    """Entity updated by the adaptive filtration manager."""

    _attr_has_entity_name = True

    def __init__(self, manager: AdaptiveFiltrationManager, entry_id: str) -> None:
        self.manager = manager
        self._entry_id = entry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name="iMAGI-X",
            manufacturer="Piscines Magiline",
            model="iMAGI-X pool controller",
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to manager updates."""
        self.async_on_remove(
            self.manager.async_add_listener(self.async_write_ha_state)
        )

