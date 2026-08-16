"""Actions for adaptive filtration."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity

from ..manager import AdaptiveFiltrationManager
from .base import AdaptiveFiltrationEntity


class AdaptiveFiltrationRecalculateButton(AdaptiveFiltrationEntity, ButtonEntity):
    """Force a recalculation and publication of the expert program."""

    _attr_name = "Recalculer le planning de filtration"
    _attr_icon = "mdi:calculator-variant-outline"

    def __init__(self, manager: AdaptiveFiltrationManager, entry_id: str) -> None:
        super().__init__(manager, entry_id)
        self._attr_unique_id = f"{entry_id}_adaptive_filtration_recalculate"

    async def async_press(self) -> None:
        await self.manager.async_recalculate(force_publish=True)

