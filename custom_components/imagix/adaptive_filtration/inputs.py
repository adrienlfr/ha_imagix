"""Normalize controller data for the adaptive filtration engine."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .models import DataConfidence, FiltrationInputs


def collect_inputs(data: dict[str, Any], now: datetime) -> FiltrationInputs:
    """Extract safe typed values from a ``/pool/info`` response."""
    state = data.get("state", {})
    metrics = state.get("metrics", {}) if isinstance(state, dict) else {}
    pool = state.get("pool", {}) if isinstance(state, dict) else {}
    information = pool.get("informations", {}) if isinstance(pool, dict) else {}
    pumps = pool.get("pumps", {}) if isinstance(pool, dict) else {}
    pump = pumps.get("pumpFx1", {}) if isinstance(pumps, dict) else {}

    water_temperature = _number_in_range(
        metrics.get("waterTemperature"),
        minimum=-5,
        maximum=50,
    )
    if water_temperature is None:
        water_temperature = _number_in_range(
            metrics.get("waterTemperatureFlow"),
            minimum=-5,
            maximum=50,
        )

    pool_volume = _number_in_range(
        information.get("volume"),
        minimum=1,
        maximum=1000,
    )
    rpm_value = _number_in_range(pump.get("rpm"), minimum=0, maximum=10000)
    pump_rpm = int(rpm_value) if rpm_value is not None else None
    pump_running = bool(
        (pump_rpm is not None and pump_rpm > 0)
        or pump.get("command")
        or pump.get("state")
    )
    orp = _fresh_circulation_metric(
        metrics,
        current_key="orp",
        flow_key="orpFlow",
        date_key="orpFlowDate",
        pump_running=pump_running,
        now=now,
        minimum=1,
        maximum=1500,
    )
    ph = _fresh_circulation_metric(
        metrics,
        current_key="ph",
        flow_key="phFlow",
        date_key="phFlowDate",
        pump_running=pump_running,
        now=now,
        minimum=0.1,
        maximum=14,
    )

    if water_temperature is not None and pool_volume is not None and pump_rpm is not None:
        confidence = DataConfidence.HIGH
    elif water_temperature is not None:
        confidence = DataConfidence.MEDIUM
    else:
        confidence = DataConfidence.LOW

    return FiltrationInputs(
        now=now,
        water_temperature=water_temperature,
        pool_volume_m3=pool_volume,
        orp_mv=orp,
        ph=ph,
        pump_running=pump_running,
        pump_rpm=pump_rpm,
        confidence=confidence,
    )


def calculation_fingerprint(
    inputs: FiltrationInputs,
    config: object,
) -> tuple[object, ...]:
    """Return a stable fingerprint that ignores insignificant sensor noise."""

    def bucket(value: float | None, size: float) -> float | None:
        if value is None:
            return None
        return round(value / size) * size

    return (
        inputs.now.date(),
        bucket(inputs.water_temperature, 0.5),
        bucket(inputs.pool_volume_m3, 0.5),
        bucket(inputs.orp_mv, 25),
        bucket(inputs.ph, 0.1),
        config,
    )


def _number_in_range(
    value: Any,
    *,
    minimum: float,
    maximum: float,
) -> float | None:
    """Return a finite numeric value inside the requested range."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    number = float(value)
    if number < minimum or number > maximum:
        return None
    return number


def _fresh_circulation_metric(
    metrics: dict[str, Any],
    *,
    current_key: str,
    flow_key: str,
    date_key: str,
    pump_running: bool,
    now: datetime,
    minimum: float,
    maximum: float,
) -> float | None:
    """Use water-quality data only while circulating or when recently saved."""
    if pump_running:
        return _number_in_range(
            metrics.get(current_key),
            minimum=minimum,
            maximum=maximum,
        )

    measured_at = _parse_timestamp(metrics.get(date_key))
    if measured_at is None:
        return None
    comparable_now = now
    if comparable_now.tzinfo is None:
        comparable_now = comparable_now.replace(tzinfo=timezone.utc)
    age = comparable_now.astimezone(timezone.utc) - measured_at
    if age.total_seconds() < 0 or age.total_seconds() > 6 * 3600:
        return None
    return _number_in_range(
        metrics.get(flow_key),
        minimum=minimum,
        maximum=maximum,
    )


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or value.startswith("1970-01-01"):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
