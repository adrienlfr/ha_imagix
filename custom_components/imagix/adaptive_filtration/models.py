"""Domain models used by the adaptive filtration engine."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Any


class HydraulicProfile(StrEnum):
    """Physical pump operating points."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ModeLabel(StrEnum):
    """User-facing reasons for selecting a physical profile."""

    ECO = "eco"
    MEDIUM = "medium"
    OPTIMIZED_FLOW = "optimized_flow"
    BOOST = "boost"


class Strategy(StrEnum):
    """Global scheduling strategy."""

    ECO = "eco"
    BALANCED = "balanced"
    QUALITY = "quality"


class DataConfidence(StrEnum):
    """Confidence in the data used to build a plan."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True, slots=True)
class ProfileSpec:
    """Hydraulic and controller properties for one physical profile."""

    profile: HydraulicProfile
    rpm: int
    flow_m3h: float
    controller_mode: int

    def efh_per_hour(self, reference_flow_m3h: float) -> float:
        """Return EFH delivered by one hour at this profile."""
        return self.flow_m3h / reference_flow_m3h


@dataclass(frozen=True, slots=True)
class FiltrationInputs:
    """Normalized data used by the pure calculation engine."""

    now: datetime
    water_temperature: float | None
    pool_volume_m3: float | None
    orp_mv: float | None
    ph: float | None
    pump_running: bool
    pump_rpm: int | None
    confidence: DataConfidence


@dataclass(frozen=True, slots=True)
class WeatherPoint:
    """Normalized hourly weather forecast point."""

    at: datetime
    temperature_c: float | None = None
    cloud_coverage: float | None = None
    uv_index: float | None = None
    precipitation_mm: float | None = None
    precipitation_probability: float | None = None
    wind_speed_kmh: float | None = None
    condition: str | None = None


@dataclass(frozen=True, slots=True)
class WeatherContext:
    """Current weather and forecasts used by the adaptive engine."""

    entity_id: str | None = None
    current_condition: str | None = None
    points: tuple[WeatherPoint, ...] = ()
    available: bool = False


@dataclass(frozen=True, slots=True)
class TargetResult:
    """Result of the daily filtration load calculation."""

    base_efh: float
    required_efh: float
    volume_factor: float
    water_quality_factor: float
    environment_factor: float
    weather_bonus_efh: float
    confidence: DataConfidence
    recovery_required: bool = False
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PlanSegment:
    """One continuous filtration segment in local minutes since midnight."""

    start_minute: int
    end_minute: int
    profile: HydraulicProfile
    mode_label: ModeLabel
    rpm: int
    flow_m3h: float
    planned_efh: float
    reason: str

    @property
    def duration_minutes(self) -> int:
        """Return segment duration."""
        return self.end_minute - self.start_minute

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "start_minute": self.start_minute,
            "end_minute": self.end_minute,
            "profile": self.profile.value,
            "mode_label": self.mode_label.value,
            "rpm": self.rpm,
            "flow_m3h": round(self.flow_m3h, 3),
            "planned_efh": round(self.planned_efh, 3),
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class DailyPlan:
    """Complete adaptive plan for one local day."""

    day: date
    required_efh: float
    planned_efh: float
    confidence: DataConfidence
    strategy: Strategy
    sunrise_minute: int
    sunset_minute: int
    estimated_cost: float = 0.0
    off_peak_minutes: int = 0
    high_minutes: float = 0.0
    medium_minutes: float = 0.0
    peak_weather_minute: int | None = None
    weather_entity_id: str | None = None
    unmet_efh: float = 0.0
    daylight_limited: bool = False
    segments: tuple[PlanSegment, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "date": self.day.isoformat(),
            "required_efh": round(self.required_efh, 3),
            "planned_efh": round(self.planned_efh, 3),
            "confidence": self.confidence.value,
            "strategy": self.strategy.value,
            "sunrise_minute": self.sunrise_minute,
            "sunset_minute": self.sunset_minute,
            "estimated_cost": round(self.estimated_cost, 3),
            "off_peak_minutes": self.off_peak_minutes,
            "high_minutes": round(self.high_minutes, 1),
            "medium_minutes": round(self.medium_minutes, 1),
            "peak_weather_minute": self.peak_weather_minute,
            "weather_entity_id": self.weather_entity_id,
            "unmet_efh": round(self.unmet_efh, 3),
            "daylight_limited": self.daylight_limited,
            "segments": [segment.as_dict() for segment in self.segments],
        }
