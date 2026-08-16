"""Data update coordinator for iMagi-x."""
from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import ImagixApiClient, ImagixConnectionError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = timedelta(seconds=5)


class ImagixDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching iMagi-x data."""

    def __init__(self, hass: HomeAssistant, client: ImagixApiClient) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from API."""
        try:
            return await self.client.get_pool_info()
        except ImagixConnectionError as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err
