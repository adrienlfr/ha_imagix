"""Shared entity helpers for iMagi-x."""
from __future__ import annotations

from collections.abc import Awaitable
from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ImagixDataUpdateCoordinator


class ImagixEntity(CoordinatorEntity[ImagixDataUpdateCoordinator]):
    """Base entity backed by the iMagi-x coordinator."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ImagixDataUpdateCoordinator,
        entry_id: str,
    ) -> None:
        """Initialize the iMagi-x entity."""
        super().__init__(coordinator)
        self._entry_id = entry_id

        system = self._state("system")
        version = system.get("version", {})
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name="iMAGI-X",
            manufacturer="Piscines Magiline",
            model="iMAGI-X pool controller",
            serial_number=system.get("id"),
            sw_version=version.get("buildVersion"),
        )

    def _state(self, *path: str) -> dict[str, Any]:
        """Return a mapping from the coordinator data."""
        value: Any = self.coordinator.data.get("state", {})
        for key in path:
            if not isinstance(value, dict):
                return {}
            value = value.get(key, {})
        return value if isinstance(value, dict) else {}

    async def _async_execute(self, command: Awaitable[None]) -> None:
        """Run a command and immediately refresh the reported state."""
        await command
        await self.coordinator.async_request_refresh()
