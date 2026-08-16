"""Switch platform for iMagi-x timed filtration modes."""
from __future__ import annotations

from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import ImagixDataUpdateCoordinator
from .entity import ImagixEntity

DEFAULT_DURATION = 3600


@dataclass(frozen=True, kw_only=True)
class ImagixTimedSwitchDescription:
    """Describe a timed iMagi-x switch."""

    key: str
    name: str
    icon: str
    state_key: str


DESCRIPTIONS = (
    ImagixTimedSwitchDescription(
        key="swimming_filtration",
        name="Filtration baignade",
        icon="mdi:swim",
        state_key="swimming",
    ),
    ImagixTimedSwitchDescription(
        key="filtration_pause",
        name="Pause filtration",
        icon="mdi:pause-circle",
        state_key="pause",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up iMagi-x switches from a config entry."""
    coordinator: ImagixDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities(
        ImagixTimedFiltrationSwitch(coordinator, config_entry.entry_id, description)
        for description in DESCRIPTIONS
    )


class ImagixTimedFiltrationSwitch(ImagixEntity, SwitchEntity):
    """Representation of a timed filtration action."""

    def __init__(
        self,
        coordinator: ImagixDataUpdateCoordinator,
        entry_id: str,
        description: ImagixTimedSwitchDescription,
    ) -> None:
        """Initialize the timed filtration switch."""
        super().__init__(coordinator, entry_id)
        self._description = description
        self._attr_unique_id = f"{entry_id}_{description.key}"
        self._attr_name = description.name
        self._attr_icon = description.icon

    @property
    def is_on(self) -> bool:
        """Return whether the timed action is running."""
        return self._settings().get("remainTime", 0) > 0

    @property
    def extra_state_attributes(self) -> dict[str, int]:
        """Expose the remaining and default durations in seconds."""
        settings = self._settings()
        return {
            "remaining_seconds": settings.get("remainTime", 0),
            "default_seconds": settings.get("defaultTime", DEFAULT_DURATION),
        }

    async def async_turn_on(self, **kwargs: object) -> None:
        """Start the timed filtration action for its configured duration."""
        duration = self._settings().get("defaultTime", DEFAULT_DURATION)
        await self._async_execute(self._command(int(duration)))

    async def async_turn_off(self, **kwargs: object) -> None:
        """Stop the timed filtration action."""
        await self._async_execute(self._command(0))

    def _settings(self) -> dict[str, Any]:
        """Return the action settings from the current controller state."""
        return self._state("filtration", self._description.state_key)

    def _command(self, duration: int) -> Awaitable[None]:
        """Build the corresponding controller command."""
        if self._description.state_key == "swimming":
            return self.coordinator.client.async_set_swimming(duration)
        return self.coordinator.client.async_set_pause(duration)
