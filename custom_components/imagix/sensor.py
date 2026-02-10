"""Platform for sensor integration."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfTemperature,
    UnitOfVolume,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ImagixDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ImagixSensorEntityDescription(SensorEntityDescription):
    """Describes iMagi-x sensor entity."""

    value_fn: Callable[[dict[str, Any]], Any] | None = None


SENSORS: tuple[ImagixSensorEntityDescription, ...] = (
    ImagixSensorEntityDescription(
        key="water_temperature",
        translation_key="water_temperature",
        name="Température de l'eau",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda data: data.get("state", {}).get("metrics", {}).get("waterTemperature"),
    ),
    ImagixSensorEntityDescription(
        key="air_temperature",
        translation_key="air_temperature",
        name="Température de l'air",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda data: data.get("state", {}).get("metrics", {}).get("airTemperature"),
    ),
    ImagixSensorEntityDescription(
        key="ph",
        translation_key="ph",
        name="pH",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:ph",
        value_fn=lambda data: data.get("state", {}).get("metrics", {}).get("ph"),
    ),
    ImagixSensorEntityDescription(
        key="orp",
        translation_key="orp",
        name="ORP (Redox)",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="mV",
        icon="mdi:water-check",
        value_fn=lambda data: data.get("state", {}).get("metrics", {}).get("orp"),
    ),
    ImagixSensorEntityDescription(
        key="filtration_state",
        translation_key="filtration_state",
        name="État de la filtration",
        device_class=SensorDeviceClass.ENUM,
        options=["arrêt", "marche", "eco", "boost"],
        icon="mdi:air-filter",
        value_fn=lambda data: _get_filtration_state(data),
    ),
    ImagixSensorEntityDescription(
        key="filtration_mode",
        translation_key="filtration_mode",
        name="Mode de filtration",
        device_class=SensorDeviceClass.ENUM,
        options=["manuel", "auto", "nage", "pause", "hivernal"],
        icon="mdi:tune",
        value_fn=lambda data: _get_filtration_mode(data),
    ),
    ImagixSensorEntityDescription(
        key="pool_volume",
        translation_key="pool_volume",
        name="Volume du bassin",
        device_class=SensorDeviceClass.VOLUME,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        icon="mdi:pool",
        value_fn=lambda data: data.get("state", {}).get("pool", {}).get("informations", {}).get("volume"),
    ),
    ImagixSensorEntityDescription(
        key="filter_clogging",
        translation_key="filter_clogging",
        name="Colmatage du filtre",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:air-filter",
        value_fn=lambda data: data.get("state", {}).get("metrics", {}).get("filterClogging"),
    ),
    ImagixSensorEntityDescription(
        key="pump_rpm",
        translation_key="pump_rpm",
        name="Vitesse de la pompe",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="rpm",
        icon="mdi:pump",
        value_fn=lambda data: data.get("state", {}).get("pool", {}).get("pumps", {}).get("pumpFx1", {}).get("rpm"),
    ),
    ImagixSensorEntityDescription(
        key="system_uptime",
        translation_key="system_uptime",
        name="Temps de fonctionnement",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement="s",
        icon="mdi:timer",
        value_fn=lambda data: data.get("state", {}).get("system", {}).get("info", {}).get("uptime"),
    ),
)


def _get_filtration_state(data: dict[str, Any]) -> str:
    """Get filtration state as a readable string."""
    state = data.get("state", {}).get("filtration", {}).get("state", 0)
    state_map = {
        0: "arrêt",
        1: "marche",
        2: "eco",
        3: "boost",
    }
    return state_map.get(state, "inconnu")


def _get_filtration_mode(data: dict[str, Any]) -> str:
    """Get filtration mode as a readable string."""
    mode = data.get("state", {}).get("filtration", {}).get("mode", 0)
    mode_map = {
        0: "manuel",
        1: "auto",
        2: "nage",
        3: "pause",
        4: "hivernal",
    }
    return mode_map.get(mode, "inconnu")


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    coordinator: ImagixDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    
    async_add_entities(
        ImagixSensor(coordinator, description, config_entry.entry_id)
        for description in SENSORS
    )


class ImagixSensor(CoordinatorEntity[ImagixDataUpdateCoordinator], SensorEntity):
    """Representation of an iMagi-x Sensor."""

    entity_description: ImagixSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ImagixDataUpdateCoordinator,
        description: ImagixSensorEntityDescription,
        entry_id: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry_id}_{description.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": "iMagi-x Pool Controller",
            "manufacturer": "iMagi-x",
            "model": "Pool Controller",
        }

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        if self.entity_description.value_fn is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)
