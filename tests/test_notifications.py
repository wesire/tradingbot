"""
Tests for the notifications module.

Covers:
- TelegramNotifier: formatting, send with mocked HTTP, availability check
- NotificationManager: channel routing, throttling, sync dispatch
"""
import time
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import pytest

from bot.notifications.base import BaseNotifier, Severity
from bot.notifications.notification_manager import NotificationManager
from bot.notifications.telegram_notifier import TelegramNotifier


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class MemoryNotifier(BaseNotifier):
    """In-process notifier that records calls for assertions."""

    def __init__(self, available: bool = True):
        self._available = available
        self.calls: list = []

    def is_available(self) -> bool:
        return self._available

    def send_alert(
        self,
        title: str,
        message: str,
        severity: Severity = Severity.INFO,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        self.calls.append(
            {"title": title, "message": message, "severity": severity, "metadata": metadata}
        )
        return True


# ---------------------------------------------------------------------------
# TelegramNotifier
# ---------------------------------------------------------------------------

class TestTelegramNotifier:
    def test_not_available_without_config(self):
        notifier = TelegramNotifier(token="", chat_id="")
        assert not notifier.is_available()

    def test_available_with_config(self):
        notifier = TelegramNotifier(token="123:ABC", chat_id="456")
        assert notifier.is_available()

    def test_send_alert_skips_when_not_configured(self):
        notifier = TelegramNotifier(token="", chat_id="")
        result = notifier.send_alert("Title", "Body")
        assert result is False

    @patch("bot.notifications.telegram_notifier.requests.post")
    def test_send_alert_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        notifier = TelegramNotifier(token="tok", chat_id="cid")
        result = notifier.send_alert("Test", "Body", Severity.INFO)
        assert result is True
        mock_post.assert_called_once()

        call_kwargs = mock_post.call_args[1]
        payload = call_kwargs["json"]
        assert payload["chat_id"] == "cid"
        assert "Test" in payload["text"]
        assert payload["parse_mode"] == "Markdown"

    @patch("bot.notifications.telegram_notifier.requests.post")
    def test_send_alert_http_error(self, mock_post):
        import requests as req
        mock_post.side_effect = req.RequestException("connection refused")

        notifier = TelegramNotifier(token="tok", chat_id="cid")
        result = notifier.send_alert("Title", "Body")
        assert result is False

    @patch("bot.notifications.telegram_notifier.requests.post")
    def test_severity_prefix_in_message(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        notifier = TelegramNotifier(token="tok", chat_id="cid")
        notifier.send_alert("AlertTitle", "Body", Severity.CRITICAL)
        text = mock_post.call_args[1]["json"]["text"]
        assert "🔴" in text

    @patch("bot.notifications.telegram_notifier.requests.post")
    def test_trade_executed_long(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        notifier = TelegramNotifier(token="tok", chat_id="cid")
        notifier.send_trade_executed("BTC/USDT", "long", 65000.0, 0.01, pnl=12.5)
        text = mock_post.call_args[1]["json"]["text"]
        assert "📈" in text
        assert "BTC/USDT" in text
        assert "12.50" in text

    @patch("bot.notifications.telegram_notifier.requests.post")
    def test_trade_executed_short(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        notifier = TelegramNotifier(token="tok", chat_id="cid")
        notifier.send_trade_executed("ETH/USDT", "short", 3200.0, 0.5)
        text = mock_post.call_args[1]["json"]["text"]
        assert "📉" in text

    @patch("bot.notifications.telegram_notifier.requests.post")
    def test_daily_pnl(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        notifier = TelegramNotifier(token="tok", chat_id="cid")
        notifier.send_daily_pnl(pnl=150.0, win_rate=0.65, trades=20)
        text = mock_post.call_args[1]["json"]["text"]
        assert "150" in text

    @patch("bot.notifications.telegram_notifier.requests.post")
    def test_high_confidence_opportunity(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        notifier = TelegramNotifier(token="tok", chat_id="cid")
        notifier.send_high_confidence_opportunity("SOL/USDT", "long", 0.87, ml_signal="long")
        text = mock_post.call_args[1]["json"]["text"]
        assert "🎯" in text
        assert "SOL/USDT" in text

    @patch("bot.notifications.telegram_notifier.requests.post")
    def test_metadata_appended_to_message(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        notifier = TelegramNotifier(token="tok", chat_id="cid")
        notifier.send_alert(
            "Title", "Body", metadata={"pair": "BTC/USDT", "confidence": 0.9}
        )
        text = mock_post.call_args[1]["json"]["text"]
        assert "pair" in text
        assert "BTC/USDT" in text


# ---------------------------------------------------------------------------
# NotificationManager
# ---------------------------------------------------------------------------

class TestNotificationManager:
    @pytest.fixture
    def manager(self):
        mgr = NotificationManager(throttle_minutes=1.0)
        return mgr

    @pytest.fixture
    def manager_with_notifier(self):
        mgr = NotificationManager(throttle_minutes=1.0)
        notifier = MemoryNotifier()
        mgr.add_notifier("memory", notifier)
        return mgr, notifier

    def test_add_and_remove_notifier(self, manager):
        n = MemoryNotifier()
        manager.add_notifier("test", n)
        assert "test" in manager._notifiers
        manager.remove_notifier("test")
        assert "test" not in manager._notifiers

    def test_sync_dispatch_reaches_notifier(self, manager_with_notifier):
        mgr, notifier = manager_with_notifier
        results = mgr.send_alert_sync("Test title", "Test body", Severity.INFO)
        assert results.get("memory") is True
        assert len(notifier.calls) == 1
        assert notifier.calls[0]["title"] == "Test title"

    def test_throttle_suppresses_duplicate(self, manager_with_notifier):
        mgr, notifier = manager_with_notifier
        mgr.send_alert_sync("Same title", "Body 1", Severity.INFO)
        mgr.send_alert_sync("Same title", "Body 2", Severity.INFO)
        # Second call should be throttled
        assert len(notifier.calls) == 1

    def test_different_severity_not_throttled(self, manager_with_notifier):
        mgr, notifier = manager_with_notifier
        mgr.send_alert_sync("Title", "Body", Severity.INFO)
        mgr.send_alert_sync("Title", "Body", Severity.CRITICAL)
        assert len(notifier.calls) == 2

    def test_different_title_not_throttled(self, manager_with_notifier):
        mgr, notifier = manager_with_notifier
        mgr.send_alert_sync("Title A", "Body", Severity.INFO)
        mgr.send_alert_sync("Title B", "Body", Severity.INFO)
        assert len(notifier.calls) == 2

    def test_unavailable_notifier_skipped(self, manager):
        unavailable = MemoryNotifier(available=False)
        manager.add_notifier("unavail", unavailable)
        results = manager.send_alert_sync("Title", "Body")
        assert results.get("unavail") is None  # Not dispatched
        assert len(unavailable.calls) == 0

    def test_notifier_exception_does_not_propagate(self, manager):
        """A crashing notifier should not raise in the manager."""
        class FaultyNotifier(BaseNotifier):
            def send_alert(self, *args, **kwargs):
                raise RuntimeError("Simulated failure")

        manager.add_notifier("faulty", FaultyNotifier())
        # Should not raise
        results = manager.send_alert_sync("Title", "Body")
        assert results.get("faulty") is False

    def test_metadata_forwarded_to_notifier(self, manager_with_notifier):
        mgr, notifier = manager_with_notifier
        meta = {"pair": "BTC/USDT"}
        mgr.send_alert_sync("Title", "Body", metadata=meta)
        assert notifier.calls[0]["metadata"] == meta

    def test_queue_based_send_delivers(self):
        """Enqueue an alert and verify it reaches the notifier via worker thread."""
        mgr = NotificationManager(throttle_minutes=0)
        notifier = MemoryNotifier()
        mgr.add_notifier("mem", notifier)
        mgr.start()
        try:
            mgr.send_alert("Async title", "Async body", Severity.WARNING)
            # Give the background thread time to process
            deadline = time.monotonic() + 3.0
            while len(notifier.calls) == 0 and time.monotonic() < deadline:
                time.sleep(0.05)
            assert len(notifier.calls) == 1
            assert notifier.calls[0]["title"] == "Async title"
        finally:
            mgr.stop()

    def test_stop_graceful(self):
        mgr = NotificationManager(throttle_minutes=0)
        mgr.start()
        mgr.stop(timeout=2.0)
        assert not mgr._worker.is_alive()
