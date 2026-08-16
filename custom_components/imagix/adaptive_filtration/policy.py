"""Hydraulic profile policies for adaptive filtration strategies."""
from __future__ import annotations

from dataclasses import dataclass

from .models import Strategy


@dataclass(frozen=True, slots=True)
class ProfilePolicy:
    """Target mix and slot weights for one strategy."""

    medium_share_of_flexible_efh: float
    high_heat_weight: float
    medium_heat_weight: float
    low_heat_weight: float


POLICIES = {
    Strategy.ECO: ProfilePolicy(0.40, 0.65, 0.55, 0.15),
    Strategy.BALANCED: ProfilePolicy(0.70, 0.85, 0.75, 0.30),
    Strategy.QUALITY: ProfilePolicy(0.90, 0.95, 0.90, 0.50),
}


def policy_for(strategy: Strategy) -> ProfilePolicy:
    """Return the scheduling policy for a configured strategy."""
    return POLICIES[strategy]
