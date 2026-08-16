"""Unit tests for the pure adaptive filtration engine."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys
import unittest


INTEGRATION_ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "imagix"
sys.path.insert(0, str(INTEGRATION_ROOT))

from adaptive_filtration.config import AdaptiveFiltrationConfig  # noqa: E402
from adaptive_filtration.inputs import collect_inputs  # noqa: E402
from adaptive_filtration.models import (  # noqa: E402
    DataConfidence,
    FiltrationInputs,
    HydraulicProfile,
    ModeLabel,
    Strategy,
)
from adaptive_filtration.profiles import delivered_efh, resolve_label  # noqa: E402
from adaptive_filtration.scheduler import build_daily_plan  # noqa: E402
from adaptive_filtration.serializer import serialize_plan  # noqa: E402
from adaptive_filtration.target import (  # noqa: E402
    calculate_target,
    interpolate_temperature_efh,
)


def inputs(
    *,
    temperature: float | None = 24.0,
    volume: float | None = 35.0,
    orp: float | None = 700.0,
) -> FiltrationInputs:
    """Build stable test inputs."""
    return FiltrationInputs(
        now=datetime(2026, 8, 16, 8, 0),
        water_temperature=temperature,
        pool_volume_m3=volume,
        orp_mv=orp,
        ph=7.3,
        pump_running=False,
        pump_rpm=0,
        confidence=DataConfidence.HIGH,
    )


class TargetTests(unittest.TestCase):
    """Test load calculation."""

    def test_temperature_curve_points(self) -> None:
        self.assertEqual(interpolate_temperature_efh(14), 2.0)
        self.assertEqual(interpolate_temperature_efh(20), 3.5)
        self.assertEqual(interpolate_temperature_efh(24), 5.5)
        self.assertEqual(interpolate_temperature_efh(28), 7.5)
        self.assertEqual(interpolate_temperature_efh(30), 8.0)

    def test_missing_temperature_uses_safe_default(self) -> None:
        result = calculate_target(inputs(temperature=None), AdaptiveFiltrationConfig())
        self.assertEqual(result.base_efh, 5.5)
        self.assertIn("missing_temperature_safe_default", result.reasons)

    def test_low_orp_requests_recovery(self) -> None:
        result = calculate_target(inputs(orp=500), AdaptiveFiltrationConfig())
        self.assertTrue(result.recovery_required)
        self.assertGreater(result.required_efh, result.base_efh)

    def test_stale_orp_does_not_request_recovery(self) -> None:
        data = {
            "state": {
                "metrics": {
                    "waterTemperature": 24,
                    "orp": 400,
                    "orpFlow": 400,
                    "orpFlowDate": "2026-08-15T00:00:00Z",
                },
                "pool": {
                    "informations": {"volume": 35},
                    "pumps": {"pumpFx1": {"rpm": 0, "state": 0}},
                },
            }
        }
        normalized = collect_inputs(data, datetime(2026, 8, 16, 8, 0))
        self.assertIsNone(normalized.orp_mv)
        result = calculate_target(normalized, AdaptiveFiltrationConfig())
        self.assertFalse(result.recovery_required)


class ProfileTests(unittest.TestCase):
    """Test the three-profile invariant."""

    def test_medium_labels_share_one_physical_profile(self) -> None:
        config = AdaptiveFiltrationConfig()
        medium = resolve_label(ModeLabel.MEDIUM, config)
        optimized = resolve_label(ModeLabel.OPTIMIZED_FLOW, config)
        self.assertEqual(medium, optimized)
        self.assertEqual(medium.controller_mode, 3)
        self.assertEqual(medium.rpm, 2200)

    def test_efh_rates(self) -> None:
        config = AdaptiveFiltrationConfig()
        profiles = config.profiles
        self.assertAlmostEqual(
            delivered_efh(60, profiles[HydraulicProfile.LOW], 21),
            14 / 21,
        )
        self.assertEqual(
            delivered_efh(60, profiles[HydraulicProfile.MEDIUM], 21),
            1.0,
        )
        self.assertAlmostEqual(
            delivered_efh(60, profiles[HydraulicProfile.HIGH], 21),
            30 / 21,
        )


class SchedulerTests(unittest.TestCase):
    """Test planning and controller serialization."""

    def test_balanced_plan_covers_target_and_uses_medium_mode(self) -> None:
        config = AdaptiveFiltrationConfig(strategy=Strategy.BALANCED)
        target = calculate_target(inputs(), config)
        plan = build_daily_plan(inputs(), target, config)
        self.assertGreaterEqual(plan.planned_efh, plan.required_efh)
        self.assertTrue(plan.segments)
        self.assertTrue(
            all(segment.profile is HydraulicProfile.MEDIUM for segment in plan.segments)
        )
        program = serialize_plan(plan, config)
        modes = {step["mode"] for step in program[0]["steps"]}
        self.assertEqual(modes, {0, 3})

    def test_eco_plan_uses_low_and_medium(self) -> None:
        config = AdaptiveFiltrationConfig(strategy=Strategy.ECO)
        target = calculate_target(inputs(), config)
        plan = build_daily_plan(inputs(), target, config)
        self.assertGreaterEqual(plan.planned_efh, plan.required_efh)
        profiles = {segment.profile for segment in plan.segments}
        self.assertEqual(
            profiles,
            {HydraulicProfile.LOW, HydraulicProfile.MEDIUM},
        )
        modes = {
            step["mode"]
            for step in serialize_plan(plan, config)[0]["steps"]
        }
        self.assertEqual(modes, {0, 3, 4})

    def test_recovery_starts_with_high_profile(self) -> None:
        config = AdaptiveFiltrationConfig()
        target = calculate_target(inputs(orp=500), config)
        plan = build_daily_plan(inputs(orp=500), target, config)
        self.assertIs(plan.segments[0].profile, HydraulicProfile.HIGH)
        modes = {
            step["mode"]
            for step in serialize_plan(plan, config)[0]["steps"]
        }
        self.assertIn(1, modes)

    def test_midday_recalculation_only_plans_remaining_efh(self) -> None:
        config = AdaptiveFiltrationConfig(strategy=Strategy.BALANCED)
        late_inputs = FiltrationInputs(
            now=datetime(2026, 8, 16, 16, 0),
            water_temperature=24,
            pool_volume_m3=35,
            orp_mv=700,
            ph=7.3,
            pump_running=False,
            pump_rpm=0,
            confidence=DataConfidence.HIGH,
        )
        target = calculate_target(late_inputs, config)
        plan = build_daily_plan(
            late_inputs,
            target,
            config,
            delivered_today_efh=2.0,
        )
        self.assertGreaterEqual(plan.segments[0].start_minute, 16 * 60 + 5)
        self.assertGreaterEqual(plan.planned_efh, plan.required_efh)
        self.assertAlmostEqual(plan.segments[0].planned_efh, 3.5)


if __name__ == "__main__":
    unittest.main()
