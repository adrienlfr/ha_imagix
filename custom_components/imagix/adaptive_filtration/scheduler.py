"""Pure daily schedule builder."""
from __future__ import annotations

from dataclasses import dataclass
from math import ceil

from .config import AdaptiveFiltrationConfig
from .models import (
    DailyPlan,
    FiltrationInputs,
    HydraulicProfile,
    ModeLabel,
    PlanSegment,
    TargetResult,
    Strategy,
)
from .profiles import delivered_efh


@dataclass(frozen=True, slots=True)
class _Allocation:
    profile: HydraulicProfile
    label: ModeLabel
    required_efh: float
    reason: str


def build_daily_plan(
    inputs: FiltrationInputs,
    target: TargetResult,
    config: AdaptiveFiltrationConfig,
    solar_noon_minute: int = 13 * 60,
    delivered_today_efh: float = 0.0,
) -> DailyPlan:
    """Allocate target EFH around local solar noon with few starts."""
    credited_efh = min(target.required_efh, max(0.0, delivered_today_efh))
    remaining = max(0.0, target.required_efh - credited_efh)
    allocations: list[_Allocation] = []

    if target.recovery_required:
        recovery_efh = min(1.0, remaining)
        allocations.append(
            _Allocation(
                HydraulicProfile.HIGH,
                ModeLabel.BOOST,
                recovery_efh,
                "water_quality_recovery",
            )
        )
        remaining -= recovery_efh

    if config.strategy is Strategy.ECO and remaining > 0:
        medium_efh = min(remaining, max(0.5, remaining * config.solar_share_target))
        low_efh = max(0.0, remaining - medium_efh)
        if low_efh:
            allocations.append(
                _Allocation(
                    HydraulicProfile.LOW,
                    ModeLabel.ECO,
                    low_efh,
                    "economy",
                )
            )
        if medium_efh:
            allocations.append(
                _Allocation(
                    HydraulicProfile.MEDIUM,
                    ModeLabel.OPTIMIZED_FLOW,
                    medium_efh,
                    "solar_window",
                )
            )
    elif remaining > 0:
        label = (
            ModeLabel.OPTIMIZED_FLOW
            if config.solar_share_target > 0
            else ModeLabel.MEDIUM
        )
        allocations.append(
            _Allocation(
                HydraulicProfile.MEDIUM,
                label,
                remaining,
                "solar_window" if label is ModeLabel.OPTIMIZED_FLOW else "daily_need",
            )
        )

    durations = [_duration_for(allocation, config) for allocation in allocations]
    total_duration = sum(durations)
    if total_duration > 20 * 60:
        # Avoid an unrealistic LOW-heavy plan: deliver the flexible part at MEDIUM.
        allocations = [
            _Allocation(
                allocation.profile
                if allocation.profile is HydraulicProfile.HIGH
                else HydraulicProfile.MEDIUM,
                allocation.label
                if allocation.profile is HydraulicProfile.HIGH
                else ModeLabel.OPTIMIZED_FLOW,
                allocation.required_efh,
                allocation.reason,
            )
            for allocation in allocations
        ]
        durations = [_duration_for(allocation, config) for allocation in allocations]
        total_duration = sum(durations)

    start_minute = max(
        0,
        min(1440 - total_duration, solar_noon_minute - total_duration // 2),
    )
    current_minute = inputs.now.hour * 60 + inputs.now.minute
    future_start = current_minute + 5
    if start_minute < future_start and future_start + total_duration <= 1440:
        start_minute = future_start
    cursor = start_minute
    segments: list[PlanSegment] = []
    for allocation, duration in zip(allocations, durations):
        profile = config.profiles[allocation.profile]
        efh = delivered_efh(duration, profile, config.reference_flow_m3h)
        segments.append(
            PlanSegment(
                start_minute=cursor,
                end_minute=cursor + duration,
                profile=allocation.profile,
                mode_label=allocation.label,
                rpm=profile.rpm,
                flow_m3h=profile.flow_m3h,
                planned_efh=round(efh, 3),
                reason=allocation.reason,
            )
        )
        cursor += duration

    planned = credited_efh + sum(segment.planned_efh for segment in segments)
    return DailyPlan(
        day=inputs.now.date(),
        required_efh=target.required_efh,
        planned_efh=round(planned, 3),
        confidence=target.confidence,
        strategy=config.strategy,
        segments=tuple(segments),
    )


def _duration_for(
    allocation: _Allocation,
    config: AdaptiveFiltrationConfig,
) -> int:
    profile = config.profiles[allocation.profile]
    minutes = ceil(
        allocation.required_efh
        / profile.efh_per_hour(config.reference_flow_m3h)
        * 60
    )
    return max(config.minimum_run_minutes, minutes)
