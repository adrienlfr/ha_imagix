"""Climate entity for the iMagi-x pool heat pump."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import ImagixDataUpdateCoordinator
from .entity import ImagixEntity

HEATER_OFF = 0
HEATER_ECO = 1
HEATER_COMFORT = 2
HEATER_BOOST = 3
HEATER_PLANNING = 4


@dataclass(frozen=True)
class HeaterPreset:
    """A climate preset mapped to the controller's heater mode."""

    mode: int
    priority: bool


PRESETS: dict[str, HeaterPreset] = {
    "Éco": HeaterPreset(HEATER_ECO, False),
    "Confort": HeaterPreset(HEATER_COMFORT, False),
    "Boost": HeaterPreset(HEATER_BOOST, False),
    "Planning": HeaterPreset(HEATER_PLANNING, False),
    "Éco · priorité chauffage": HeaterPreset(HEATER_ECO, True),
    "Confort · priorité chauffage": HeaterPreset(HEATER_COMFORT, True),
    "Boost · priorité chauffage": HeaterPreset(HEATER_BOOST, True),
    "Planning · priorité chauffage": HeaterPreset(HEATER_PLANNING, True),
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the heat-pump climate entity when a heater is present."""
    coordinator: ImagixDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    heater = _state(coordinator.data, "heater")
    if heater.get("presence"):
        async_add_entities(
            [ImagixHeaterClimate(coordinator, config_entry.entry_id)]
        )


class ImagixHeaterClimate(ImagixEntity, ClimateEntity):
    """Expose all regular heat-pump controls through one climate card."""

    _attr_has_entity_name = True
    _attr_name = "Chauffage piscine"
    _attr_icon = "mdi:heat-pump"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.AUTO]
    _attr_preset_modes = list(PRESETS)
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.PRESET_MODE
    )

    def __init__(
        self,
        coordinator: ImagixDataUpdateCoordinator,
        entry_id: str,
    ) -> None:
        """Initialize the climate entity."""
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_heater_climate"
        limits = _state(coordinator.data, "pool", "heater")
        self._attr_min_temp = float(limits.get("tempMin", 15))
        self._attr_max_temp = float(limits.get("tempMax", 45))
        self._attr_target_temperature_step = 0.5

    @property
    def current_temperature(self) -> float | None:
        """Return the measured pool-water temperature."""
        value = _state(self.coordinator.data, "metrics").get("waterTemperature")
        return float(value) if isinstance(value, int | float) else None

    @property
    def target_temperature(self) -> float | None:
        """Return the active heat-pump target."""
        value = _state(self.coordinator.data, "heater").get("setpointActual")
        if isinstance(value, int | float):
            return float(value)
        return self._selected_target()

    @property
    def hvac_mode(self) -> HVACMode:
        """Map the controller mode to Home Assistant's standard HVAC modes."""
        mode = _heater_mode(self.coordinator.data)
        if mode == HEATER_OFF:
            return HVACMode.OFF
        if mode == HEATER_PLANNING:
            return HVACMode.AUTO
        return HVACMode.HEAT

    @property
    def preset_mode(self) -> str | None:
        """Return the current mode and filtration-priority combination."""
        heater = _state(self.coordinator.data, "heater")
        mode = heater.get("mode")
        priority = bool(heater.get("filtrationPriority"))
        for name, preset in PRESETS.items():
            if preset.mode == mode and preset.priority == priority:
                return name
        return None

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return whether the heat pump appears to be heating."""
        heater = _state(self.coordinator.data, "heater")
        if heater.get("mode") == HEATER_OFF:
            return HVACAction.OFF
        if any(heater.get(key, 0) for key in ("pacState", "pumpState")):
            return HVACAction.HEATING
        if heater.get("state") in (1, 2, 3):
            return HVACAction.HEATING
        return HVACAction.IDLE

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the secondary targets and the priority schedule."""
        heater = _state(self.coordinator.data, "heater")
        return {
            "temperature_eco": _tenths_to_temperature(
                heater.get("setpointModeEco")
            ),
            "temperature_confort": _tenths_to_temperature(
                heater.get("setpointModeConfort")
            ),
            "priorite_filtration_chauffage": bool(
                heater.get("filtrationPriority")
            ),
            "planning_priorite_chauffage": heater.get(
                "planningAuthorization", []
            ),
            "planning_mode_chauffage": heater.get("planningMode", []),
        }

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set Off, Heat or Auto from the climate card."""
        current_mode = _heater_mode(self.coordinator.data)
        if hvac_mode == HVACMode.OFF:
            mode = HEATER_OFF
        elif hvac_mode == HVACMode.AUTO:
            mode = HEATER_PLANNING
        elif hvac_mode == HVACMode.HEAT:
            mode = current_mode if current_mode in (1, 2, 3) else HEATER_COMFORT
        else:
            return

        await self._async_execute(
            self.coordinator.client.async_set_heater_settings(
                mode,
                bool(_state(self.coordinator.data, "heater").get("filtrationPriority")),
            )
        )

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set one of the controller modes from the climate card."""
        preset = PRESETS.get(preset_mode)
        if preset is None:
            return
        await self._async_execute(
            self.coordinator.client.async_set_heater_settings(
                preset.mode, preset.priority
            )
        )

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Update the Eco or Comfort target used by the active mode."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if not isinstance(temperature, int | float):
            return

        mode = _heater_mode(self.coordinator.data)
        if mode == HEATER_ECO:
            command = self.coordinator.client.async_set_heater_eco_temperature(
                float(temperature)
            )
        else:
            # Boost and Planning use the active Comfort target unless the
            # active setpoint is closer to the Eco target.
            if mode == HEATER_PLANNING and self._active_target_is_eco():
                command = self.coordinator.client.async_set_heater_eco_temperature(
                    float(temperature)
                )
            else:
                command = self.coordinator.client.async_set_heater_comfort_temperature(
                    float(temperature)
                )
        await self._async_execute(command)

    def _selected_target(self) -> float | None:
        """Return the configured target for the current heater mode."""
        heater = _state(self.coordinator.data, "heater")
        mode = heater.get("mode")
        if mode == HEATER_ECO:
            return _tenths_to_temperature(heater.get("setpointModeEco"))
        return _tenths_to_temperature(heater.get("setpointModeConfort"))

    def _active_target_is_eco(self) -> bool:
        """Infer the active target while the controller is in Planning mode."""
        heater = _state(self.coordinator.data, "heater")
        actual = heater.get("setpointActual")
        eco = _tenths_to_temperature(heater.get("setpointModeEco"))
        comfort = _tenths_to_temperature(heater.get("setpointModeConfort"))
        if not all(isinstance(value, int | float) for value in (actual, eco, comfort)):
            return False
        return abs(float(actual) - float(eco)) <= abs(float(actual) - float(comfort))


def _state(data: dict[str, Any], *path: str) -> dict[str, Any]:
    """Read a nested state mapping."""
    value: Any = data.get("state", {})
    for key in path:
        if not isinstance(value, dict):
            return {}
        value = value.get(key, {})
    return value if isinstance(value, dict) else {}


def _heater_mode(data: dict[str, Any]) -> int:
    """Read the numeric heater mode."""
    value = _state(data, "heater").get("mode")
    return int(value) if isinstance(value, int) else HEATER_OFF


def _tenths_to_temperature(value: Any) -> float | None:
    """Convert the API's tenth-degree target representation."""
    return float(value) / 10 if isinstance(value, int | float) else None
