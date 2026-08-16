"""Persistent state for adaptive filtration."""
from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from ..const import DOMAIN

STORAGE_VERSION = 1


class AdaptiveFiltrationStore:
    """Persist debt and accounting without mixing them into configuration."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store = Store[dict[str, Any]](
            hass,
            STORAGE_VERSION,
            f"{DOMAIN}.adaptive_filtration.{entry_id}",
        )

    async def async_load(self) -> dict[str, Any]:
        """Load the last state."""
        return await self._store.async_load() or {}

    async def async_save(self, data: dict[str, Any]) -> None:
        """Save a JSON-serializable snapshot."""
        await self._store.async_save(data)

