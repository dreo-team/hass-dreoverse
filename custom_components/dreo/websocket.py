"""WebSocket client for Dreo real-time state updates."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

WEBSOCKET_URL = "wss://wsb-{region}.dreo-tech.com/websocket"
PING_INTERVAL = 15
PING_MESSAGE = "2"
RECONNECT_DELAY = 5

# Map token region suffix to WebSocket region slug
REGION_MAP: dict[str, str] = {
    "NA": "us",
    "US": "us",
    "EU": "eu",
}


class DreoWebSocket:
    """Manage a WebSocket connection for real-time Dreo device updates."""

    def __init__(
        self,
        token: str,
        region: str,
        on_message: Callable[[str, dict[str, Any]], None],
    ) -> None:
        """Initialize the WebSocket client."""
        self._token = token
        self._region = REGION_MAP.get(region.upper(), "us")
        self._on_message = on_message
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._session: aiohttp.ClientSession | None = None
        self._running = False
        self._task: asyncio.Task[None] | None = None

    @property
    def connected(self) -> bool:
        """Return True if WebSocket is open."""
        return self._ws is not None and not self._ws.closed

    async def start(self) -> None:
        """Start the WebSocket connection loop."""
        self._running = True
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Gracefully close the WebSocket and clean up."""
        self._running = False
        if self._ws and not self._ws.closed:
            await self._ws.close()
        if self._session and not self._session.closed:
            await self._session.close()
        if self._task:
            self._task.cancel()

    async def _run(self) -> None:
        """Reconnect loop — keeps retrying until stopped."""
        while self._running:
            try:
                await self._connect_and_listen()
            except Exception:
                _LOGGER.debug(
                    "Dreo WebSocket disconnected, reconnecting in %ss",
                    RECONNECT_DELAY,
                    exc_info=True,
                )
            if self._running:
                await asyncio.sleep(RECONNECT_DELAY)

    async def _connect_and_listen(self) -> None:
        """Open a WebSocket and consume messages until closed."""
        timestamp = int(time.time() * 1000)
        url = (
            f"{WEBSOCKET_URL.format(region=self._region)}"
            f"?accessToken={self._token}&timestamp={timestamp}"
        )

        self._session = aiohttp.ClientSession()
        try:
            self._ws = await self._session.ws_connect(url)
            _LOGGER.info("Dreo WebSocket connected to %s region", self._region)

            ping_task = asyncio.create_task(self._ping_loop())
            try:
                async for msg in self._ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        self._process_message(msg.data)
                    elif msg.type in (
                        aiohttp.WSMsgType.CLOSED,
                        aiohttp.WSMsgType.ERROR,
                    ):
                        break
            finally:
                ping_task.cancel()
        finally:
            if self._session and not self._session.closed:
                await self._session.close()
            self._ws = None
            self._session = None

    async def _ping_loop(self) -> None:
        """Send periodic text pings to keep the connection alive."""
        try:
            while self._ws and not self._ws.closed:
                await self._ws.send_str(PING_MESSAGE)
                await asyncio.sleep(PING_INTERVAL)
        except (ConnectionError, asyncio.CancelledError):
            pass

    def _process_message(self, raw: str) -> None:
        """Parse an incoming WebSocket message and dispatch to callback."""
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return

        device_sn: str | None = data.get("devicesn")
        reported: dict[str, Any] | None = data.get("reported")

        if device_sn and isinstance(reported, dict) and reported:
            _LOGGER.debug(
                "WebSocket push for %s: %s",
                device_sn,
                reported,
            )
            self._on_message(device_sn, reported)
