"""Unit tests for the pure adaptive filtration engine."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys
import unittest


INTEGRATION_ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "imagix"
sys.path.insert(0, str(INTEGRATION_ROOT))

from adaptive_filtration.config import (  # noqa: E402
    AdaptiveFiltrationConfig,
    load_config,
)
from adaptive_filtration.inputs import collect_inputs  # noqa: E402
from adaptive_filtration.models import (  # noqa: E402
    DataConfidence,
    FiltrationInputs,
    HydraulicProfile,
    ModeLabel,
    Strategy,
    WeatherContext,
    WeatherPoint,
)
from adaptive_filtration.profiles import delivered_efh, resolve_label  # noqa: E402
from adaptive_filtration.scheduler import build_daily_plan  # noqa: E402
from adaptive_filtration.serializer import serialize_plan  # noqa: E402
from adaptive_filtration.target import (  # noqa: E402
    calculate_target,
    interpolate_temperature_efh,
)
from adaptive_filtration.weather import normalize_forecast  # noqa: E402


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


def hot_afternoon_weather() -> WeatherContext:
    """Build an hourly forecast whose warmest period is late afternoon."""
    return WeatherContext(
        entity_id="weather.home",
        current_condition="sunny",
        available=True,
        points=tuple(
            WeatherPoint(
                at=datetime(2026, 8, 16, hour),
                temperature_c=temperature,
                cloud_coverage=10,
                uv_index=max(0, 8 - abs(14 - hour)),
                condition="sunny",
            )
            for hour, temperature in (
                (8, 19),
                (10, 22),
                (12, 26),
                (14, 29),
                (16, 33),
                (18, 30),
                (20, 25),
            )
        ),
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

    def test_hot_weather_increases_target(self) -> None:
        config = AdaptiveFiltrationConfig()
        baseline = calculate_target(inputs(), config)
        hot = calculate_target(inputs(), config, weather=hot_afternoon_weather())
        self.assertGreater(hot.environment_factor, 1.0)
        self.assertGreater(hot.required_efh, baseline.required_efh)
        self.assertIn("forecast_heat", hot.reasons)

    def test_observed_storm_adds_a_filtration_reserve(self) -> None:
        config = AdaptiveFiltrationConfig()
        weather = hot_afternoon_weather()
        storm = WeatherContext(
            entity_id=weather.entity_id,
            current_condition="lightning-rainy",
            points=weather.points,
            available=True,
        )
        target = calculate_target(inputs(), config, weather=storm)
        self.assertEqual(target.weather_bonus_efh, 0.6)
        self.assertIn("observed_storm", target.reasons)


class ProfileTests(unittest.TestCase):
    """Test the three-profile invariant."""

    def test_medium_labels_share_one_physical_profile(self) -> None:
        config = AdaptiveFiltrationConfig()
        medium = resolve_label(ModeLabel.MEDIUM, config)
        optimized = resolve_label(ModeLabel.OPTIMIZED_FLOW, config)
        self.assertEqual(medium, optimized)
        self.assertEqual(medium.controller_mode, 7)
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


class WeatherTests(unittest.TestCase):
    """Test Home Assistant weather forecast normalization."""

    def test_forecast_units_are_normalized(self) -> None:
        points = normalize_forecast(
            [
                {
                    "datetime": "2026-08-16T16:00:00+02:00",
                    "temperature": 86,
                    "wind_speed": 10,
                    "condition": "sunny",
                }
            ],
            datetime(2026, 8, 16, 8),
            {"temperature_unit": "°F", "wind_speed_unit": "mph"},
        )
        self.assertEqual(len(points), 1)
        self.assertAlmostEqual(points[0].temperature_c or 0, 30)
        self.assertAlmostEqual(points[0].wind_speed_kmh or 0, 16.09344)


class SchedulerTests(unittest.TestCase):
    """Test planning and controller serialization."""

    def test_plan_covers_target_inside_daylight_with_daily_high(self) -> None:
        config = AdaptiveFiltrationConfig(strategy=Strategy.BALANCED)
        target = calculate_target(inputs(), config)
        plan = build_daily_plan(
            inputs(), target, config, sunrise_minute=7 * 60, sunset_minute=21 * 60
        )
        self.assertGreaterEqual(plan.planned_efh, plan.required_efh)
        self.assertTrue(plan.segments)
        self.assertTrue(all(segment.start_minute >= 7 * 60 for segment in plan.segments))
        self.assertTrue(all(segment.end_minute <= 21 * 60 for segment in plan.segments))
        self.assertGreaterEqual(
            sum(
                segment.duration_minutes
                for segment in plan.segments
                if segment.profile is HydraulicProfile.HIGH
            ),
            60,
        )
        program = serialize_plan(plan, config)
        modes = {step["mode"] for step in program[0]["steps"]}
        self.assertIn(1, modes)
        self.assertIn(7, modes)
        self.assertIn(0, modes)

    def test_cost_optimized_plan_uses_multiple_profiles(self) -> None:
        config = AdaptiveFiltrationConfig(strategy=Strategy.ECO)
        target = calculate_target(inputs(), config)
        plan = build_daily_plan(inputs(), target, config)
        self.assertGreaterEqual(plan.planned_efh, plan.required_efh)
        profiles = {segment.profile for segment in plan.segments}
        self.assertIn(HydraulicProfile.HIGH, profiles)
        self.assertGreaterEqual(len(profiles), 2)
        modes = {
            step["mode"]
            for step in serialize_plan(plan, config)[0]["steps"]
        }
        self.assertIn(1, modes)
        self.assertTrue({7, 4} & modes)

    def test_daily_boost_is_split_into_four_weather_placed_quarters(self) -> None:
        config = AdaptiveFiltrationConfig(strategy=Strategy.BALANCED)
        weather = hot_afternoon_weather()
        target = calculate_target(inputs(), config, weather=weather)
        plan = build_daily_plan(
            inputs(),
            target,
            config,
            sunrise_minute=7 * 60,
            sunset_minute=21 * 60,
            weather=weather,
        )
        high = [
            segment
            for segment in plan.segments
            if segment.profile is HydraulicProfile.HIGH
        ]
        self.assertEqual(len(high), 4)
        self.assertTrue(all(segment.duration_minutes == 15 for segment in high))
        self.assertNotEqual(plan.segments[0].profile, HydraulicProfile.HIGH)
        self.assertTrue(
            all(
                left.end_minute < right.start_minute
                for left, right in zip(high, high[1:])
            )
        )
        steps = serialize_plan(plan, config)[0]["steps"]
        off_minutes = [step["minute"] for step in steps if step["mode"] == 0]
        self.assertEqual(off_minutes, [0, plan.segments[-1].end_minute])

    def test_balanced_strategy_uses_medium_for_most_flexible_efh(self) -> None:
        config = AdaptiveFiltrationConfig(strategy=Strategy.BALANCED)
        target = calculate_target(inputs(), config)
        plan = build_daily_plan(inputs(), target, config)
        flexible = [
            segment
            for segment in plan.segments
            if segment.profile is not HydraulicProfile.HIGH
        ]
        medium_efh = sum(
            segment.planned_efh
            for segment in flexible
            if segment.profile is HydraulicProfile.MEDIUM
        )
        low_efh = sum(
            segment.planned_efh
            for segment in flexible
            if segment.profile is HydraulicProfile.LOW
        )
        self.assertGreater(medium_efh, low_efh)

    def test_weather_peak_moves_schedule_toward_hot_afternoon(self) -> None:
        config = AdaptiveFiltrationConfig(strategy=Strategy.BALANCED)
        weather = hot_afternoon_weather()
        target = calculate_target(inputs(), config, weather=weather)
        plan = build_daily_plan(
            inputs(),
            target,
            config,
            sunrise_minute=7 * 60,
            sunset_minute=21 * 60,
            solar_noon_minute=13 * 60,
            weather=weather,
        )
        self.assertEqual(plan.peak_weather_minute, 16 * 60)
        high_midpoints = [
            (segment.start_minute + segment.end_minute) / 2
            for segment in plan.segments
            if segment.profile is HydraulicProfile.HIGH
        ]
        self.assertGreater(sum(high_midpoints) / len(high_midpoints), 13 * 60)

    def test_recovery_contains_high_profile(self) -> None:
        config = AdaptiveFiltrationConfig()
        target = calculate_target(inputs(orp=500), config)
        plan = build_daily_plan(inputs(orp=500), target, config)
        high_segments = [
            segment
            for segment in plan.segments
            if segment.profile is HydraulicProfile.HIGH
        ]
        self.assertTrue(high_segments)
        self.assertIn("water_quality_recovery", high_segments[0].reason)
        modes = {
            step["mode"]
            for step in serialize_plan(plan, config)[0]["steps"]
        }
        self.assertIn(1, modes)

    def test_midday_recalculation_preserves_the_complete_daily_plan(self) -> None:
        config = AdaptiveFiltrationConfig(strategy=Strategy.BALANCED)
        weather = hot_afternoon_weather()
        morning_inputs = inputs()
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
        morning_target = calculate_target(morning_inputs, config, weather=weather)
        late_target = calculate_target(late_inputs, config, weather=weather)
        morning_plan = build_daily_plan(
            morning_inputs,
            morning_target,
            config,
            weather=weather,
        )
        late_plan = build_daily_plan(
            late_inputs,
            late_target,
            config,
            weather=weather,
        )
        self.assertEqual(
            serialize_plan(late_plan, config),
            serialize_plan(morning_plan, config),
        )
        self.assertEqual(
            late_plan.segments[0].start_minute,
            morning_plan.segments[0].start_minute,
        )

    def test_after_sunset_recalculation_prepares_tomorrow(self) -> None:
        config = AdaptiveFiltrationConfig()
        night_inputs = FiltrationInputs(
            now=datetime(2026, 8, 16, 22, 30),
            water_temperature=24,
            pool_volume_m3=35,
            orp_mv=700,
            ph=7.3,
            pump_running=False,
            pump_rpm=0,
            confidence=DataConfidence.HIGH,
        )
        target = calculate_target(night_inputs, config)
        plan = build_daily_plan(
            night_inputs,
            target,
            config,
            sunrise_minute=7 * 60,
            sunset_minute=21 * 60,
        )
        self.assertEqual(plan.day.isoformat(), "2026-08-17")
        self.assertTrue(plan.segments)
        self.assertGreaterEqual(plan.planned_efh, plan.required_efh)
        self.assertGreaterEqual(plan.high_minutes, 60)
        self.assertTrue(all(item.start_minute >= 7 * 60 for item in plan.segments))
        self.assertTrue(all(item.end_minute <= 21 * 60 for item in plan.segments))
        modes = {step["mode"] for step in serialize_plan(plan, config)[0]["steps"]}
        self.assertIn(1, modes)

    def test_night_off_peak_window_is_ignored(self) -> None:
        config = AdaptiveFiltrationConfig(
            off_peak_start_minute=22 * 60,
            off_peak_end_minute=6 * 60,
        )
        target = calculate_target(inputs(), config)
        plan = build_daily_plan(
            inputs(), target, config, sunrise_minute=8 * 60, sunset_minute=20 * 60
        )
        self.assertEqual(plan.off_peak_minutes, 0)
        self.assertTrue(all(8 * 60 <= item.start_minute for item in plan.segments))
        self.assertTrue(all(item.end_minute <= 20 * 60 for item in plan.segments))

    def test_full_day_recalculation_retains_daily_high(self) -> None:
        config = AdaptiveFiltrationConfig()
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
        plan = build_daily_plan(late_inputs, target, config)
        self.assertGreaterEqual(
            sum(
                item.duration_minutes
                for item in plan.segments
                if item.profile is HydraulicProfile.HIGH
            ),
            60,
        )
        self.assertGreaterEqual(plan.planned_efh, plan.required_efh)

    def test_afternoon_recalculation_keeps_past_segments_in_program(self) -> None:
        config = AdaptiveFiltrationConfig()
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
        plan = build_daily_plan(late_inputs, target, config)
        self.assertLess(plan.segments[0].start_minute, 16 * 60)
        self.assertFalse(plan.daylight_limited)

    def test_daytime_off_peak_window_is_used(self) -> None:
        config = AdaptiveFiltrationConfig(
            off_peak_start_minute=10 * 60,
            off_peak_end_minute=14 * 60,
            off_peak_price=0.05,
            peak_price=0.50,
        )
        target = calculate_target(inputs(), config)
        plan = build_daily_plan(
            inputs(), target, config, sunrise_minute=8 * 60, sunset_minute=20 * 60
        )
        self.assertGreater(plan.off_peak_minutes, 0)
        high = next(
            item for item in plan.segments if item.profile is HydraulicProfile.HIGH
        )
        self.assertGreaterEqual(high.start_minute, 10 * 60)
        self.assertLessEqual(high.end_minute, 14 * 60)

    def test_impossible_target_never_escapes_daylight(self) -> None:
        config = AdaptiveFiltrationConfig(max_efh=12.0)
        hot_inputs = inputs(temperature=40)
        target = calculate_target(hot_inputs, config, filtration_debt_efh=3.0)
        plan = build_daily_plan(
            hot_inputs,
            target,
            config,
            sunrise_minute=10 * 60,
            sunset_minute=12 * 60,
        )
        self.assertTrue(plan.daylight_limited)
        self.assertGreater(plan.unmet_efh, 0)
        self.assertTrue(all(item.start_minute >= 10 * 60 for item in plan.segments))
        self.assertTrue(all(item.end_minute <= 12 * 60 for item in plan.segments))

    def test_cross_midnight_tariff_config(self) -> None:
        config = load_config(
            {"adaptive_off_peak_start": "22:30", "adaptive_off_peak_end": "06:30"}
        )
        self.assertTrue(config.is_off_peak(23 * 60))
        self.assertTrue(config.is_off_peak(6 * 60))
        self.assertFalse(config.is_off_peak(12 * 60))


if __name__ == "__main__":
    unittest.main()
