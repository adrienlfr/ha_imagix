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
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfVolume,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

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
        key="water_temperature_flow",
        translation_key="water_temperature_flow",
        name="Température d'eau en circulation",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda data: data.get("state", {})
        .get("metrics", {})
        .get("waterTemperatureFlow"),
    ),
    ImagixSensorEntityDescription(
        key="ph_flow",
        translation_key="ph_flow",
        name="pH en circulation",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:ph",
        value_fn=lambda data: data.get("state", {}).get("metrics", {}).get("phFlow"),
    ),
    ImagixSensorEntityDescription(
        key="orp_flow",
        translation_key="orp_flow",
        name="ORP en circulation",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="mV",
        icon="mdi:water-check",
        value_fn=lambda data: data.get("state", {}).get("metrics", {}).get("orpFlow"),
    ),
    ImagixSensorEntityDescription(
        key="water_temperature_flow_date",
        translation_key="water_temperature_flow_date",
        name="Dernière mesure d'eau en circulation",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock-outline",
        value_fn=lambda data: _get_metric_timestamp(data, "waterTemperatureFlowDate"),
    ),
    ImagixSensorEntityDescription(
        key="ph_flow_date",
        translation_key="ph_flow_date",
        name="Dernière mesure pH en circulation",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock-outline",
        value_fn=lambda data: _get_metric_timestamp(data, "phFlowDate"),
    ),
    ImagixSensorEntityDescription(
        key="orp_flow_date",
        translation_key="orp_flow_date",
        name="Dernière mesure ORP en circulation",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock-outline",
        value_fn=lambda data: _get_metric_timestamp(data, "orpFlowDate"),
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
        options=["automatique", "marche forcée", "arrêt manuel"],
        icon="mdi:tune",
        value_fn=lambda data: _get_filtration_mode(data),
    ),
    ImagixSensorEntityDescription(
        key="pool_volume",
        translation_key="pool_volume",
        name="Volume du bassin",
        device_class=SensorDeviceClass.VOLUME,
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
        key="free_chlorine",
        translation_key="free_chlorine",
        name="Chlore libre",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-check",
        value_fn=lambda data: data.get("state", {}).get("metrics", {}).get("freeChlorine"),
    ),
    ImagixSensorEntityDescription(
        key="salinity",
        translation_key="salinity",
        name="Salinité",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-percent",
        value_fn=lambda data: data.get("state", {}).get("metrics", {}).get("salinity"),
    ),
    ImagixSensorEntityDescription(
        key="water_hardness",
        translation_key="water_hardness",
        name="Dureté de l'eau",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-opacity",
        value_fn=lambda data: data.get("state", {}).get("metrics", {}).get("waterHardness"),
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
        key="pump_power",
        translation_key="pump_power",
        name="Puissance de la pompe",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        icon="mdi:lightning-bolt",
        value_fn=lambda data: _get_pump_power(data),
    ),
    ImagixSensorEntityDescription(
        key="pump_energy_total",
        translation_key="pump_energy_total",
        name="Consommation totale de la pompe",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        icon="mdi:counter",
        value_fn=lambda data: _get_pump_power_total(data),
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


def _get_metric_timestamp(data: dict[str, Any], key: str):
    """Return a valid metric timestamp or None for the controller sentinel."""
    value = data.get("state", {}).get("metrics", {}).get(key)
    if not value or value.startswith("1970-01-01"):
        return None
    return dt_util.parse_datetime(value)


def _get_filtration_mode(data: dict[str, Any]) -> str:
    """Get filtration mode as a readable string."""
    mode = data.get("state", {}).get("filtration", {}).get("mode", 0)
    mode_map = {
        0: "automatique",
        1: "marche forcée",
        2: "arrêt manuel",
    }
    return mode_map.get(mode, "inconnu")


def _get_pump_power(data: dict[str, Any]) -> int | None:
    """Get pump power from pumps array."""
    pumps = data.get("state", {}).get("cards", {}).get("pumps", [])
    if pumps and len(pumps) > 0:
        return pumps[0].get("power")
    return None


def _get_pump_power_total(data: dict[str, Any]) -> int | None:
    """Get total pump energy consumption from pumps array."""
    pumps = data.get("state", {}).get("cards", {}).get("pumps", [])
    if pumps and len(pumps) > 0:
        return pumps[0].get("powerTotal")
    return None


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
