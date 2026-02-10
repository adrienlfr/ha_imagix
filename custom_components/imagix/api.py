"""API client for iMagi-x pool controller."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp
import async_timeout

_LOGGER = logging.getLogger(__name__)

API_TIMEOUT = 10


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

    async def _api_request(self, endpoint: str) -> dict[str, Any]:
        """Make a request to the API."""
        url = f"{self._base_url}/{endpoint}"
        
        try:
            async with async_timeout.timeout(API_TIMEOUT):
                async with self._session.get(url) as response:
                    response.raise_for_status()
                    return await response.json()
        except asyncio.TimeoutError as exception:
            _LOGGER.error("Timeout error fetching information from %s", url)
            raise ImagixConnectionError(
                f"Timeout connecting to iMagi-x at {self._ip}"
            ) from exception
        except aiohttp.ClientError as exception:
            _LOGGER.error("Error fetching information from %s: %s", url, exception)
            raise ImagixConnectionError(
                f"Error connecting to iMagi-x at {self._ip}: {exception}"
            ) from exception
        except Exception as exception:
            _LOGGER.error("Unexpected error fetching information from %s: %s", url, exception)
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
