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
    )

