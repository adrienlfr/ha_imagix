"""Select platform for iMagi-x operating modes."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import ImagixDataUpdateCoordinator
from .entity import ImagixEntity

Command = Callable[[int | bool], Awaitable[None]]


@dataclass(frozen=True, kw_only=True)
class ImagixSelectDescription:
    """Describe an iMagi-x mode selector."""

    key: str
    name: str
    icon: str
    options: dict[str, int | bool]
    state_path: tuple[str, ...]
    command: Command
    presence_path: tuple[str, ...] | None = None


FILTRATION_MODES = {
    "Automatique": 0,
    "Marche forcée": 1,
    "Arrêt manuel": 2,
}

FILTRATION_PROGRAMS = {
    "Programme 1": 0,
    "Programme 2": 1,
    "Programme 3": 2,
    "Auto 25": 3,
    "Auto 50": 4,
    "NFX4": 5,
    "Serveur": 6,
}

HEATER_MODES = {
    "Arrêt": 0,
    "Éco": 1,
    "Confort": 2,
    "Boost": 3,
    "Planning": 4,
}

HEATER_FILTRATION_PRIORITY = {
    "Priorité au chauffage": True,
    "Identique à la filtration": False,
}

TREATMENT_MODES = {
    "Automatique": 0,
    "Arrêt manuel": 1,
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up iMagi-x selects from a config entry."""
    coordinator: ImagixDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    client = coordinator.client

    descriptions = (
        ImagixSelectDescription(
            key="filtration_mode",
            name="Mode de filtration",
            icon="mdi:air-filter",
            options=FILTRATION_MODES,
            state_path=("filtration", "mode"),
            command=client.async_set_filtration_mode,
        ),
        ImagixSelectDescription(
            key="filtration_program",
            name="Programme de filtration",
            icon="mdi:calendar-clock",
            options=FILTRATION_PROGRAMS,
            state_path=("filtration", "actualProg"),
            command=client.async_set_filtration_program,
        ),
        ImagixSelectDescription(
            key="heater_mode",
            name="Mode de chauffage",
            icon="mdi:heat-wave",
            options=HEATER_MODES,
            state_path=("heater", "mode"),
            presence_path=("heater",),
            command=client.async_set_heater_mode,
        ),
        ImagixSelectDescription(
            key="heater_filtration_priority",
            name="Fonctionnement de la filtration pour le chauffage",
            icon="mdi:heat-wave",
            options=HEATER_FILTRATION_PRIORITY,
            state_path=("heater", "filtrationPriority"),
            presence_path=("heater",),
            command=client.async_set_heater_filtration_priority,
        ),
        ImagixSelectDescription(
            key="ph_mode",
            name="Mode de traitement pH",
            icon="mdi:ph",
            options=TREATMENT_MODES,
            state_path=("treatment", "ph", "mode"),
            presence_path=("treatment", "ph"),
            command=client.async_set_ph_mode,
        ),
        ImagixSelectDescription(
            key="chlorine_mode",
            name="Mode de traitement chlore",
            icon="mdi:water-check",
            options=TREATMENT_MODES,
            state_path=("treatment", "chlorine", "mode"),
            presence_path=("treatment", "chlorine"),
            command=client.async_set_chlorine_mode,
        ),
        ImagixSelectDescription(
            key="electrolyzer_mode",
            name="Mode électrolyseur",
            icon="mdi:water-sync",
            options=TREATMENT_MODES,
            state_path=("treatment", "electrolyzer", "mode"),
            presence_path=("treatment", "electrolyzer"),
            command=client.async_set_electrolyzer_mode,
        ),
    )

    entities = [
        ImagixSelect(coordinator, config_entry.entry_id, description)
        for description in descriptions
        if _is_available(coordinator.data, description.presence_path)
    ]
    async_add_entities(entities)


def _is_available(
    data: dict[str, Any],
    presence_path: tuple[str, ...] | None,
) -> bool:
    """Return whether the equipment backing an entity is present."""
    if presence_path is None:
        return True

    value: Any = data.get("state", {})
    for key in presence_path:
        if not isinstance(value, dict):
            return False
        value = value.get(key, {})
    return isinstance(value, dict) and bool(value.get("presence"))


class ImagixSelect(ImagixEntity, SelectEntity):
    """Representation of an iMagi-x operating mode selector."""

    def __init__(
        self,
        coordinator: ImagixDataUpdateCoordinator,
        entry_id: str,
        description: ImagixSelectDescription,
    ) -> None:
        """Initialize an iMagi-x selector."""
        super().__init__(coordinator, entry_id)
        self._description = description
        self._attr_unique_id = f"{entry_id}_{description.key}"
        self._attr_name = description.name
        self._attr_icon = description.icon
        self._attr_options = list(description.options)

    @property
    def current_option(self) -> str | None:
        """Return the currently selected option."""
        value: Any = self.coordinator.data.get("state", {})
        for key in self._description.state_path:
            if not isinstance(value, dict):
                return None
            value = value.get(key)

        for option, mode in self._description.options.items():
            if mode == value:
                return option
        return None

    async def async_select_option(self, option: str) -> None:
        """Set the requested operating mode."""
        await self._async_execute(
            self._description.command(self._description.options[option])
        )
