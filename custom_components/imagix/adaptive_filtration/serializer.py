"""Serialize adaptive plans to the iMagi-x ``prog_user`` format."""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any

from .config import AdaptiveFiltrationConfig
from .models import DailyPlan
from .profiles import MODE_OFF


def serialize_plan(
    plan: DailyPlan,
    config: AdaptiveFiltrationConfig,
) -> list[dict[str, Any]]:
    """Return a single temperature-band program for today's plan."""
    steps_by_minute: dict[int, int] = {0: MODE_OFF}
    previous_end = 0
    for segment in plan.segments:
        if not 0 <= segment.start_minute < segment.end_minute <= 1440:
            raise ValueError("Filtration segment is outside the daily schedule")
        if segment.start_minute < previous_end:
            raise ValueError("Filtration segments overlap")

        profile = config.profiles[segment.profile]
        steps_by_minute[segment.start_minute] = profile.controller_mode
        steps_by_minute[segment.end_minute] = MODE_OFF
        previous_end = segment.end_minute

    steps = [
        {"minute": minute, "mode": mode}
        for minute, mode in sorted(steps_by_minute.items())
    ]
    return [{"temperatureMax": 99, "steps": steps}]


def program_hash(program: list[dict[str, Any]]) -> str:
    """Return a stable hash used to avoid unnecessary controller writes."""
    canonical = json.dumps(program, sort_keys=True, separators=(",", ":"))
    return sha256(canonical.encode()).hexdigest()

