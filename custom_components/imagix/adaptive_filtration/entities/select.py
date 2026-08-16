"""Strategy selector for adaptive filtration."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity

from ..config import CONF_STRATEGY
from ..manager import AdaptiveFiltrationManager
from ..models import Strategy
from .base import AdaptiveFiltrationEntity


class AdaptiveFiltrationStrategySelect(AdaptiveFiltrationEntity, SelectEntity):
    """Select the global adaptive filtration strategy."""

    _attr_name = "Stratégie de filtration"
    _attr_icon = "mdi:tune-variant"
    _attr_options = [strategy.value for strategy in Strategy]

    def __init__(self, manager: AdaptiveFiltrationManager, entry_id: str) -> None:
        super().__init__(manager, entry_id)
        self._attr_unique_id = f"{entry_id}_adaptive_filtration_strategy"

    @property
    def current_option(self) -> str:
        return self.manager.config.strategy.value

    async def async_select_option(self, option: str) -> None:
        Strategy(option)
        options = dict(self.manager.entry.options)
        options[CONF_STRATEGY] = option
        self.manager.hass.config_entries.async_update_entry(
            self.manager.entry,
            options=options,
        )

