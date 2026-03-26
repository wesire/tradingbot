"""
Unit tests for tv_gateway.websocket_manager.WebSocketManager.

Covers: subscribe, unsubscribe, broadcast, rate limiting, client cleanup,
and the WebSocket /ws endpoint integration.
"""
import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from tv_gateway.websocket_manager import WebSocketManager, VALID_CHANNELS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ws(send_raises: bool = False) -> MagicMock:
    """Return a mock WebSocket."""
    ws = MagicMock()
    if send_raises:
        ws.send_json = AsyncMock(side_effect=RuntimeError("disconnected"))
    else:
        ws.send_json = AsyncMock()
    ws.accept = AsyncMock()
    return ws


# ---------------------------------------------------------------------------
# connect / disconnect
# ---------------------------------------------------------------------------

class TestConnectDisconnect:
    @pytest.mark.asyncio
    async def test_connect_accepts_and_registers(self):
        manager = WebSocketManager()
        ws = _make_ws()
        await manager.connect(ws)
        ws.accept.assert_awaited_once()
        assert manager.client_count == 1

    @pytest.mark.asyncio
    async def test_disconnect_removes_client(self):
        manager = WebSocketManager()
        ws = _make_ws()
        await manager.connect(ws)
        await manager.disconnect(ws)
        assert manager.client_count == 0

    @pytest.mark.asyncio
    async def test_disconnect_unknown_client_is_noop(self):
        manager = WebSocketManager()
        ws = _make_ws()
        # Should not raise
        await manager.disconnect(ws)
        assert manager.client_count == 0


# ---------------------------------------------------------------------------
# subscribe / unsubscribe
# ---------------------------------------------------------------------------

class TestSubscribeUnsubscribe:
    @pytest.mark.asyncio
    async def test_subscribe_valid_channels(self):
        manager = WebSocketManager()
        ws = _make_ws()
        await manager.connect(ws)
        await manager.subscribe(ws, ["positions", "trades"])
        subs = manager.subscriptions_for(ws)
        assert "positions" in subs
        assert "trades" in subs

    @pytest.mark.asyncio
    async def test_subscribe_sends_ack(self):
        manager = WebSocketManager()
        ws = _make_ws()
        await manager.connect(ws)
        await manager.subscribe(ws, ["positions"])
        call_args = ws.send_json.call_args_list
        ack = next((c.args[0] for c in call_args if c.args[0].get("type") == "subscribe_ack"), None)
        assert ack is not None
        assert "positions" in ack["channels"]

    @pytest.mark.asyncio
    async def test_subscribe_invalid_channels_returns_error(self):
        manager = WebSocketManager()
        ws = _make_ws()
        await manager.connect(ws)
        await manager.subscribe(ws, ["nonexistent"])
        call_args = ws.send_json.call_args_list
        err = next((c.args[0] for c in call_args if c.args[0].get("type") == "error"), None)
        assert err is not None

    @pytest.mark.asyncio
    async def test_subscribe_mixed_valid_and_invalid(self):
        manager = WebSocketManager()
        ws = _make_ws()
        await manager.connect(ws)
        await manager.subscribe(ws, ["positions", "bogus"])
        subs = manager.subscriptions_for(ws)
        assert "positions" in subs
        assert "bogus" not in subs

    @pytest.mark.asyncio
    async def test_unsubscribe_removes_channel(self):
        manager = WebSocketManager()
        ws = _make_ws()
        await manager.connect(ws)
        await manager.subscribe(ws, ["positions", "trades"])
        await manager.unsubscribe(ws, ["positions"])
        subs = manager.subscriptions_for(ws)
        assert "positions" not in subs
        assert "trades" in subs


# ---------------------------------------------------------------------------
# broadcast
# ---------------------------------------------------------------------------

class TestBroadcast:
    @pytest.mark.asyncio
    async def test_broadcast_sends_to_subscribed_clients(self):
        manager = WebSocketManager()
        ws1 = _make_ws()
        ws2 = _make_ws()
        await manager.connect(ws1)
        await manager.connect(ws2)
        await manager.subscribe(ws1, ["positions"])
        await manager.subscribe(ws2, ["trades"])

        sent = await manager.broadcast("positions", {"positions": []})
        assert sent == 1
        # ws1 got the message (after the subscribe_ack call)
        position_msgs = [
            c.args[0] for c in ws1.send_json.call_args_list
            if c.args[0].get("channel") == "positions"
        ]
        assert len(position_msgs) == 1
        assert position_msgs[0]["type"] == "update"

    @pytest.mark.asyncio
    async def test_broadcast_not_sent_to_unsubscribed_clients(self):
        manager = WebSocketManager()
        ws = _make_ws()
        await manager.connect(ws)
        # Not subscribed to "sentiment"
        sent = await manager.broadcast("sentiment", {"score": 0.5})
        assert sent == 0

    @pytest.mark.asyncio
    async def test_broadcast_cleans_up_dead_clients(self):
        manager = WebSocketManager()
        ws = _make_ws(send_raises=True)
        await manager.connect(ws)
        await manager.subscribe(ws, ["positions"])
        # Simulate disconnected client — send_json raises
        await manager.broadcast("positions", {"positions": []})
        # Client should have been cleaned up
        assert manager.client_count == 0

    @pytest.mark.asyncio
    async def test_broadcast_message_format(self):
        manager = WebSocketManager()
        ws = _make_ws()
        await manager.connect(ws)
        await manager.subscribe(ws, ["status"])
        await manager.broadcast("status", {"running": True})
        msgs = [
            c.args[0] for c in ws.send_json.call_args_list
            if c.args[0].get("type") == "update"
        ]
        assert len(msgs) == 1
        msg = msgs[0]
        assert msg["channel"] == "status"
        assert msg["data"] == {"running": True}
        assert "timestamp" in msg


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

