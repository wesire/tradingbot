"""
WebSocket Manager for real-time streaming to dashboard clients.

Supports channel-based subscriptions, heartbeat/ping-pong, rate limiting,
and graceful client disconnect handling.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, Set

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

# Supported subscription channels
VALID_CHANNELS: Set[str] = {
    "positions",
    "trades",
    "sentiment",
    "status",
    "alerts",
    "opportunities",
}

# Configuration (overridable via env vars in main.py)
HEARTBEAT_INTERVAL = 30        # seconds
RATE_LIMIT_MAX = 10            # messages per second per client
RATE_LIMIT_WINDOW = 1.0        # seconds


class _ClientState:
    """Per-connection state tracked by the manager."""

    def __init__(self, websocket: WebSocket) -> None:
        self.websocket = websocket
        self.channels: Set[str] = set()
        self.connected_at: float = time.monotonic()
        # Rate-limit tracking: timestamps of recent sends
        self._send_times: deque = deque()

    def can_send(self) -> bool:
        """Return True if this client is within the rate limit."""
        now = time.monotonic()
        # Drop timestamps older than the window
        while self._send_times and now - self._send_times[0] > RATE_LIMIT_WINDOW:
            self._send_times.popleft()
        return len(self._send_times) < RATE_LIMIT_MAX

    def record_send(self) -> None:
        self._send_times.append(time.monotonic())


class WebSocketManager:
    """
    Manages WebSocket connections and broadcasts channel updates.

    Thread-safe for concurrent async access via asyncio.Lock.
    """

    def __init__(self) -> None:
        # websocket → _ClientState
        self._clients: Dict[WebSocket, _ClientState] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self, websocket: WebSocket) -> None:
        """Accept a new WebSocket connection and register it."""
        await websocket.accept()
        async with self._lock:
            self._clients[websocket] = _ClientState(websocket)
        logger.info("WebSocket client connected. Total clients: %d", len(self._clients))

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a client and clean up its state."""
        async with self._lock:
            self._clients.pop(websocket, None)
        logger.info("WebSocket client disconnected. Total clients: %d", len(self._clients))

    # ------------------------------------------------------------------
    # Subscription management
    # ------------------------------------------------------------------

    async def subscribe(self, websocket: WebSocket, channels: list[str]) -> None:
        """Subscribe a client to one or more channels."""
        valid = [c for c in channels if c in VALID_CHANNELS]
        invalid = [c for c in channels if c not in VALID_CHANNELS]

        async with self._lock:
            if websocket in self._clients:
                self._clients[websocket].channels.update(valid)

        if valid:
            await self._send(websocket, {
                "type": "subscribe_ack",
                "channels": valid,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        if invalid:
            await self._send(websocket, {
                "type": "error",
                "message": f"Unknown channels: {invalid}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

    async def unsubscribe(self, websocket: WebSocket, channels: list[str]) -> None:
        """Unsubscribe a client from one or more channels."""
        async with self._lock:
            if websocket in self._clients:
                self._clients[websocket].channels.difference_update(channels)

    # ------------------------------------------------------------------
    # Sending helpers
    # ------------------------------------------------------------------

    async def _send(self, websocket: WebSocket, message: dict) -> bool:
        """
        Send a JSON message to a single client.

        Returns True on success, False if the send failed (client gone).
        """
        async with self._lock:
            state = self._clients.get(websocket)

        if state is None:
            return False

        if not state.can_send():
            # Drop the message silently — client is being rate-limited
            logger.debug("Rate-limiting WebSocket client, dropping message")
            return False

        try:
            await websocket.send_json(message)
            state.record_send()
            return True
        except Exception:
            # Client disconnected mid-send
            await self.disconnect(websocket)
            return False

    async def broadcast(self, channel: str, data: Any) -> int:
        """
        Broadcast *data* to all clients subscribed to *channel*.

        Returns the number of clients that were sent the message.
        """
        message = {
            "type": "update",
            "channel": channel,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        async with self._lock:
            recipients = [
                ws for ws, state in self._clients.items()
                if channel in state.channels
            ]

        sent = 0
        for ws in recipients:
            if await self._send(ws, message):
                sent += 1
        return sent

    # ------------------------------------------------------------------
    # Heartbeat
    # ------------------------------------------------------------------

    async def send_ping(self, websocket: WebSocket) -> bool:
        """Send a ping to a specific client."""
        return await self._send(websocket, {"type": "ping"})

    async def run_heartbeat(self) -> None:
        """
        Background task: send a ping to every connected client every
        HEARTBEAT_INTERVAL seconds. Clients that fail to receive the ping
        are removed (the next send error triggers cleanup).
        """
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            async with self._lock:
                clients = list(self._clients.keys())
            for ws in clients:
                await self.send_ping(ws)

    # ------------------------------------------------------------------
    # Message handling (called from the endpoint)
    # ------------------------------------------------------------------

    async def handle_message(self, websocket: WebSocket, raw: str) -> None:
        """Parse and dispatch a message received from a client."""
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            await self._send(websocket, {
                "type": "error",
                "message": "Invalid JSON",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            return

        msg_type = msg.get("type", "")

        if msg_type == "subscribe":
            channels = msg.get("channels", [])
            if isinstance(channels, list):
                await self.subscribe(websocket, channels)
        elif msg_type == "unsubscribe":
            channels = msg.get("channels", [])
            if isinstance(channels, list):
                await self.unsubscribe(websocket, channels)
        elif msg_type == "pong":
            # Heartbeat response — no action needed
            pass
        else:
            await self._send(websocket, {
                "type": "error",
                "message": f"Unknown message type: {msg_type!r}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    @property
    def client_count(self) -> int:
        # dict.__len__ is a single atomic C-level operation in CPython; safe
        # without the lock for this non-critical diagnostic read.
        return len(self._clients)

    def subscriptions_for(self, websocket: WebSocket) -> Set[str]:
        """Return the set of channels a specific client is subscribed to.

        Returns a snapshot copy — safe to read outside the lock.
        """
        state = self._clients.get(websocket)
        return set(state.channels) if state else set()


# Module-level singleton used by main.py
ws_manager = WebSocketManager()
