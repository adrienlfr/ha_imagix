"""Home Assistant orchestration for adaptive filtration."""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import date, datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_change
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
        await self.async_recalculate(force_publish=True)

    async def async_stop(self) -> None:
        """Remove listeners and persist the final accounting state."""
        if self._unsub_coordinator is not None:
            self._unsub_coordinator()
            self._unsub_coordinator = None
        if self._unsub_daily is not None:
            self._unsub_daily()
            self._unsub_daily = None
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
            self.plan = build_daily_plan(
                inputs,
                self.target,
                config,
                solar_noon_minute=self._solar_noon_minute(now),
                delivered_today_efh=self.delivered_efh,
            )
            program = serialize_plan(self.plan, config)
            new_hash = program_hash(program)

            self.last_error = None
            if not config.enabled:
                self.status = STATUS_DISABLED
            elif self.target.confidence.value == "low":
                self.status = STATUS_SAFE_MODE
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
                        STATUS_SAFE_MODE
                        if self.target.confidence.value == "low"
                        else STATUS_PUBLISHED
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
        self._accounting_day = now.date()
        self._fingerprint = None
        self._last_accounting_at = now

    def _solar_noon_minute(self, now: datetime) -> int:
        sun_state = self.hass.states.get("sun.sun")
        if sun_state is None:
            return 13 * 60
        next_noon = dt_util.parse_datetime(sun_state.attributes.get("next_noon", ""))
        if next_noon is None:
            return 13 * 60
        local_noon = dt_util.as_local(next_noon)
        if local_noon.date() > now.date():
            local_noon -= timedelta(days=1)
        if abs((local_noon.date() - now.date()).days) > 1:
            return 13 * 60
        return local_noon.hour * 60 + local_noon.minute

    async def _async_save(self) -> None:
        required = self.plan.required_efh if self.plan is not None else 0.0
        await self._store.async_save(
            {
                "date": (self._accounting_day or dt_util.now().date()).isoformat(),
                "required_efh": round(required, 4),
                "delivered_efh": round(self.delivered_efh, 4),
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
