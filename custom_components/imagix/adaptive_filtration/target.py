"""Daily EFH target calculation."""
from __future__ import annotations

from .config import AdaptiveFiltrationConfig
from .models import FiltrationInputs, TargetResult

TEMPERATURE_CURVE = (
    (14.0, 2.0),
    (20.0, 3.5),
    (24.0, 5.5),
    (28.0, 7.5),
)


def interpolate_temperature_efh(temperature: float) -> float:
    """Interpolate the specification's temperature curve."""
    if temperature <= TEMPERATURE_CURVE[0][0]:
        return TEMPERATURE_CURVE[0][1]

    for (left_temp, left_efh), (right_temp, right_efh) in zip(
        TEMPERATURE_CURVE,
        TEMPERATURE_CURVE[1:],
    ):
        if temperature <= right_temp:
            position = (temperature - left_temp) / (right_temp - left_temp)
            return left_efh + position * (right_efh - left_efh)

    # 0.5 EFH per 2 °C above 28 °C.
    return TEMPERATURE_CURVE[-1][1] + (temperature - 28.0) * 0.25


def calculate_target(
    inputs: FiltrationInputs,
    config: AdaptiveFiltrationConfig,
    filtration_debt_efh: float = 0.0,
) -> TargetResult:
    """Calculate today's bounded EFH requirement."""
    reasons: list[str] = []
    if inputs.water_temperature is None:
        temperature = 24.0
        reasons.append("missing_temperature_safe_default")
    else:
        temperature = inputs.water_temperature

    base_efh = interpolate_temperature_efh(temperature)
    volume = inputs.pool_volume_m3 or config.reference_volume_m3
    volume_factor = _clamp(
        volume / config.reference_volume_m3,
        0.85,
        1.20,
    )

    quality_factor = 1.0
    recovery_required = False
    if inputs.orp_mv is not None:
        if inputs.orp_mv < 550:
            quality_factor = 1.25
            recovery_required = True
            reasons.append("orp_recovery")
        elif inputs.orp_mv < 650:
            quality_factor = 1.10
            reasons.append("orp_vigilance")

    if inputs.ph is not None and not 7.0 <= inputs.ph <= 7.6:
        quality_factor = max(quality_factor, 1.05)
        reasons.append("ph_out_of_range")

    debt = _clamp(filtration_debt_efh, 0.0, config.debt_carry_limit_efh)
    required = base_efh * volume_factor * quality_factor + debt
    required = _clamp(required, config.min_efh, config.max_efh)

    return TargetResult(
        base_efh=round(base_efh, 3),
        required_efh=round(required, 3),
        volume_factor=round(volume_factor, 3),
        water_quality_factor=round(quality_factor, 3),
        confidence=inputs.confidence,
        recovery_required=recovery_required,
        reasons=tuple(reasons),
    )


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return min(maximum, max(minimum, value))

