"""Profile resolution and EFH accounting helpers."""
from __future__ import annotations

from .config import AdaptiveFiltrationConfig
from .models import HydraulicProfile, ModeLabel, ProfileSpec

MODE_OFF = 0
MODE_HIGH = 1
MODE_MEDIUM = 3
MODE_LOW = 4
MODE_NATIVE_OPTIMIZED = 7

LABEL_TO_PROFILE = {
    ModeLabel.ECO: HydraulicProfile.LOW,
    ModeLabel.MEDIUM: HydraulicProfile.MEDIUM,
    ModeLabel.OPTIMIZED_FLOW: HydraulicProfile.MEDIUM,
    ModeLabel.BOOST: HydraulicProfile.HIGH,
}


def resolve_label(
    label: ModeLabel,
    config: AdaptiveFiltrationConfig,
) -> ProfileSpec:
    """Resolve a functional label to one of three physical profiles."""
    return config.profiles[LABEL_TO_PROFILE[label]]


def delivered_efh(
    duration_minutes: float,
    profile: ProfileSpec,
    reference_flow_m3h: float,
) -> float:
    """Calculate EFH delivered by a confirmed physical profile."""
    return (
        duration_minutes
        / 60.0
        * profile.efh_per_hour(reference_flow_m3h)
    )

