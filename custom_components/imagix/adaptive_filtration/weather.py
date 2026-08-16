"""Home Assistant weather forecast adapter with safe normalization."""
from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any

from .models import WeatherContext, WeatherPoint

_LOGGER = logging.getLogger(__name__)


class WeatherProvider:
    """Fetch and cache hourly forecasts from a Home Assistant weather entity."""

    def __init__(self, hass: Any) -> None:
        self.hass = hass
        self._context = WeatherContext()
        self._loaded_at: datetime | None = None

    async def async_get(
        self,
        configured_entity_id: str | None,
        now: datetime,
        *,
        force: bool = False,
    ) -> WeatherContext:
        """Return a forecast no older than thirty minutes when possible."""
        entity_id = configured_entity_id or self._first_weather_entity()
        if entity_id is None:
            return WeatherContext()
        if (
            not force
            and self._loaded_at is not None
            and now - self._loaded_at < timedelta(minutes=30)
            and self._context.entity_id == entity_id
        ):
            return self._context

        state = self.hass.states.get(entity_id)
        current_condition = state.state if state is not None else None
        try:
            response = await self.hass.services.async_call(
                "weather",
                "get_forecasts",
                {"entity_id": entity_id, "type": "hourly"},
                blocking=True,
                return_response=True,
            )
        except Exception as err:  # Home Assistant/provider availability varies.
            _LOGGER.debug("Unable to retrieve hourly weather forecast: %s", err)
            self._context = WeatherContext(
                entity_id=entity_id,
                current_condition=current_condition,
                available=False,
            )
        else:
            payload = response.get(entity_id, {}) if isinstance(response, dict) else {}
            raw_points = payload.get("forecast", []) if isinstance(payload, dict) else []
            points = normalize_forecast(raw_points, now, state.attributes if state else {})
            self._context = WeatherContext(
                entity_id=entity_id,
                current_condition=current_condition,
                points=points,
                available=bool(points),
            )
        self._loaded_at = now
        return self._context

    def _first_weather_entity(self) -> str | None:
        for state in self.hass.states.async_all():
            if state.entity_id.startswith("weather."):
                return state.entity_id
        return None


def normalize_forecast(
    raw_points: Any,
    now: datetime,
    state_attributes: dict[str, Any],
) -> tuple[WeatherPoint, ...]:
    """Normalize provider-dependent forecast dictionaries."""
    if not isinstance(raw_points, list):
        return ()
    temperature_unit = str(state_attributes.get("temperature_unit", "°C"))
    wind_unit = str(state_attributes.get("wind_speed_unit", "km/h"))
    points: list[WeatherPoint] = []
    for raw in raw_points:
        if not isinstance(raw, dict):
            continue
        try:
            at = datetime.fromisoformat(str(raw["datetime"]).replace("Z", "+00:00"))
        except (KeyError, TypeError, ValueError):
            continue
        if now.tzinfo is not None:
            at = at.astimezone(now.tzinfo)
        points.append(
            WeatherPoint(
                at=at,
                temperature_c=_temperature_c(raw.get("temperature"), temperature_unit),
                cloud_coverage=_number(raw.get("cloud_coverage")),
                uv_index=_number(raw.get("uv_index")),
                precipitation_mm=_number(raw.get("precipitation")),
                precipitation_probability=_number(raw.get("precipitation_probability")),
                wind_speed_kmh=_wind_kmh(raw.get("wind_speed"), wind_unit),
                condition=str(raw.get("condition")) if raw.get("condition") else None,
            )
        )
    return tuple(points)


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _temperature_c(value: Any, unit: str) -> float | None:
    number = _number(value)
    if number is None:
        return None
    return (number - 32) * 5 / 9 if "F" in unit else number


def _wind_kmh(value: Any, unit: str) -> float | None:
    number = _number(value)
    if number is None:
        return None
    if unit in {"m/s", "mps"}:
        return number * 3.6
    if unit in {"mph", "mi/h"}:
        return number * 1.609344
    if unit in {"kn", "kt", "kts"}:
        return number * 1.852
    return number
