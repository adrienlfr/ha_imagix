"""Regression tests for Home Assistant entity module initialization."""
from __future__ import annotations

from datetime import datetime
import importlib
from pathlib import Path
import sys
from types import ModuleType
import unittest


INTEGRATION_ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "imagix"
sys.path.insert(0, str(INTEGRATION_ROOT))


class EntityImportTests(unittest.TestCase):
    """Ensure module-level entity descriptions can be evaluated."""

    def test_adaptive_sensor_module_imports(self) -> None:
        module_names = (
            "homeassistant",
            "homeassistant.components",
            "homeassistant.components.sensor",
            "homeassistant.util",
            "homeassistant.util.dt",
            "adaptive_filtration.manager",
            "adaptive_filtration.entities.base",
            "adaptive_filtration.entities.sensor",
        )
        previous = {name: sys.modules.get(name) for name in module_names}
        try:
            homeassistant = ModuleType("homeassistant")
            components = ModuleType("homeassistant.components")
            sensor = ModuleType("homeassistant.components.sensor")
            util = ModuleType("homeassistant.util")
            dt = ModuleType("homeassistant.util.dt")
            manager = ModuleType("adaptive_filtration.manager")
            base = ModuleType("adaptive_filtration.entities.base")

            class SensorEntity:
                pass

            class SensorStateClass:
                MEASUREMENT = "measurement"

            class AdaptiveFiltrationManager:
                pass

            class AdaptiveFiltrationEntity:
                pass

            sensor.SensorEntity = SensorEntity
            sensor.SensorStateClass = SensorStateClass
            dt.now = datetime.now
            util.dt = dt
            manager.AdaptiveFiltrationManager = AdaptiveFiltrationManager
            base.AdaptiveFiltrationEntity = AdaptiveFiltrationEntity

            sys.modules.update(
                {
                    "homeassistant": homeassistant,
                    "homeassistant.components": components,
                    "homeassistant.components.sensor": sensor,
                    "homeassistant.util": util,
                    "homeassistant.util.dt": dt,
                    "adaptive_filtration.manager": manager,
                    "adaptive_filtration.entities.base": base,
                }
            )
            sys.modules.pop("adaptive_filtration.entities.sensor", None)

            imported = importlib.import_module(
                "adaptive_filtration.entities.sensor"
            )
            self.assertEqual(len(imported.DESCRIPTIONS), 13)
        finally:
            for name, module in previous.items():
                if module is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = module


if __name__ == "__main__":
    unittest.main()
