"""Configuration for adaptive filtration."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .models import HydraulicProfile, ProfileSpec, Strategy

CONF_ADAPTIVE_ENABLED = "adaptive_filtration_enabled"
CONF_STRATEGY = "adaptive_filtration_strategy"
CONF_REFERENCE_VOLUME = "adaptive_reference_volume_m3"
CONF_LOW_FLOW = "adaptive_low_flow_m3h"
CONF_MEDIUM_FLOW = "adaptive_medium_flow_m3h"
CONF_HIGH_FLOW = "adaptive_high_flow_m3h"
CONF_LOW_RPM = "adaptive_low_rpm"
CONF_MEDIUM_RPM = "adaptive_medium_rpm"
CONF_HIGH_RPM = "adaptive_high_rpm"
CONF_MIN_EFH = "adaptive_min_efh"
CONF_MAX_EFH = "adaptive_max_efh"
CONF_MINIMUM_RUN = "adaptive_minimum_run_minutes"
CONF_SOLAR_SHARE = "adaptive_solar_share_target"
CONF_DEBT_LIMIT = "adaptive_debt_carry_limit_efh"
CONF_MINIMUM_HIGH_MINUTES = "adaptive_minimum_high_minutes"
CONF_OFF_PEAK_START = "adaptive_off_peak_start"
CONF_OFF_PEAK_END = "adaptive_off_peak_end"
CONF_OFF_PEAK_PRICE = "adaptive_off_peak_price"
CONF_PEAK_PRICE = "adaptive_peak_price"
CONF_LOW_POWER = "adaptive_low_power_w"
CONF_MEDIUM_POWER = "adaptive_medium_power_w"
CONF_HIGH_POWER = "adaptive_high_power_w"
CONF_DAYLIGHT_MARGIN = "adaptive_daylight_margin_minutes"
CONF_WEATHER_ENTITY = "adaptive_weather_entity_id"
CONF_MINIMUM_MEDIUM_MINUTES = "adaptive_minimum_medium_minutes"

DEFAULT_REFERENCE_FLOW_M3H = 21.0


@dataclass(frozen=True, slots=True)
class AdaptiveFiltrationConfig:
    """Validated settings consumed by the pure engine."""

    enabled: bool = True
    strategy: Strategy = Strategy.BALANCED
    reference_volume_m3: float = 35.0
    reference_flow_m3h: float = DEFAULT_REFERENCE_FLOW_M3H
    low_flow_m3h: float = 14.0
    medium_flow_m3h: float = 21.0
    high_flow_m3h: float = 30.0
    low_rpm: int = 1800
    medium_rpm: int = 2200
    high_rpm: int = 2850
    min_efh: float = 2.0
    max_efh: float = 12.0
    minimum_run_minutes: int = 20
    solar_share_target: float = 0.45
    debt_carry_limit_efh: float = 3.0
    minimum_high_minutes: int = 60
    off_peak_start_minute: int = 22 * 60
    off_peak_end_minute: int = 6 * 60
    off_peak_price: float = 0.15
    peak_price: float = 0.25
    low_power_w: float = 353.0
    medium_power_w: float = 610.0
    high_power_w: float = 1266.0
    daylight_margin_minutes: int = 0
    weather_entity_id: str | None = None
    minimum_medium_minutes: int = 60

    @property
    def profiles(self) -> dict[HydraulicProfile, ProfileSpec]:
        """Return the three physical profiles and verified controller modes."""
        return {
            HydraulicProfile.LOW: ProfileSpec(
                HydraulicProfile.LOW,
                self.low_rpm,
                self.low_flow_m3h,
                4,
            ),
            HydraulicProfile.MEDIUM: ProfileSpec(
                HydraulicProfile.MEDIUM,
                self.medium_rpm,
                self.medium_flow_m3h,
                3,
            ),
            HydraulicProfile.HIGH: ProfileSpec(
                HydraulicProfile.HIGH,
                self.high_rpm,
                self.high_flow_m3h,
                1,
            ),
        }

    @property
    def profile_power_w(self) -> dict[HydraulicProfile, float]:
        """Return configured electrical power for cost optimization."""
        return {
            HydraulicProfile.LOW: self.low_power_w,
            HydraulicProfile.MEDIUM: self.medium_power_w,
            HydraulicProfile.HIGH: self.high_power_w,
        }

    def is_off_peak(self, minute: int) -> bool:
        """Return whether a local minute belongs to the recurring HC window."""
        start = self.off_peak_start_minute
        end = self.off_peak_end_minute
        if start == end:
            return False
        if start < end:
            return start <= minute < end
        return minute >= start or minute < end

    def tariff_at(self, minute: int) -> float:
        """Return the configured electricity price for one local minute."""
        return self.off_peak_price if self.is_off_peak(minute) else self.peak_price


def load_config(options: Mapping[str, Any]) -> AdaptiveFiltrationConfig:
    """Build and validate adaptive configuration from config entry options."""

    def number(key: str, default: float, minimum: float) -> float:
        value = options.get(key, default)
        try:
            return max(minimum, float(value))
        except (TypeError, ValueError):
            return default

    def integer(key: str, default: int, minimum: int) -> int:
        value = options.get(key, default)
        try:
            return max(minimum, int(value))
        except (TypeError, ValueError):
            return default

    def time_minute(key: str, default: str) -> int:
        value = str(options.get(key, default))
        try:
            hour_text, minute_text = value.split(":", maxsplit=1)
            hour = int(hour_text)
            minute = int(minute_text)
        except (TypeError, ValueError):
            return _time_to_minute(default)
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            return _time_to_minute(default)
        return hour * 60 + minute

    try:
        strategy = Strategy(str(options.get(CONF_STRATEGY, Strategy.BALANCED)))
    except ValueError:
        strategy = Strategy.BALANCED

    min_efh = number(CONF_MIN_EFH, 2.0, 0.0)
    max_efh = max(min_efh, number(CONF_MAX_EFH, 12.0, min_efh))

    return AdaptiveFiltrationConfig(
        enabled=bool(options.get(CONF_ADAPTIVE_ENABLED, True)),
        strategy=strategy,
        reference_volume_m3=number(CONF_REFERENCE_VOLUME, 35.0, 1.0),
        low_flow_m3h=number(CONF_LOW_FLOW, 14.0, 0.1),
        medium_flow_m3h=number(CONF_MEDIUM_FLOW, 21.0, 0.1),
        high_flow_m3h=number(CONF_HIGH_FLOW, 30.0, 0.1),
        low_rpm=integer(CONF_LOW_RPM, 1800, 1),
        medium_rpm=integer(CONF_MEDIUM_RPM, 2200, 1),
        high_rpm=integer(CONF_HIGH_RPM, 2850, 1),
        min_efh=min_efh,
        max_efh=max_efh,
        minimum_run_minutes=integer(CONF_MINIMUM_RUN, 20, 1),
        solar_share_target=min(
            1.0,
            number(CONF_SOLAR_SHARE, 0.45, 0.0),
        ),
        debt_carry_limit_efh=number(CONF_DEBT_LIMIT, 3.0, 0.0),
        minimum_high_minutes=integer(CONF_MINIMUM_HIGH_MINUTES, 60, 0),
        off_peak_start_minute=time_minute(CONF_OFF_PEAK_START, "22:00"),
        off_peak_end_minute=time_minute(CONF_OFF_PEAK_END, "06:00"),
        off_peak_price=number(CONF_OFF_PEAK_PRICE, 0.15, 0.0),
        peak_price=number(CONF_PEAK_PRICE, 0.25, 0.0),
        low_power_w=number(CONF_LOW_POWER, 353.0, 0.0),
        medium_power_w=number(CONF_MEDIUM_POWER, 610.0, 0.0),
        high_power_w=number(CONF_HIGH_POWER, 1266.0, 0.0),
        daylight_margin_minutes=integer(CONF_DAYLIGHT_MARGIN, 0, 0),
        weather_entity_id=(
            str(options.get(CONF_WEATHER_ENTITY, "")).strip() or None
        ),
        minimum_medium_minutes=integer(CONF_MINIMUM_MEDIUM_MINUTES, 60, 0),
    )


def _time_to_minute(value: str) -> int:
    hour_text, minute_text = value.split(":", maxsplit=1)
    return int(hour_text) * 60 + int(minute_text)
