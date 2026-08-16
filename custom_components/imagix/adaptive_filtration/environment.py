"""Pure weather and solar scoring for adaptive filtration."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from math import sin, pi

from .models import WeatherContext, WeatherPoint

_STORM_CONDITIONS = {"lightning", "lightning-rainy", "pouring", "hail"}
_WET_CONDITIONS = _STORM_CONDITIONS | {"rainy", "snowy-rainy"}


@dataclass(frozen=True, slots=True)
class EnvironmentResult:
    """Bounded weather correction applied to the daily EFH target."""

    factor: float = 1.0
    bonus_efh: float = 0.0
    reasons: tuple[str, ...] = ()


def environment_adjustment(
    weather: WeatherContext | None,
    day: date,
) -> EnvironmentResult:
    """Return conservative heat, UV, wind and storm corrections."""
    if weather is None or not weather.available:
        return EnvironmentResult(reasons=("weather_unavailable",))
    points = points_for_day(weather, day)
    if not points:
        return EnvironmentResult(reasons=("weather_forecast_missing",))

    reasons: list[str] = []
    factor = 1.0
    temperatures = [p.temperature_c for p in points if p.temperature_c is not None]
    if temperatures:
        maximum = max(temperatures)
        if maximum > 28:
            factor += min(0.12, (maximum - 28) * 0.015)
            reasons.append("forecast_heat")

    uv_values = [p.uv_index for p in points if p.uv_index is not None]
    if uv_values and max(uv_values) > 5:
        factor += min(0.06, (max(uv_values) - 5) * 0.015)
        reasons.append("forecast_uv")

    winds = [p.wind_speed_kmh for p in points if p.wind_speed_kmh is not None]
    if winds and max(winds) >= 30:
        factor += 0.03
        reasons.append("forecast_wind")

    conditions = {p.condition for p in points if p.condition}
    bonus = 0.0
    if weather.current_condition in _STORM_CONDITIONS:
        bonus = 0.6
        reasons.append("observed_storm")
    elif weather.current_condition in _WET_CONDITIONS:
        bonus = 0.3
        reasons.append("observed_rain")
    elif conditions & _STORM_CONDITIONS:
        bonus = 0.2
        reasons.append("forecast_storm_reserve")
    else:
        precipitation = [
            point.precipitation_mm
            for point in points
            if point.precipitation_mm is not None
        ]
        probabilities = [
            point.precipitation_probability
            for point in points
            if point.precipitation_probability is not None
        ]
        forecast_rain = bool(conditions & _WET_CONDITIONS)
        forecast_rain |= bool(precipitation and max(precipitation) >= 2)
        forecast_rain |= bool(probabilities and max(probabilities) >= 60)
        if forecast_rain:
            bonus = 0.1
            reasons.append("forecast_rain_reserve")

    return EnvironmentResult(
        factor=round(min(1.20, factor), 3),
        bonus_efh=bonus,
        reasons=tuple(reasons),
    )


def points_for_day(weather: WeatherContext | None, day: date) -> tuple[WeatherPoint, ...]:
    """Return forecast points belonging to the requested local day."""
    if weather is None:
        return ()
    return tuple(point for point in weather.points if point.at.date() == day)


def peak_weather_minute(
    weather: WeatherContext | None,
    day: date,
    solar_noon_minute: int,
) -> int:
    """Return the warmest forecast hour, falling back to solar noon."""
    points = [
        point
        for point in points_for_day(weather, day)
        if point.temperature_c is not None
    ]
    if not points:
        return solar_noon_minute
    point = max(points, key=lambda item: item.temperature_c or -100.0)
    return point.at.hour * 60 + point.at.minute


def heat_score(
    minute: int,
    day: date,
    sunrise_minute: int,
    sunset_minute: int,
    solar_noon_minute: int,
    weather: WeatherContext | None,
) -> float:
    """Return a 0..1 combined forecast-temperature and solar score."""
    if sunset_minute <= sunrise_minute:
        return 0.0
    position = (minute - sunrise_minute) / (sunset_minute - sunrise_minute)
    solar = max(0.0, sin(pi * max(0.0, min(1.0, position))))
    points = points_for_day(weather, day)
    temperatures = [p.temperature_c for p in points if p.temperature_c is not None]
    if not temperatures:
        return round(solar, 4)
    nearest = min(
        points,
        key=lambda point: abs((point.at.hour * 60 + point.at.minute) - minute),
    )
    if nearest.temperature_c is None:
        return round(solar, 4)
    low = min(temperatures)
    high = max(temperatures)
    temperature_score = 1.0 if high <= low else (nearest.temperature_c - low) / (high - low)
    cloud = nearest.cloud_coverage
    solar_weather = solar if cloud is None else solar * (1.0 - 0.35 * cloud / 100)
    uv_score = min(1.0, (nearest.uv_index or 0.0) / 8.0)
    return round(min(1.0, 0.55 * temperature_score + 0.30 * solar_weather + 0.15 * uv_score), 4)
