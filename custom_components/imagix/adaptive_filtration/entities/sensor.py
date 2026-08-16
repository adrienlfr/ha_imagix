"""Diagnostic sensors for adaptive filtration."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.util import dt as dt_util

from ..manager import AdaptiveFiltrationManager
from .base import AdaptiveFiltrationEntity


@dataclass(frozen=True, slots=True)
class AdaptiveSensorDescription:
    key: str
    name: str
    icon: str
    value_fn: Callable[[AdaptiveFiltrationManager], Any]
    unit: str | None = None
    state_class: SensorStateClass | None = None


def _format_minute(minute: int) -> str:
    if minute == 1440:
        return "24:00"
    return f"{minute // 60:02d}:{minute % 60:02d}"


def _next_segment(manager: AdaptiveFiltrationManager) -> str | None:
    if manager.plan is None:
        return None
    now: datetime = dt_util.now()
    minute = now.hour * 60 + now.minute
    for segment in manager.plan.segments:
        if segment.end_minute > minute:
            return (
                f"{_format_minute(segment.start_minute)}-"
                f"{_format_minute(segment.end_minute)} "
                f"{segment.mode_label.value}"
            )
    return None


DESCRIPTIONS = (
    AdaptiveSensorDescription(
        key="adaptive_filtration_status",
        name="État de la filtration adaptative",
        icon="mdi:state-machine",
        value_fn=lambda manager: manager.status,
    ),
    AdaptiveSensorDescription(
        key="adaptive_filtration_required_efh",
        name="Filtration nécessaire",
        icon="mdi:water-sync",
        unit="EFH",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda manager: (
            manager.plan.required_efh if manager.plan is not None else None
        ),
    ),
    AdaptiveSensorDescription(
        key="adaptive_filtration_planned_efh",
        name="Filtration planifiée",
        icon="mdi:calendar-clock",
        unit="EFH",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda manager: (
            manager.plan.planned_efh if manager.plan is not None else None
        ),
    ),
    AdaptiveSensorDescription(
        key="adaptive_filtration_delivered_efh",
        name="Filtration délivrée",
        icon="mdi:check-circle-outline",
        unit="EFH",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda manager: round(manager.delivered_efh, 3),
    ),
    AdaptiveSensorDescription(
        key="adaptive_filtration_delivered_high_minutes",
        name="Boost délivré aujourd'hui",
        icon="mdi:speedometer",
        unit="min",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda manager: round(manager.delivered_high_minutes, 1),
    ),
    AdaptiveSensorDescription(
        key="adaptive_filtration_estimated_cost",
        name="Coût estimé de la filtration",
        icon="mdi:currency-eur",
        unit="€",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda manager: (
            manager.plan.estimated_cost if manager.plan is not None else None
        ),
    ),
    AdaptiveSensorDescription(
        key="adaptive_filtration_unmet_efh",
        name="Filtration non planifiable en journée",
        icon="mdi:weather-sunset-down",
        unit="EFH",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda manager: (
            manager.plan.unmet_efh if manager.plan is not None else None
        ),
    ),
    AdaptiveSensorDescription(
        key="adaptive_filtration_debt_efh",
        name="Dette de filtration",
        icon="mdi:water-alert-outline",
        unit="EFH",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda manager: round(manager.debt_efh, 3),
    ),
    AdaptiveSensorDescription(
        key="adaptive_filtration_current_profile",
        name="Profil hydraulique actuel",
        icon="mdi:pump",
        value_fn=lambda manager: (
            manager.current_profile.value
            if manager.current_profile is not None
            else "off"
        ),
    ),
    AdaptiveSensorDescription(
        key="adaptive_filtration_data_confidence",
        name="Confiance des données de filtration",
        icon="mdi:gauge",
        value_fn=lambda manager: (
            manager.plan.confidence.value if manager.plan is not None else None
        ),
    ),
    AdaptiveSensorDescription(
        key="adaptive_filtration_next_segment",
        name="Prochain segment de filtration",
        icon="mdi:clock-start",
        value_fn=_next_segment,
    ),
)


def create_adaptive_sensors(
    manager: AdaptiveFiltrationManager,
    entry_id: str,
) -> list["AdaptiveFiltrationSensor"]:
    """Create all adaptive diagnostic sensors."""
    return [
        AdaptiveFiltrationSensor(manager, entry_id, description)
        for description in DESCRIPTIONS
    ]


class AdaptiveFiltrationSensor(AdaptiveFiltrationEntity, SensorEntity):
    """One adaptive filtration diagnostic value."""

    def __init__(
        self,
        manager: AdaptiveFiltrationManager,
        entry_id: str,
        description: AdaptiveSensorDescription,
    ) -> None:
        super().__init__(manager, entry_id)
        self._description = description
        self._attr_unique_id = f"{entry_id}_{description.key}"
        self._attr_name = description.name
        self._attr_icon = description.icon
        self._attr_native_unit_of_measurement = description.unit
        self._attr_state_class = description.state_class

    @property
    def native_value(self) -> Any:
        return self._description.value_fn(self.manager)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self._description.key != "adaptive_filtration_status":
            return None
        return self.manager.plan_attributes