class TestRateLimiting:
    @pytest.mark.asyncio
    async def test_rate_limit_drops_excess_messages(self):
        """Sending more than 10 messages per second should drop the extras."""
        from tv_gateway.websocket_manager import RATE_LIMIT_MAX

        manager = WebSocketManager()
        ws = _make_ws()
        await manager.connect(ws)
        await manager.subscribe(ws, ["status"])

        # Flood with messages — all within the same second
        for _ in range(RATE_LIMIT_MAX + 5):
            await manager.broadcast("status", {"ping": True})

        # subscribe_ack + at most RATE_LIMIT_MAX update messages
        sent_updates = [
            c for c in ws.send_json.call_args_list
            if c.args[0].get("type") == "update"
        ]
        assert len(sent_updates) <= RATE_LIMIT_MAX


# ---------------------------------------------------------------------------
# handle_message
# ---------------------------------------------------------------------------

class TestHandleMessage:
    @pytest.mark.asyncio
    async def test_handle_subscribe_message(self):
        manager = WebSocketManager()
        ws = _make_ws()
        await manager.connect(ws)
        msg = json.dumps({"type": "subscribe", "channels": ["positions"]})
        await manager.handle_message(ws, msg)
        assert "positions" in manager.subscriptions_for(ws)

    @pytest.mark.asyncio
    async def test_handle_unsubscribe_message(self):
        manager = WebSocketManager()
        ws = _make_ws()
        await manager.connect(ws)
        await manager.subscribe(ws, ["positions", "trades"])
        msg = json.dumps({"type": "unsubscribe", "channels": ["positions"]})
        await manager.handle_message(ws, msg)
        assert "positions" not in manager.subscriptions_for(ws)
        assert "trades" in manager.subscriptions_for(ws)

    @pytest.mark.asyncio
    async def test_handle_pong_is_noop(self):
        manager = WebSocketManager()
        ws = _make_ws()
        await manager.connect(ws)
        ws.send_json.reset_mock()
        await manager.handle_message(ws, json.dumps({"type": "pong"}))
        ws.send_json.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_handle_invalid_json_returns_error(self):
        manager = WebSocketManager()
        ws = _make_ws()
        await manager.connect(ws)
        ws.send_json.reset_mock()
        await manager.handle_message(ws, "not json {{{")
        call = ws.send_json.call_args.args[0]
        assert call["type"] == "error"

    @pytest.mark.asyncio
    async def test_handle_unknown_type_returns_error(self):
        manager = WebSocketManager()
        ws = _make_ws()
        await manager.connect(ws)
        ws.send_json.reset_mock()
        await manager.handle_message(ws, json.dumps({"type": "unknown_cmd"}))
        call = ws.send_json.call_args.args[0]
        assert call["type"] == "error"


# ---------------------------------------------------------------------------
# /ws endpoint integration
# ---------------------------------------------------------------------------

class TestWebSocketEndpoint:
    """Integration tests for the /ws FastAPI endpoint."""

    def test_ws_connect_and_subscribe(self):
        """Client can connect and subscribe to channels."""
        from fastapi.testclient import TestClient
        import tv_gateway.main as main_module

        with TestClient(main_module.app) as client:
            with client.websocket_connect("/ws") as ws:
                ws.send_json({"type": "subscribe", "channels": ["positions"]})
                msg = ws.receive_json()
                assert msg["type"] == "subscribe_ack"
                assert "positions" in msg["channels"]

    def test_ws_subscribe_invalid_channel(self):
        """Subscribing to an invalid channel returns an error response."""
        from fastapi.testclient import TestClient
        import tv_gateway.main as main_module

        with TestClient(main_module.app) as client:
            with client.websocket_connect("/ws") as ws:
                ws.send_json({"type": "subscribe", "channels": ["bogus_channel"]})
                msg = ws.receive_json()
                assert msg["type"] == "error"

    def test_ws_max_clients_rejected(self):
        """Connections beyond WS_MAX_CLIENTS should be refused."""
        from fastapi.testclient import TestClient
        import tv_gateway.main as main_module

        original_max = main_module.WS_MAX_CLIENTS
        main_module.WS_MAX_CLIENTS = 0  # Reject all
        try:
            with TestClient(main_module.app) as client:
                with pytest.raises(Exception):
                    with client.websocket_connect("/ws"):
                        pass
        finally:
            main_module.WS_MAX_CLIENTS = original_max
