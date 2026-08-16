"""Data update coordinator for iMagi-x."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import ImagixApiClient, ImagixConnectionError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = timedelta(seconds=5)
EXPERT_PROGRAM_SYNC_INTERVAL = timedelta(minutes=10)


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
        self._unsub_expert_program_sync: CALLBACK_TYPE | None = None

    def async_start_expert_program_sync(self) -> None:
        """Synchronize the controller's server program to the expert program."""
        if self._unsub_expert_program_sync is not None:
            return

        self._unsub_expert_program_sync = async_track_time_interval(
            self.hass,
            self._async_sync_expert_program,
            EXPERT_PROGRAM_SYNC_INTERVAL,
        )

    def async_stop_expert_program_sync(self) -> None:
        """Stop the periodic expert-program synchronization."""
        if self._unsub_expert_program_sync is None:
            return

        self._unsub_expert_program_sync()
        self._unsub_expert_program_sync = None

    async def _async_sync_expert_program(self, _now: datetime) -> None:
        """Copy the latest ``progServer`` planning to ``prog_user``.

        ``prog_user`` is not available on every controller's ``/pool/info``
        response, so the source is deliberately written every ten minutes.
        The active filtration program is left unchanged.
        """
        try:
            data = await self._async_update_data()
        except UpdateFailed as err:
            _LOGGER.warning(
                "Unable to refresh progServer before synchronization: %s", err
            )
            return

        self.async_set_updated_data(data)

        state = data.get("state")
        filtration = state.get("filtration") if isinstance(state, dict) else None
        program_container = (
            filtration.get("progServer") if isinstance(filtration, dict) else None
        )
        server_program = (
            program_container.get("prog")
            if isinstance(program_container, dict)
            else None
        )
        if not isinstance(server_program, list) or not all(
            isinstance(band, dict) for band in server_program
        ):
            _LOGGER.debug("No progServer planning available; expert program not changed")
            return

        try:
            await self.client.async_set_custom_filtration_program(
                deepcopy(server_program)
            )
        except ImagixConnectionError as err:
            _LOGGER.warning("Unable to synchronize progServer to prog_user: %s", err)
            return

        _LOGGER.debug("Synchronized progServer to prog_user")

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from API."""
        try:
            return await self.client.get_pool_info()
        except ImagixConnectionError as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err
