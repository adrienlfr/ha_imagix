"""Weather, hydraulic-profile and electricity-aware schedule builder."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from math import ceil, floor

from .config import AdaptiveFiltrationConfig
from .environment import heat_score, peak_weather_minute
from .models import (
    DailyPlan,
    FiltrationInputs,
    HydraulicProfile,
    ModeLabel,
    PlanSegment,
    TargetResult,
    WeatherContext,
)
from .policy import ProfilePolicy, policy_for
from .profiles import delivered_efh

_SLOT_MINUTES = 15


@dataclass(frozen=True, slots=True)
class _Allocation:
    """Number of quarter-hour slots assigned to every profile."""

    high: int
    medium: int
    low: int

    @property
    def total(self) -> int:
        return self.high + self.medium + self.low


@dataclass(frozen=True, slots=True)
class _Placement:
    """A continuous run placed inside the usable daylight window."""

    start_minute: int
    profiles: tuple[HydraulicProfile, ...]
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
    delivered_medium_minutes: float = 0.0,
    weather: WeatherContext | None = None,
) -> DailyPlan:
    """Build one continuous, daylight-only run with weather-aware profiles."""
    daylight_start = max(0, sunrise_minute + config.daylight_margin_minutes)
    daylight_end = min(1440, sunset_minute - config.daylight_margin_minutes)
    current_minute = inputs.now.hour * 60 + inputs.now.minute
    planning_day = inputs.now.date()
    effective_efh = max(0.0, delivered_today_efh)
    effective_high = max(0.0, delivered_high_minutes)
    effective_medium = max(0.0, delivered_medium_minutes)
    usable_start = _round_up(daylight_start)
    usable_end = _round_down(daylight_end)

    if daylight_start <= current_minute < daylight_end:
        usable_start = min(usable_end, _round_up(current_minute + 1))
    elif daylight_start < daylight_end and current_minute >= daylight_end:
        # The controller program repeats daily: after sunset, prepare tomorrow.
        planning_day += timedelta(days=1)
        effective_efh = 0.0
        effective_high = 0.0
        effective_medium = 0.0

    credited_efh = min(target.required_efh, effective_efh)
    remaining_efh = max(0.0, target.required_efh - credited_efh)
    available_slots = max(0, (usable_end - usable_start) // _SLOT_MINUTES)
    policy = policy_for(config.strategy)
    allocation = _choose_allocation(
        remaining_efh,
        effective_high,
        effective_medium,
        available_slots,
        target.recovery_required,
        config,
        policy,
    )
    placement = _best_placement(
        allocation,
        usable_start,
        usable_end,
        planning_day,
        sunrise_minute,
        sunset_minute,
        solar_noon_minute,
        weather,
        config,
        policy,
    )

    if allocation is None and available_slots:
        placement = _fallback_placement(usable_start, available_slots, config)

    segments = _segments_from_placement(placement, target, config)
    scheduled_efh = sum(segment.planned_efh for segment in segments)
    planned_efh = credited_efh + scheduled_efh
    scheduled_high = _duration_for(segments, HydraulicProfile.HIGH)
    scheduled_medium = _duration_for(segments, HydraulicProfile.MEDIUM)
    high_minutes = effective_high + scheduled_high
    medium_minutes = effective_medium + scheduled_medium
    unmet_efh = max(0.0, target.required_efh - planned_efh)
    high_unmet = high_minutes + 0.01 < config.minimum_high_minutes
    medium_unmet = medium_minutes + 0.01 < config.minimum_medium_minutes

    return DailyPlan(
        day=planning_day,
        required_efh=target.required_efh,
        planned_efh=round(planned_efh, 3),
        confidence=target.confidence,
        strategy=config.strategy,
        sunrise_minute=daylight_start,
        sunset_minute=daylight_end,
        estimated_cost=round(placement.cost, 4) if placement else 0.0,
        off_peak_minutes=placement.off_peak_minutes if placement else 0,
        high_minutes=round(high_minutes, 1),
        medium_minutes=round(medium_minutes, 1),
        peak_weather_minute=peak_weather_minute(
            weather,
            planning_day,
            solar_noon_minute,
        ),
        weather_entity_id=weather.entity_id if weather else None,
        unmet_efh=round(unmet_efh, 3),
        daylight_limited=unmet_efh > 0.001 or high_unmet or medium_unmet,
        segments=segments,
    )


def _choose_allocation(
    remaining_efh: float,
    delivered_high_minutes: float,
    delivered_medium_minutes: float,
    available_slots: int,
    recovery_required: bool,
    config: AdaptiveFiltrationConfig,
    policy: ProfilePolicy,
) -> _Allocation | None:
    """Choose a useful profile mix before deciding when it should run."""
    high_minutes = max(0.0, config.minimum_high_minutes - delivered_high_minutes)
    if recovery_required:
        high_minutes += 2 * _SLOT_MINUTES
    high_slots = ceil(high_minutes / _SLOT_MINUTES)
    medium_minutes = max(
        0.0,
        config.minimum_medium_minutes - delivered_medium_minutes,
    )
    minimum_medium_slots = ceil(medium_minutes / _SLOT_MINUTES)
    if high_slots + minimum_medium_slots > available_slots:
        return None

    high_efh = _slot_efh(HydraulicProfile.HIGH, config) * high_slots
    best: _Allocation | None = None
    best_key: tuple[float, float, float, int] | None = None
    for medium_slots in range(minimum_medium_slots, available_slots - high_slots + 1):
        medium_efh = _slot_efh(HydraulicProfile.MEDIUM, config) * medium_slots
        residual = max(0.0, remaining_efh - high_efh - medium_efh)
        low_slot_efh = _slot_efh(HydraulicProfile.LOW, config)
        low_slots = ceil(residual / low_slot_efh - 1e-9) if residual else 0
        if high_slots + medium_slots + low_slots > available_slots:
            continue

        low_efh = low_slot_efh * low_slots
        flexible = medium_efh + low_efh
        medium_share = medium_efh / flexible if flexible else 1.0
        share_distance = abs(medium_share - policy.medium_share_of_flexible_efh)
        total_efh = high_efh + flexible
        excess = max(0.0, total_efh - remaining_efh)
        energy = (
            config.profile_power_w[HydraulicProfile.HIGH] * high_slots
            + config.profile_power_w[HydraulicProfile.MEDIUM] * medium_slots
            + config.profile_power_w[HydraulicProfile.LOW] * low_slots
        )
        key = (round(share_distance, 5), round(excess, 5), energy, medium_slots)
        if best_key is None or key < best_key:
            best_key = key
            best = _Allocation(high_slots, medium_slots, low_slots)
    return best


def _best_placement(
    allocation: _Allocation | None,
    usable_start: int,
    usable_end: int,
    day: date,
    sunrise: int,
    sunset: int,
    solar_noon: int,
    weather: WeatherContext | None,
    config: AdaptiveFiltrationConfig,
    policy: ProfilePolicy,
) -> _Placement | None:
    if allocation is None or allocation.total <= 0:
        return None
    latest_start = usable_end - allocation.total * _SLOT_MINUTES
    best: _Placement | None = None
    best_key: tuple[float, float, float] | None = None

    for start in range(usable_start, latest_start + 1, _SLOT_MINUTES):
        for low_before in range(allocation.low + 1):
            core_start = start + low_before * _SLOT_MINUTES
            core = _weather_core_profiles(
                allocation.high,
                allocation.medium,
                core_start,
                day,
                sunrise,
                sunset,
                solar_noon,
                weather,
                config,
                policy,
            )
            profiles = (
                (HydraulicProfile.LOW,) * low_before
                + core
                + (HydraulicProfile.LOW,) * (allocation.low - low_before)
            )
            score = _placement_score(
                profiles,
                start,
                day,
                sunrise,
                sunset,
                solar_noon,
                weather,
                config,
                policy,
            )
            cost, off_peak = _placement_cost(profiles, start, config)
            midpoint = start + allocation.total * _SLOT_MINUTES / 2
            peak = peak_weather_minute(weather, day, solar_noon)
            key = (-round(score, 6), round(cost, 6), abs(midpoint - peak))
            if best_key is None or key < best_key:
                best_key = key
                best = _Placement(start, profiles, cost, off_peak)
    return best


def _weather_core_profiles(
    high_slots: int,
    medium_slots: int,
    start: int,
    day: date,
    sunrise: int,
    sunset: int,
    solar_noon: int,
    weather: WeatherContext | None,
    config: AdaptiveFiltrationConfig,
    policy: ProfilePolicy,
) -> tuple[HydraulicProfile, ...]:
    """Spread HIGH slots across the warm core instead of grouping them."""
    size = high_slots + medium_slots
    if not size:
        return ()
    result = [HydraulicProfile.MEDIUM] * size
    if high_slots >= size:
        return (HydraulicProfile.HIGH,) * size

    selected: set[int] = set()
    for zone in range(high_slots):
        zone_start = floor(zone * size / high_slots)
        zone_end = max(zone_start + 1, floor((zone + 1) * size / high_slots))
        candidates = [index for index in range(zone_start, min(size, zone_end))]
        non_adjacent = [
            index
            for index in candidates
            if index - 1 not in selected and index + 1 not in selected
        ]
        if non_adjacent:
            candidates = non_adjacent
        chosen = max(
            candidates,
            key=lambda index: _high_slot_value(
                start + index * _SLOT_MINUTES,
                day,
                sunrise,
                sunset,
                solar_noon,
                weather,
                config,
                policy,
            ),
        )
        selected.add(chosen)
    for index in selected:
        result[index] = HydraulicProfile.HIGH
    return tuple(result)


def _high_slot_value(
    minute: int,
    day: date,
    sunrise: int,
    sunset: int,
    solar_noon: int,
    weather: WeatherContext | None,
    config: AdaptiveFiltrationConfig,
    policy: ProfilePolicy,
) -> float:
    heat = heat_score(
        minute + _SLOT_MINUTES // 2,
        day,
        sunrise,
        sunset,
        solar_noon,
        weather,
    )
    tariff = _tariff_score(config, minute)
    return policy.high_heat_weight * heat + (1 - policy.high_heat_weight) * tariff


def _placement_score(
    profiles: tuple[HydraulicProfile, ...],
    start: int,
    day: date,
    sunrise: int,
    sunset: int,
    solar_noon: int,
    weather: WeatherContext | None,
    config: AdaptiveFiltrationConfig,
    policy: ProfilePolicy,
) -> float:
    weights = {
        HydraulicProfile.HIGH: policy.high_heat_weight,
        HydraulicProfile.MEDIUM: policy.medium_heat_weight,
        HydraulicProfile.LOW: policy.low_heat_weight,
    }
    score = 0.0
    for index, profile in enumerate(profiles):
        minute = start + index * _SLOT_MINUTES
        heat = heat_score(
            minute + _SLOT_MINUTES // 2,
            day,
            sunrise,
            sunset,
            solar_noon,
            weather,
        )
        heat_weight = weights[profile]
        tariff = _tariff_score(config, minute)
        score += heat_weight * heat + (1 - heat_weight) * tariff
    switches = sum(left is not right for left, right in zip(profiles, profiles[1:]))
    return score - switches * 0.025


def _placement_cost(
    profiles: tuple[HydraulicProfile, ...],
    start: int,
    config: AdaptiveFiltrationConfig,
) -> tuple[float, int]:
    cost = 0.0
    off_peak = 0
    for index, profile in enumerate(profiles):
        minute = start + index * _SLOT_MINUTES
        tariff = config.tariff_at(minute)
        cost += config.profile_power_w[profile] / 1000 * (_SLOT_MINUTES / 60) * tariff
        if config.is_off_peak(minute):
            off_peak += _SLOT_MINUTES
    return cost, off_peak


def _tariff_score(config: AdaptiveFiltrationConfig, minute: int) -> float:
    """Return the relative saving at this minute, from 0 to almost 1."""
    highest = max(config.off_peak_price, config.peak_price)
    if highest <= 0:
        return 0.0
    return max(0.0, (highest - config.tariff_at(minute)) / highest)


def _fallback_placement(
    start: int,
    available_slots: int,
    config: AdaptiveFiltrationConfig,
) -> _Placement:
    profiles = (HydraulicProfile.HIGH,) * available_slots
    cost, off_peak = _placement_cost(profiles, start, config)
    return _Placement(start, profiles, cost, off_peak)


def _segments_from_placement(
    placement: _Placement | None,
    target: TargetResult,
    config: AdaptiveFiltrationConfig,
) -> tuple[PlanSegment, ...]:
    if placement is None:
        return ()
    raw: list[tuple[int, int, HydraulicProfile]] = []
    for index, profile in enumerate(placement.profiles):
        start = placement.start_minute + index * _SLOT_MINUTES
        end = start + _SLOT_MINUTES
        if raw and raw[-1][2] is profile:
            previous = raw[-1]
            raw[-1] = (previous[0], end, profile)
        else:
            raw.append((start, end, profile))

    segments: list[PlanSegment] = []
    for start, end, profile_name in raw:
        profile = config.profiles[profile_name]
        if profile_name is HydraulicProfile.HIGH:
            label = ModeLabel.BOOST
            reason = (
                "water_quality_recovery"
                if target.recovery_required
                else "weather_peak_boost"
            )
        elif profile_name is HydraulicProfile.MEDIUM:
            label = ModeLabel.OPTIMIZED_FLOW
            reason = "weather_optimized_treatment"
        else:
            label = ModeLabel.ECO
            reason = "economic_daylight_filtration"
        segments.append(
            PlanSegment(
                start_minute=start,
                end_minute=end,
                profile=profile_name,
                mode_label=label,
                rpm=profile.rpm,
                flow_m3h=profile.flow_m3h,
                planned_efh=round(
                    delivered_efh(end - start, profile, config.reference_flow_m3h),
                    3,
                ),
                reason=reason,
            )
        )
    return tuple(segments)


def _slot_efh(profile: HydraulicProfile, config: AdaptiveFiltrationConfig) -> float:
    return delivered_efh(
        _SLOT_MINUTES,
        config.profiles[profile],
        config.reference_flow_m3h,
    )


def _duration_for(
    segments: tuple[PlanSegment, ...],
    profile: HydraulicProfile,
) -> int:
    return sum(
        segment.duration_minutes
        for segment in segments
        if segment.profile is profile
    )


def _round_up(minutes: int) -> int:
    return int(ceil(minutes / _SLOT_MINUTES) * _SLOT_MINUTES)


def _round_down(minutes: int) -> int:
    return int(floor(minutes / _SLOT_MINUTES) * _SLOT_MINUTES)
