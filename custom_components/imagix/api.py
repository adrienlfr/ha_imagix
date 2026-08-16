"""API client for iMagi-x pool controller."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import aiohttp
import async_timeout

_LOGGER = logging.getLogger(__name__)

API_TIMEOUT = 10
LOCAL_POOL_ID = "local"

FILTRATION_ROUTE = "configure-filtration"
HEATER_ROUTE = "configure-heater"
SPOTLIGHT_ROUTE = "spotlight"
PH_ROUTE = "configure-ph-treatment"
CHLORINE_ROUTE = "configure-chlorine-treatment"
ELECTROLYZER_ROUTE = "configure-electrolyzer-treatment"


class ImagixApiClient:
    """Client to interact with iMagi-x API."""

    def __init__(self, ip: str, session: aiohttp.ClientSession) -> None:
        """Initialize the API client."""
        self._ip = ip
        self._session = session
        self._base_url = f"http://{ip}:11000/api/v1"

    async def get_pool_info(self) -> dict[str, Any]:
        """Get pool information from the API."""
        return await self._api_request("pool/info")

    async def async_set_spotlight(self, is_on: bool) -> None:
        """Turn the pool spotlight on or off in manual mode."""
        await self._async_command(
            SPOTLIGHT_ROUTE,
            {"mode": {"wanted": 2 if is_on else 1}},
        )

    async def async_set_filtration_mode(self, mode: int) -> None:
        """Set the filtration operating mode."""
        await self._async_command(FILTRATION_ROUTE, {"mode": {"wanted": mode}})

    async def async_set_filtration_program(self, program: int) -> None:
        """Set the active filtration program."""
        await self._async_command(
            FILTRATION_ROUTE,
            {"program": {"wanted": program}},
        )

    async def async_set_custom_filtration_program(
        self, program: list[dict[str, Any]]
    ) -> None:
        """Replace the expert filtration program with ``program``.

        The local iMagi-x API stores the application's "Custom (expert)"
        planning under ``prog_user``. The program format is the one returned
        by ``/pool/info``: temperature bands containing ``minute``/``mode``
        steps.
        """
        await self._async_command(
            FILTRATION_ROUTE,
            {"prog_user": {"prog": program}},
        )

    async def async_set_swimming(self, remain_time: int) -> None:
        """Start or stop the timed swimming filtration mode."""
        await self._async_command(
            FILTRATION_ROUTE,
            {"swimming_mode": {"remain_time": remain_time}},
        )

    async def async_set_pause(self, remain_time: int) -> None:
        """Start or stop the timed filtration pause."""
        await self._async_command(
            FILTRATION_ROUTE,
            {"pause": {"remain_time": remain_time}},
        )

    async def async_set_pause_default_time(self, default_time: int) -> None:
        """Set the default duration used for a filtration pause."""
        await self._async_command(
            FILTRATION_ROUTE,
            {"pause": {"default_time": default_time}},
        )

    async def async_set_heater_mode(self, mode: int) -> None:
        """Set the heater operating mode."""
        await self._async_command(HEATER_ROUTE, {"mode": {"wanted": mode}})

    async def async_set_heater_eco_temperature(self, temperature: float) -> None:
        """Set the Eco heating target, expressed in degrees Celsius."""
        await self._async_command(
            HEATER_ROUTE,
            {"mode_eco_temp": {"temperature": temperature}},
        )

    async def async_set_heater_comfort_temperature(self, temperature: float) -> None:
        """Set the Comfort heating target, expressed in degrees Celsius."""
        await self._async_command(
            HEATER_ROUTE,
            {"mode_confort_temp": {"temperature": temperature}},
        )

    async def async_set_heater_filtration_priority(self, enabled: bool) -> None:
        """Choose whether heating may request filtration outside its program."""
        await self._async_command(
            HEATER_ROUTE,
            {"filtration_priority": {"enable": enabled}},
        )

    async def async_set_heater_settings(self, mode: int, priority: bool) -> None:
        """Set the heater mode and its filtration-priority setting together."""
        await self._async_command(
            HEATER_ROUTE,
            {
                "mode": {"wanted": mode},
                "filtration_priority": {"enable": priority},
            },
        )

    async def async_set_heater_priority_schedule(
        self, planning: list[dict[str, int]]
    ) -> None:
        """Set the time slots during which heating may request filtration.

        The controller represents a daily schedule as changes of state, using
        minutes since midnight and values 0 (not authorised) or 1 (authorised).
        """
        await self._async_command(
            HEATER_ROUTE,
            {
                "filtration_priority": {"enable": True},
                "authorization": {"planning": planning},
            },
        )

    async def async_set_ph_mode(self, mode: int) -> None:
        """Set the pH treatment operating mode."""
        await self._async_command(PH_ROUTE, {"setmode": {"mode": mode}})

    async def async_set_ph_setpoint(self, value: float, delta: float) -> None:
        """Set the pH target and its delta."""
        await self._async_command(
            PH_ROUTE,
            {"setpoint": {"value": value, "delta_x": delta}},
        )

    async def async_set_chlorine_mode(self, mode: int) -> None:
        """Set the chlorine treatment operating mode."""
        await self._async_command(CHLORINE_ROUTE, {"setmode": {"mode": mode}})

    async def async_set_chlorine_setpoint(self, value: float, delta: float) -> None:
        """Set the chlorine/ORP target and its delta."""
        await self._async_command(
            CHLORINE_ROUTE,
            {"setpoint": {"value": value, "delta_x": delta}},
        )

    async def async_set_electrolyzer_mode(self, mode: int) -> None:
        """Set the electrolyzer operating mode."""
        await self._async_command(
            ELECTROLYZER_ROUTE,
            {"setmode": {"mode": mode}},
        )

    async def async_set_electrolyzer_setpoint(self, value: float, delta: float) -> None:
        """Set the electrolyzer target and its delta."""
        await self._async_command(
            ELECTROLYZER_ROUTE,
            {"setpoint": {"value": value, "delta": delta}},
        )

    async def _async_command(self, route: str, payload: dict[str, Any]) -> None:
        """Send a confirmed local command to the controller."""
        await self._api_request(
            f"pool/{LOCAL_POOL_ID}/{route}",
            method="POST",
            payload=payload,
        )

    async def _api_request(
        self,
        endpoint: str,
        *,
        method: str = "GET",
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make a request to the API."""
        url = f"{self._base_url}/{endpoint}"

        try:
            async with async_timeout.timeout(API_TIMEOUT):
                async with self._session.request(
                    method,
                    url,
                    json=payload,
                    headers={"Accept": "*/*"},
                ) as response:
                    body = await response.text()
                    if response.status >= 400:
                        raise ImagixApiError(response.status, body)
                    if not body:
                        return {}
                    try:
                        return json.loads(body)
                    except json.JSONDecodeError:
                        _LOGGER.debug("Non-JSON response from %s: %s", url, body)
                        return {}
        except asyncio.TimeoutError as exception:
            _LOGGER.error("Timeout error calling %s", url)
            raise ImagixConnectionError(
                f"Timeout connecting to iMagi-x at {self._ip}"
            ) from exception
        except ImagixApiError:
            raise
        except aiohttp.ClientError as exception:
            _LOGGER.error("Error calling %s: %s", url, exception)
            raise ImagixConnectionError(
                f"Error connecting to iMagi-x at {self._ip}: {exception}"
            ) from exception
        except Exception as exception:
            _LOGGER.error("Unexpected error calling %s: %s", url, exception)
            raise ImagixConnectionError(
                f"Unexpected error connecting to iMagi-x at {self._ip}"
            ) from exception

    async def test_connection(self) -> bool:
        """Test if we can connect to the iMagi-x controller."""
        try:
            data = await self.get_pool_info()
            return bool(data.get("state"))
        except ImagixConnectionError:
            return False


class ImagixConnectionError(Exception):
    """Exception to indicate a connection error."""


class ImagixApiError(ImagixConnectionError):
    """Exception raised when the iMagi-x API rejects a request."""

    def __init__(self, status: int, body: str) -> None:
        """Initialize an API error."""
        detail = body.strip() or "No error detail returned"
        super().__init__(f"iMagi-x API returned HTTP {status}: {detail}")
        self.status = status
        self.body = body
