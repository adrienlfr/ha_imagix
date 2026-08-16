"""Home Assistant orchestration for adaptive filtration."""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import date, datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_change,
)
from homeassistant.util import dt as dt_util

from ..api import ImagixConnectionError
from ..coordinator import ImagixDataUpdateCoordinator
from .config import AdaptiveFiltrationConfig, load_config
from .inputs import calculation_fingerprint, collect_inputs
from .models import DailyPlan, HydraulicProfile, TargetResult
from .profiles import delivered_efh
from .scheduler import build_daily_plan
from .serializer import program_hash, serialize_plan
from .storage import AdaptiveFiltrationStore
from .target import calculate_target

_LOGGER = logging.getLogger(__name__)

STATUS_INITIALIZING = "initializing"
STATUS_DISABLED = "disabled"
STATUS_READY = "ready"
STATUS_PUBLISHED = "published"
STATUS_SAFE_MODE = "safe_mode"
STATUS_DAYLIGHT_LIMITED = "daylight_limited"
STATUS_SUN_UNAVAILABLE = "sun_unavailable"
STATUS_ERROR = "error"

MAX_ACCOUNTING_GAP_SECONDS = 60


class AdaptiveFiltrationManager:
    """Calculate, publish and account for the adaptive expert program."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        coordinator: ImagixDataUpdateCoordinator,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.coordinator = coordinator
        self._store = AdaptiveFiltrationStore(hass, entry.entry_id)
        self._lock = asyncio.Lock()
        self._listeners: set[Callable[[], None]] = set()
        self._unsub_coordinator: CALLBACK_TYPE | None = None
        self._unsub_daily: CALLBACK_TYPE | None = None
        self._unsub_sun: CALLBACK_TYPE | None = None
        self._fingerprint: tuple[object, ...] | None = None
        self._last_accounting_at: datetime | None = None
        self._last_saved_at: datetime | None = None
        self._accounting_day: date | None = None
        self._last_program_hash: str | None = None

        self.status = STATUS_INITIALIZING
        self.last_error: str | None = None
        self.target: TargetResult | None = None
        self.plan: DailyPlan | None = None
        self.delivered_efh = 0.0
        self.delivered_high_minutes = 0.0
        self.debt_efh = 0.0
        self.current_profile: HydraulicProfile | None = None
        self.last_published_at: datetime | None = None

    @property
    def config(self) -> AdaptiveFiltrationConfig:
        """Return current config entry options as validated settings."""
        return load_config(self.entry.options)

    async def async_start(self) -> None:
        """Load state, register listeners and publish the initial plan."""
        stored = await self._store.async_load()
        now = dt_util.now()
        stored_day = _parse_date(stored.get("date"))
        self.debt_efh = _as_float(stored.get("debt_efh"), 0.0)
        if stored_day == now.date():
            self.delivered_efh = _as_float(stored.get("delivered_efh"), 0.0)
            self.delivered_high_minutes = _as_float(
                stored.get("delivered_high_minutes"), 0.0
            )
        elif stored_day is not None:
            required = _as_float(stored.get("required_efh"), 0.0)
            delivered = _as_float(stored.get("delivered_efh"), 0.0)
            self.debt_efh = min(
                self.config.debt_carry_limit_efh,
                max(self.debt_efh, required - delivered, 0.0),
            )
        self._last_program_hash = stored.get("program_hash")
        self._accounting_day = now.date()
        self._last_accounting_at = now

        self._unsub_coordinator = self.coordinator.async_add_listener(
            self._handle_coordinator_update
        )
        self._unsub_daily = async_track_time_change(
            self.hass,
            self._handle_new_day,
            hour=0,
            minute=5,
            second=0,
        )
        self._unsub_sun = async_track_state_change_event(
            self.hass,
            ["sun.sun"],
            self._handle_sun_update,
        )
        await self.async_recalculate(force_publish=True)

    async def async_stop(self) -> None:
        """Remove listeners and persist the final accounting state."""
        if self._unsub_coordinator is not None:
            self._unsub_coordinator()
            self._unsub_coordinator = None
        if self._unsub_daily is not None:
            self._unsub_daily()
            self._unsub_daily = None
        if self._unsub_sun is not None:
            self._unsub_sun()
            self._unsub_sun = None
        await self._async_save()

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> CALLBACK_TYPE:
        """Subscribe an entity to manager state changes."""
        self._listeners.add(listener)

        @callback
        def remove_listener() -> None:
            self._listeners.discard(listener)

        return remove_listener

    @callback
    def _notify_listeners(self) -> None:
        for listener in tuple(self._listeners):
            listener()

    @callback
    def _handle_coordinator_update(self) -> None:
        self.hass.async_create_task(self._async_process_coordinator_update())

    @callback
    def _handle_new_day(self, _now: datetime) -> None:
        self.hass.async_create_task(self.async_recalculate(force_publish=True))

    @callback
    def _handle_sun_update(self, _event: Any) -> None:
        """Retry a safe empty plan as soon as valid sun data becomes available."""
        if self.plan is None or self.plan.sunrise_minute >= self.plan.sunset_minute:
            self.hass.async_create_task(self.async_recalculate(force_publish=True))

    async def _async_process_coordinator_update(self) -> None:
        async with self._lock:
            now = dt_util.now()
            self._update_accounting(now)
            inputs = collect_inputs(self.coordinator.data, now)
            fingerprint = calculation_fingerprint(inputs, self.config)
            if fingerprint == self._fingerprint:
                if (
                    self._last_saved_at is None
                    or (now - self._last_saved_at).total_seconds() >= 60
                ):
                    await self._async_save()
                self._notify_listeners()
                return
        await self.async_recalculate()

    async def async_recalculate(self, force_publish: bool = False) -> None:
        """Recalculate and optionally republish today's expert program."""
        async with self._lock:
            now = dt_util.now()
            self._roll_accounting_day(now)
            config = self.config
            inputs = collect_inputs(self.coordinator.data, now)
            self._fingerprint = calculation_fingerprint(inputs, config)
            self.target = calculate_target(inputs, config, self.debt_efh)
            sunrise_minute, solar_noon_minute, sunset_minute = self._sun_window(now)
            sun_available = sunrise_minute < sunset_minute
            self.plan = build_daily_plan(
                inputs,
                self.target,
                config,
                solar_noon_minute=solar_noon_minute,
                sunrise_minute=sunrise_minute,
                sunset_minute=sunset_minute,
                delivered_today_efh=self.delivered_efh,
                delivered_high_minutes=self.delivered_high_minutes,
            )
            program = serialize_plan(self.plan, config)
            new_hash = program_hash(program)

            self.last_error = None if sun_available else "sun_data_unavailable"
            if not config.enabled:
                self.status = STATUS_DISABLED
            elif not sun_available:
                self.status = STATUS_SUN_UNAVAILABLE
            elif self.target.confidence.value == "low":
                self.status = STATUS_SAFE_MODE
            elif self.plan.daylight_limited:
                self.status = STATUS_DAYLIGHT_LIMITED
            else:
                self.status = STATUS_READY

            if config.enabled and (
                force_publish or new_hash != self._last_program_hash
            ):
                try:
                    await self.coordinator.client.async_set_custom_filtration_program(
                        program
                    )
                except ImagixConnectionError as err:
                    self.status = STATUS_ERROR
                    self.last_error = str(err)
                    _LOGGER.warning("Unable to publish adaptive filtration plan: %s", err)
                else:
                    self._last_program_hash = new_hash
                    self.last_published_at = now
                    self.status = (
                        STATUS_SUN_UNAVAILABLE
                        if not sun_available
                        else (
                            STATUS_SAFE_MODE
                            if self.target.confidence.value == "low"
                            else (
                                STATUS_DAYLIGHT_LIMITED
                                if self.plan.daylight_limited
                                else STATUS_PUBLISHED
                            )
                        )
                    )
                    _LOGGER.info(
                        "Published adaptive filtration plan: %.3f EFH in %s segments",
                        self.plan.planned_efh,
                        len(self.plan.segments),
                    )

            await self._async_save()
            self._notify_listeners()

    def _update_accounting(self, now: datetime) -> None:
        self._roll_accounting_day(now)
        previous = self._last_accounting_at
        self._last_accounting_at = now
        if previous is None:
            return
        elapsed = (now - previous).total_seconds()
        if elapsed <= 0 or elapsed > MAX_ACCOUNTING_GAP_SECONDS:
            self.current_profile = None
            return

        inputs = collect_inputs(self.coordinator.data, now)
        self.current_profile = self._confirmed_profile(inputs.pump_running, inputs.pump_rpm)
        if self.current_profile is None:
            return

        profile = self.config.profiles[self.current_profile]
        self.delivered_efh += delivered_efh(
            elapsed / 60.0,
            profile,
            self.config.reference_flow_m3h,
        )
        if self.current_profile is HydraulicProfile.HIGH:
            self.delivered_high_minutes += elapsed / 60.0

    def _confirmed_profile(
        self,
        pump_running: bool,
        pump_rpm: int | None,
    ) -> HydraulicProfile | None:
        if not pump_running or pump_rpm is None or pump_rpm <= 0:
            return None
        candidates = self.config.profiles
        profile = min(candidates, key=lambda item: abs(candidates[item].rpm - pump_rpm))
        expected_rpm = candidates[profile].rpm
        tolerance = max(100, round(expected_rpm * 0.05))
        return profile if abs(expected_rpm - pump_rpm) <= tolerance else None

    def _roll_accounting_day(self, now: datetime) -> None:
        if self._accounting_day is None:
            self._accounting_day = now.date()
        if self._accounting_day == now.date():
            return

        if self.plan is not None:
            missing = max(0.0, self.plan.required_efh - self.delivered_efh)
            self.debt_efh = min(self.config.debt_carry_limit_efh, missing)
        self.delivered_efh = 0.0
        self.delivered_high_minutes = 0.0
        self._accounting_day = now.date()
        self._fingerprint = None
        self._last_accounting_at = now

    def _sun_window(self, now: datetime) -> tuple[int, int, int]:
        """Return today's local sunrise, solar noon and sunset minutes."""
        sun_state = self.hass.states.get("sun.sun")
        if sun_state is None:
            return 0, 0, 0

        def event_minute(attribute: str) -> int | None:
            event = dt_util.parse_datetime(sun_state.attributes.get(attribute, ""))
            if event is None:
                return None
            local_event = dt_util.as_local(event)
            if local_event.date() > now.date():
                local_event -= timedelta(days=1)
            if abs((local_event.date() - now.date()).days) > 1:
                return None
            return local_event.hour * 60 + local_event.minute

        sunrise = event_minute("next_rising")
        sunset = event_minute("next_setting")
        if sunrise is None or sunset is None or sunrise >= sunset:
            return 0, 0, 0
        noon = event_minute("next_noon") or (sunrise + sunset) // 2
        return sunrise, noon, sunset

    async def _async_save(self) -> None:
        required = self.plan.required_efh if self.plan is not None else 0.0
        await self._store.async_save(
            {
                "date": (self._accounting_day or dt_util.now().date()).isoformat(),
                "required_efh": round(required, 4),
                "delivered_efh": round(self.delivered_efh, 4),
                "delivered_high_minutes": round(self.delivered_high_minutes, 2),
                "debt_efh": round(self.debt_efh, 4),
                "program_hash": self._last_program_hash,
            }
        )
        self._last_saved_at = dt_util.now()

    @property
    def plan_attributes(self) -> dict[str, Any]:
        """Return diagnostics suitable for an entity's attributes."""
        attributes: dict[str, Any] = {
            "status": self.status,
            "last_error": self.last_error,
            "last_published_at": (
                self.last_published_at.isoformat()
                if self.last_published_at is not None
                else None
            ),
            "delivered_efh": round(self.delivered_efh, 3),
            "delivered_high_minutes": round(self.delivered_high_minutes, 1),
        }
        if self.target is not None:
            attributes["target"] = {
                "base_efh": self.target.base_efh,
                "volume_factor": self.target.volume_factor,
                "water_quality_factor": self.target.water_quality_factor,
                "reasons": list(self.target.reasons),
            }
        if self.plan is not None:
            attributes.update(self.plan.as_dict())
        return attributes


def _parse_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
