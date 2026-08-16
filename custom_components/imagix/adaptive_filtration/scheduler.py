"""Pure daylight and electricity-cost optimized schedule builder."""
from __future__ import annotations

from dataclasses import dataclass
from itertools import permutations
from math import ceil

from .config import AdaptiveFiltrationConfig
from .models import (
    DailyPlan,
    FiltrationInputs,
    HydraulicProfile,
    ModeLabel,
    PlanSegment,
    TargetResult,
)
from .profiles import delivered_efh

_STEP_MINUTES = 5
_MAX_PLACEMENT_CANDIDATES = 500


@dataclass(frozen=True, slots=True)
class _Candidate:
    """Profile durations that meet the hydraulic constraints."""

    durations: tuple[tuple[HydraulicProfile, int], ...]
    efh: float
    lower_cost: float

    @property
    def total_minutes(self) -> int:
        return sum(duration for _, duration in self.durations)


@dataclass(frozen=True, slots=True)
class _Placement:
    """A candidate placed inside the usable daylight window."""

    ordered_durations: tuple[tuple[HydraulicProfile, int], ...]
    start_minute: int
    cost: float
    off_peak_minutes: int


def build_daily_plan(
    inputs: FiltrationInputs,
    target: TargetResult,
    config: AdaptiveFiltrationConfig,
    solar_noon_minute: int = 13 * 60,
    sunrise_minute: int = 8 * 60,
    sunset_minute: int = 20 * 60,
    delivered_today_efh: float = 0.0,
    delivered_high_minutes: float = 0.0,
) -> DailyPlan:
    """Build the cheapest feasible plan strictly inside daylight hours."""
    daylight_start = max(0, sunrise_minute + config.daylight_margin_minutes)
    daylight_end = min(1440, sunset_minute - config.daylight_margin_minutes)
    current_minute = inputs.now.hour * 60 + inputs.now.minute
    usable_start = daylight_start
    if daylight_start <= current_minute < daylight_end:
        usable_start = min(daylight_end, _round_up(current_minute + 5))
    elif current_minute >= daylight_end:
        usable_start = daylight_end

    credited_efh = min(target.required_efh, max(0.0, delivered_today_efh))
    remaining_efh = max(0.0, target.required_efh - credited_efh)
    # Until a full hour has been confirmed, keep one continuous HIGH segment in
    # the future plan. This is deliberately stricter than merely topping up a
    # possibly fragmented daily counter.
    mandatory_high = (
        config.minimum_high_minutes
        if delivered_high_minutes + 0.01 < config.minimum_high_minutes
        else 0
    )
    available_minutes = max(0, daylight_end - usable_start)
    minimum_tariff = (
        min(config.tariff_at(minute) for minute in range(daylight_start, daylight_end))
        if daylight_end > daylight_start
        else min(config.off_peak_price, config.peak_price)
    )
    tariff_prefix = _tariff_prefix(config)
    off_peak_prefix = _off_peak_prefix(config)
    candidates = _build_candidates(
        remaining_efh,
        mandatory_high,
        available_minutes,
        config,
        minimum_tariff,
    )
    placement = _best_placement(
        candidates,
        usable_start,
        daylight_end,
        solar_noon_minute,
        tariff_prefix,
        off_peak_prefix,
        config,
    )

    if placement is None and available_minutes > 0:
        # The hydraulic target does not fit. Use all remaining daylight at HIGH;
        # never escape the solar window to hide an infeasible requirement.
        placement = _Placement(
            ((HydraulicProfile.HIGH, available_minutes),),
            usable_start,
            _segment_cost(
                HydraulicProfile.HIGH,
                usable_start,
                daylight_end,
                tariff_prefix,
                config,
            ),
            _off_peak_minutes(usable_start, daylight_end, off_peak_prefix),
        )

    segments = _segments_from_placement(placement, target, config)
    scheduled_efh = sum(segment.planned_efh for segment in segments)
    planned_efh = credited_efh + scheduled_efh
    scheduled_high = sum(
        segment.duration_minutes
        for segment in segments
        if segment.profile is HydraulicProfile.HIGH
    )
    high_minutes = delivered_high_minutes + scheduled_high
    unmet_efh = max(0.0, target.required_efh - planned_efh)
    high_unmet = high_minutes + 0.01 < config.minimum_high_minutes

    return DailyPlan(
        day=inputs.now.date(),
        required_efh=target.required_efh,
        planned_efh=round(planned_efh, 3),
        confidence=target.confidence,
        strategy=config.strategy,
        sunrise_minute=daylight_start,
        sunset_minute=daylight_end,
        estimated_cost=round(placement.cost, 4) if placement is not None else 0.0,
        off_peak_minutes=placement.off_peak_minutes if placement is not None else 0,
        high_minutes=round(high_minutes, 1),
        unmet_efh=round(unmet_efh, 3),
        daylight_limited=unmet_efh > 0.001 or high_unmet,
        segments=segments,
    )


