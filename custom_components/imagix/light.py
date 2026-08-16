"""Light platform for iMagi-x."""
from __future__ import annotations

from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import ImagixDataUpdateCoordinator
from .entity import ImagixEntity


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up iMagi-x lights from a config entry."""
    coordinator: ImagixDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    spotlight = coordinator.data.get("state", {}).get("spotlight", {})

    if spotlight.get("presence"):
        async_add_entities([ImagixSpotlight(coordinator, config_entry.entry_id)])


class ImagixSpotlight(ImagixEntity, LightEntity):
    """Representation of the pool spotlight."""

    _attr_name = "Éclairage"
    _attr_icon = "mdi:spotlight-beam"
    _attr_supported_color_modes = {ColorMode.ONOFF}
    _attr_color_mode = ColorMode.ONOFF

    def __init__(
        self,
        coordinator: ImagixDataUpdateCoordinator,
        entry_id: str,
    ) -> None:
        """Initialize the spotlight entity."""
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_spotlight"

    @property
    def is_on(self) -> bool:
        """Return whether the spotlight is on."""
        # The controller exposes 1 as on and 2 as on via the remote control.
        return self._state("spotlight").get("state") in (1, 2)

    async def async_turn_on(self, **kwargs: object) -> None:
        """Turn the spotlight on in manual mode."""
        await self._async_execute(self.coordinator.client.async_set_spotlight(True))

    async def async_turn_off(self, **kwargs: object) -> None:
        """Turn the spotlight off in manual mode."""
        await self._async_execute(self.coordinator.client.async_set_spotlight(False))
