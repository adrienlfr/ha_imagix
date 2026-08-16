"""Number platform for iMagi-x controller settings."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import ImagixDataUpdateCoordinator
from .entity import ImagixEntity


@dataclass(frozen=True, kw_only=True)
class ImagixNumberDescription:
    """Describe a writable iMagi-x number setting."""

    key: str
    name: str
    icon: str
    state_path: tuple[str, ...]
    native_min_value: float
    native_max_value: float
    native_step: float
    unit: str | None = None
    presence_path: tuple[str, ...] | None = None
    enabled_by_default: bool = True
    state_divisor: float = 1


DESCRIPTIONS = (
    ImagixNumberDescription(
        key="filtration_pause_default_duration",
        name="Durée de pause par défaut",
        icon="mdi:timer-outline",
        state_path=("filtration", "pause", "defaultTime"),
        native_min_value=60,
        native_max_value=86400,
        native_step=60,
        unit="s",
    ),
    ImagixNumberDescription(
        key="heater_eco_temperature",
        name="Consigne chauffage Éco",
        icon="mdi:thermometer-low",
        state_path=("heater", "setpointModeEco"),
        native_min_value=15,
        native_max_value=45,
        native_step=0.5,
        unit="°C",
        presence_path=("heater",),
        state_divisor=10,
    ),
    ImagixNumberDescription(
        key="heater_comfort_temperature",
        name="Consigne chauffage Confort",
        icon="mdi:thermometer-high",
        state_path=("heater", "setpointModeConfort"),
        native_min_value=15,
        native_max_value=45,
        native_step=0.5,
        unit="°C",
        presence_path=("heater",),
        state_divisor=10,
    ),
    ImagixNumberDescription(
        key="ph_setpoint",
        name="Consigne pH",
        icon="mdi:ph",
        state_path=("treatment", "ph", "setpoint"),
        native_min_value=0,
        native_max_value=14,
        native_step=0.1,
        presence_path=("treatment", "ph"),
        enabled_by_default=False,
    ),
    ImagixNumberDescription(
        key="chlorine_setpoint",
        name="Consigne chlore / Redox",
        icon="mdi:water-check",
        state_path=("treatment", "chlorine", "setpoint"),
        native_min_value=0,
        native_max_value=1000,
        native_step=1,
        unit="mV",
        presence_path=("treatment", "chlorine"),
        enabled_by_default=False,
    ),
    ImagixNumberDescription(
        key="electrolyzer_setpoint",
        name="Consigne électrolyseur",
        icon="mdi:water-sync",
        state_path=("treatment", "electrolyzer", "setpoint"),
        native_min_value=0,
        native_max_value=1000,
        native_step=1,
        unit="mV",
        presence_path=("treatment", "electrolyzer"),
        enabled_by_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up iMagi-x number entities from a config entry."""
    coordinator: ImagixDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities(
        ImagixNumber(coordinator, config_entry.entry_id, description)
        for description in DESCRIPTIONS
        if _is_available(coordinator.data, description.presence_path)
    )


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


class ImagixNumber(ImagixEntity, NumberEntity):
    """Representation of a writable iMagi-x number setting."""

    def __init__(
        self,
        coordinator: ImagixDataUpdateCoordinator,
        entry_id: str,
        description: ImagixNumberDescription,
    ) -> None:
        """Initialize an iMagi-x number entity."""
        super().__init__(coordinator, entry_id)
        self._description = description
        self._attr_unique_id = f"{entry_id}_{description.key}"
        self._attr_name = description.name
        self._attr_icon = description.icon
        self._attr_native_min_value = description.native_min_value
        self._attr_native_max_value = description.native_max_value
        self._attr_native_step = description.native_step
        self._attr_native_unit_of_measurement = description.unit
        self._attr_entity_registry_enabled_default = description.enabled_by_default

        if description.key.startswith("heater_"):
            limits = self._state("pool", "heater")
            self._attr_native_min_value = float(
                limits.get("tempMin", description.native_min_value)
            )
            self._attr_native_max_value = float(
                limits.get("tempMax", description.native_max_value)
            )

    @property
    def native_value(self) -> float | None:
        """Return the configured value."""
        value: Any = self.coordinator.data.get("state", {})
        for key in self._description.state_path:
            if not isinstance(value, dict):
                return None
            value = value.get(key)
        if not isinstance(value, int | float):
            return None
        return float(value) / self._description.state_divisor

    async def async_set_native_value(self, value: float) -> None:
        """Set a controller value."""
        key = self._description.key
        if key == "filtration_pause_default_duration":
            command = self.coordinator.client.async_set_pause_default_time(int(value))
        elif key == "heater_eco_temperature":
            command = self.coordinator.client.async_set_heater_eco_temperature(value)
        elif key == "heater_comfort_temperature":
            command = self.coordinator.client.async_set_heater_comfort_temperature(value)
        elif key == "ph_setpoint":
            settings = self._state("treatment", "ph")
            command = self.coordinator.client.async_set_ph_setpoint(
                value,
                float(settings.get("setpointDelta", 0)),
            )
        elif key == "chlorine_setpoint":
            settings = self._state("treatment", "chlorine")
            command = self.coordinator.client.async_set_chlorine_setpoint(
                value,
                float(settings.get("setpointDelta", 0)),
            )
        else:
            settings = self._state("treatment", "electrolyzer")
            command = self.coordinator.client.async_set_electrolyzer_setpoint(
                value,
                float(settings.get("setpointDelta", 0)),
            )
        await self._async_execute(command)