def _build_candidates(
    required_efh: float,
    mandatory_high: int,
    available_minutes: int,
    config: AdaptiveFiltrationConfig,
    minimum_tariff: float,
) -> list[_Candidate]:
    if available_minutes <= 0:
        return []

    minimum_run = _round_up(config.minimum_run_minutes)
    first_high = _round_up(max(mandatory_high, minimum_run if mandatory_high else 0))
    high_values = range(first_high, available_minutes + 1, _STEP_MINUTES)
    profiles = config.profiles
    powers = config.profile_power_w
    candidates: list[_Candidate] = []
    for high_minutes in high_values:
        space_after_high = available_minutes - high_minutes
        medium_values = [0]
        if space_after_high >= minimum_run:
            medium_values.extend(range(minimum_run, space_after_high + 1, _STEP_MINUTES))
        for medium_minutes in medium_values:
            high_efh = delivered_efh(
                high_minutes,
                profiles[HydraulicProfile.HIGH],
                config.reference_flow_m3h,
            )
            medium_efh = delivered_efh(
                medium_minutes,
                profiles[HydraulicProfile.MEDIUM],
                config.reference_flow_m3h,
            )
            residual = max(0.0, required_efh - high_efh - medium_efh)
            low_rate = profiles[HydraulicProfile.LOW].efh_per_hour(
                config.reference_flow_m3h
            )
            low_minutes = _round_up(ceil(residual / low_rate * 60)) if residual else 0
            if 0 < low_minutes < minimum_run:
                low_minutes = minimum_run
            if high_minutes + medium_minutes + low_minutes > available_minutes:
                continue

            durations = tuple(
                (profile, duration)
                for profile, duration in (
                    (HydraulicProfile.HIGH, high_minutes),
                    (HydraulicProfile.MEDIUM, medium_minutes),
                    (HydraulicProfile.LOW, low_minutes),
                )
                if duration > 0
            )
            efh = sum(
                delivered_efh(duration, profiles[profile], config.reference_flow_m3h)
                for profile, duration in durations
            )
            energy_kwh = sum(
                powers[profile] * duration / 60 / 1000
                for profile, duration in durations
            )
            candidates.append(
                _Candidate(durations, efh, energy_kwh * minimum_tariff)
            )
    return sorted(candidates, key=lambda item: (item.lower_cost, item.total_minutes))


def _best_placement(
    candidates: list[_Candidate],
    daylight_start: int,
    daylight_end: int,
    solar_noon: int,
    tariff_prefix: list[float],
    off_peak_prefix: list[int],
    config: AdaptiveFiltrationConfig,
) -> _Placement | None:
    best: _Placement | None = None
    best_key: tuple[float, int, int] | None = None
    for candidate in candidates[:_MAX_PLACEMENT_CANDIDATES]:
        if best_key is not None and candidate.lower_cost > best_key[0] + 1e-9:
            break
        latest_start = daylight_end - candidate.total_minutes
        unique_orders = set(permutations(candidate.durations))
        for start in range(_round_up(daylight_start), latest_start + 1, _STEP_MINUTES):
            for order in unique_orders:
                cursor = start
                cost = 0.0
                off_peak = 0
                for profile, duration in order:
                    end = cursor + duration
                    cost += _segment_cost(profile, cursor, end, tariff_prefix, config)
                    off_peak += _off_peak_minutes(cursor, end, off_peak_prefix)
                    cursor = end
                midpoint_distance = abs(start + candidate.total_minutes // 2 - solar_noon)
                key = (round(cost, 10), midpoint_distance, candidate.total_minutes)
                if best_key is None or key < best_key:
                    best_key = key
                    best = _Placement(order, start, cost, off_peak)
    return best


def _segments_from_placement(
    placement: _Placement | None,
    target: TargetResult,
    config: AdaptiveFiltrationConfig,
) -> tuple[PlanSegment, ...]:
    if placement is None:
        return ()
    cursor = placement.start_minute
    segments: list[PlanSegment] = []
    for profile_name, duration in placement.ordered_durations:
        profile = config.profiles[profile_name]
        if profile_name is HydraulicProfile.HIGH:
            label = ModeLabel.BOOST
            reason = (
                "water_quality_recovery_and_daily_high_minimum"
                if target.recovery_required
                else "daily_high_minimum"
            )
        elif profile_name is HydraulicProfile.MEDIUM:
            label = ModeLabel.OPTIMIZED_FLOW
            reason = "cost_optimized_medium"
        else:
            label = ModeLabel.ECO
            reason = "cost_optimized_eco"
        efh = delivered_efh(duration, profile, config.reference_flow_m3h)
        segments.append(
            PlanSegment(
                start_minute=cursor,
                end_minute=cursor + duration,
                profile=profile_name,
                mode_label=label,
                rpm=profile.rpm,
                flow_m3h=profile.flow_m3h,
                planned_efh=round(efh, 3),
                reason=reason,
            )
        )
        cursor += duration
    return tuple(segments)


def _tariff_prefix(config: AdaptiveFiltrationConfig) -> list[float]:
    prefix = [0.0]
    for minute in range(1440):
        prefix.append(prefix[-1] + config.tariff_at(minute))
    return prefix


def _off_peak_prefix(config: AdaptiveFiltrationConfig) -> list[int]:
    prefix = [0]
    for minute in range(1440):
        prefix.append(prefix[-1] + int(config.is_off_peak(minute)))
    return prefix


def _segment_cost(
    profile: HydraulicProfile,
    start: int,
    end: int,
    tariff_prefix: list[float],
    config: AdaptiveFiltrationConfig,
) -> float:
    tariff_sum = tariff_prefix[end] - tariff_prefix[start]
    return config.profile_power_w[profile] / 1000 / 60 * tariff_sum


def _off_peak_minutes(start: int, end: int, prefix: list[int]) -> int:
    return prefix[end] - prefix[start]


def _round_up(minutes: int) -> int:
    return int(ceil(minutes / _STEP_MINUTES) * _STEP_MINUTES)
