"""
Unit tests for SentimentSpikeDetector.

Covers:
- Threshold detection (spike fired when change >= threshold, not fired below)
- Direction and severity classification
- Cooldown suppression (duplicate alerts suppressed within cooldown window)
- get_recent_spikes filtering
- get_active_cooldowns
- Integration: notifications dispatched when spikes are detected
"""
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest

from bot.sentiment.spike_detector import (
    SentimentSpikeDetector,
    SentimentSpike,
    _classify_severity,
)
from bot.notifications import NotificationManager, Severity


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _detector(threshold=0.3, window_minutes=60, cooldown_minutes=30, **kwargs):
    return SentimentSpikeDetector(
        spike_threshold=threshold,
        window_minutes=window_minutes,
        cooldown_minutes=cooldown_minutes,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# _classify_severity
# ---------------------------------------------------------------------------

class TestClassifySeverity:
    def test_minor(self):
        assert _classify_severity(0.31) == "minor"
        assert _classify_severity(-0.45) == "minor"

    def test_major(self):
        assert _classify_severity(0.50) == "major"
        assert _classify_severity(-0.65) == "major"

    def test_extreme(self):
        assert _classify_severity(0.70) == "extreme"
        assert _classify_severity(-1.0) == "extreme"


# ---------------------------------------------------------------------------
# Threshold detection
# ---------------------------------------------------------------------------

class TestThresholdDetection:
    def test_no_spike_below_threshold(self):
        det = _detector(threshold=0.3, window_minutes=60, cooldown_minutes=0)
        det.check_for_spikes({"BTC": 0.1})
        spikes = det.check_for_spikes({"BTC": 0.35})
        assert spikes == [], "Change of 0.25 should not trigger a spike (< 0.3 threshold)"

    def test_spike_at_threshold(self):
        det = _detector(threshold=0.3, window_minutes=60, cooldown_minutes=0)
        det.check_for_spikes({"BTC": 0.0})
        spikes = det.check_for_spikes({"BTC": 0.3})
        assert len(spikes) == 1
        assert spikes[0].asset == "BTC"

    def test_spike_above_threshold(self):
        det = _detector(threshold=0.3, window_minutes=60, cooldown_minutes=0)
        det.check_for_spikes({"BTC": -0.2})
        spikes = det.check_for_spikes({"BTC": 0.2})
        assert len(spikes) == 1
        assert spikes[0].change == pytest.approx(0.4, abs=1e-6)

    def test_negative_spike_detected(self):
        det = _detector(threshold=0.3, window_minutes=60, cooldown_minutes=0)
        det.check_for_spikes({"ETH": 0.5})
        spikes = det.check_for_spikes({"ETH": 0.1})
        assert len(spikes) == 1
        assert spikes[0].direction == "bearish"
        assert spikes[0].change == pytest.approx(-0.4, abs=1e-6)

    def test_multiple_assets(self):
        det = _detector(threshold=0.3, window_minutes=60, cooldown_minutes=0)
        det.check_for_spikes({"BTC": 0.0, "ETH": 0.0})
        spikes = det.check_for_spikes({"BTC": 0.5, "ETH": -0.35})
        assert len(spikes) == 2
        assets = {s.asset for s in spikes}
        assert assets == {"BTC", "ETH"}


# ---------------------------------------------------------------------------
# Direction and severity
# ---------------------------------------------------------------------------

class TestDirectionAndSeverity:
    def test_bullish_direction(self):
        det = _detector(threshold=0.3, window_minutes=60, cooldown_minutes=0)
        det.check_for_spikes({"BTC": 0.0})
        spikes = det.check_for_spikes({"BTC": 0.4})
        assert spikes[0].direction == "bullish"

    def test_bearish_direction(self):
        det = _detector(threshold=0.3, window_minutes=60, cooldown_minutes=0)
        det.check_for_spikes({"BTC": 0.5})
        spikes = det.check_for_spikes({"BTC": 0.1})
        assert spikes[0].direction == "bearish"

    def test_severity_minor(self):
        det = _detector(threshold=0.3, window_minutes=60, cooldown_minutes=0)
        det.check_for_spikes({"BTC": 0.0})
        spikes = det.check_for_spikes({"BTC": 0.35})
        assert spikes[0].severity == "minor"

    def test_severity_major(self):
        det = _detector(threshold=0.3, window_minutes=60, cooldown_minutes=0)
        det.check_for_spikes({"BTC": 0.0})
        spikes = det.check_for_spikes({"BTC": 0.55})
        assert spikes[0].severity == "major"

    def test_severity_extreme(self):
        det = _detector(threshold=0.3, window_minutes=60, cooldown_minutes=0)
        det.check_for_spikes({"BTC": -0.2})
        spikes = det.check_for_spikes({"BTC": 0.55})
        assert spikes[0].severity == "extreme"


# ---------------------------------------------------------------------------
# Cooldown behaviour
# ---------------------------------------------------------------------------

class TestCooldown:
    def test_duplicate_suppressed_during_cooldown(self):
        det = _detector(threshold=0.3, window_minutes=60, cooldown_minutes=30)
        det.check_for_spikes({"BTC": 0.0})
        spikes1 = det.check_for_spikes({"BTC": 0.5})
        assert len(spikes1) == 1, "First spike should fire"

        # Second spike with same direction within cooldown
        spikes2 = det.check_for_spikes({"BTC": 0.9})
        assert spikes2 == [], "Should be suppressed by cooldown"

    def test_spike_fires_after_cooldown_expires(self):
        det = _detector(threshold=0.3, window_minutes=60, cooldown_minutes=0)
        det.check_for_spikes({"BTC": 0.0})
        spikes1 = det.check_for_spikes({"BTC": 0.5})
        assert len(spikes1) == 1

        # cooldown_minutes=0 means cooldown_seconds=0; next call should fire again
        det.check_for_spikes({"BTC": 0.0})
        spikes2 = det.check_for_spikes({"BTC": 0.5})
        assert len(spikes2) == 1, "Should fire again after cooldown"

    def test_cooldown_is_per_asset(self):
        det = _detector(threshold=0.3, window_minutes=60, cooldown_minutes=30)
        det.check_for_spikes({"BTC": 0.0, "ETH": 0.0})
        det.check_for_spikes({"BTC": 0.5, "ETH": 0.0})  # BTC spikes, ETH doesn't

        # ETH spikes now — should not be affected by BTC cooldown
        spikes = det.check_for_spikes({"BTC": 0.9, "ETH": 0.5})
        eth_spikes = [s for s in spikes if s.asset == "ETH"]
        btc_spikes = [s for s in spikes if s.asset == "BTC"]
        assert len(eth_spikes) == 1, "ETH spike should fire (no ETH cooldown active)"
        assert btc_spikes == [], "BTC should be in cooldown"


# ---------------------------------------------------------------------------
# Spike history
# ---------------------------------------------------------------------------

class TestSpikeHistory:
    def test_get_recent_spikes_returns_within_window(self):
        det = _detector(threshold=0.3, window_minutes=60, cooldown_minutes=0)
        det.check_for_spikes({"BTC": 0.0})
        det.check_for_spikes({"BTC": 0.5})
        recent = det.get_recent_spikes(hours=24)
        assert len(recent) == 1
        assert recent[0].asset == "BTC"

    def test_get_recent_spikes_empty_when_none(self):
        det = _detector(threshold=0.3, window_minutes=60, cooldown_minutes=0)
        assert det.get_recent_spikes(hours=24) == []

    def test_sources_stored_on_spike(self):
        det = _detector(threshold=0.3, window_minutes=60, cooldown_minutes=0)
        det.check_for_spikes({"BTC": 0.0}, sources=["Reddit", "Fear&Greed"])
        spikes = det.check_for_spikes({"BTC": 0.5}, sources=["Reddit", "Fear&Greed"])
        assert spikes[0].sources_contributing == ["Reddit", "Fear&Greed"]


# ---------------------------------------------------------------------------
# Active cooldowns
# ---------------------------------------------------------------------------

class TestActiveCooldowns:
    def test_active_cooldown_listed(self):
        det = _detector(threshold=0.3, window_minutes=60, cooldown_minutes=30)
        det.check_for_spikes({"BTC": 0.0})
        det.check_for_spikes({"BTC": 0.5})
        cooldowns = det.get_active_cooldowns()
        assert len(cooldowns) == 1
        assert cooldowns[0]["asset"] == "BTC"
        assert cooldowns[0]["cooldown_remaining_seconds"] > 0

    def test_no_cooldown_before_first_spike(self):
        det = _detector(threshold=0.3, window_minutes=60, cooldown_minutes=30)
        assert det.get_active_cooldowns() == []


# ---------------------------------------------------------------------------
# get_config
# ---------------------------------------------------------------------------

class TestConfig:
    def test_returns_configured_values(self):
        det = SentimentSpikeDetector(
            spike_threshold=0.5,
            window_minutes=120,
            cooldown_minutes=15,
        )
        cfg = det.get_config()
        assert cfg["spike_threshold"] == 0.5
        assert cfg["window_minutes"] == 120
        assert cfg["cooldown_minutes"] == 15


# ---------------------------------------------------------------------------
# to_dict / format_alert
# ---------------------------------------------------------------------------

class TestSentimentSpikeDataclass:
    def _make_spike(self, direction="bullish", severity="major"):
        return SentimentSpike(
            asset="BTC",
            old_score=-0.4,
            new_score=0.2,
            change=0.6,
            direction=direction,
            severity=severity,
            timestamp=datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            sources_contributing=["Reddit", "Fear&Greed"],
        )

    def test_to_dict_keys(self):
        d = self._make_spike().to_dict()
        assert "asset" in d
        assert "old_score" in d
        assert "new_score" in d
        assert "change" in d
        assert "direction" in d
        assert "severity" in d
        assert "timestamp" in d
        assert "sources_contributing" in d

    def test_format_alert_bullish(self):
        msg = self._make_spike(direction="bullish", severity="major").format_alert()
        assert "BTC" in msg
        assert "BULLISH" in msg
        assert "MAJOR" in msg

    def test_format_alert_bearish(self):
        spike = SentimentSpike(
            asset="ETH",
            old_score=0.4,
            new_score=-0.2,
            change=-0.6,
            direction="bearish",
            severity="extreme",
            timestamp=datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        )
        msg = spike.format_alert()
        assert "BEARISH" in msg
        assert "EXTREME" in msg


# ---------------------------------------------------------------------------
# Notification dispatch integration
# ---------------------------------------------------------------------------

class TestNotificationDispatch:
    """Verify that spikes trigger NotificationManager.send_alert."""

    def test_spike_triggers_notification(self):
        det = _detector(threshold=0.3, window_minutes=60, cooldown_minutes=0)
        nm = NotificationManager(throttle_minutes=0)
        nm.start()

        mock_notifier = MagicMock()
        mock_notifier.is_available.return_value = True
        mock_notifier.send_alert.return_value = True
        nm.add_notifier("mock", mock_notifier)

        det.check_for_spikes({"BTC": 0.0})
        spikes = det.check_for_spikes({"BTC": 0.5})

        assert len(spikes) == 1
        spike = spikes[0]

        # Simulate what tv_gateway/main.py does
        nm.send_alert_sync(
            title=f"Sentiment Spike: {spike.asset}",
            message=spike.format_alert(),
            severity=Severity.WARNING,
            metadata=spike.to_dict(),
        )

        mock_notifier.send_alert.assert_called_once()
        call_kwargs = mock_notifier.send_alert.call_args
        assert "BTC" in call_kwargs[0][0]  # title contains asset name

        nm.stop()

    def test_no_notification_below_threshold(self):
        det = _detector(threshold=0.3, window_minutes=60, cooldown_minutes=0)
        nm = NotificationManager(throttle_minutes=0)
        nm.start()

        mock_notifier = MagicMock()
        mock_notifier.is_available.return_value = True
        nm.add_notifier("mock", mock_notifier)

        det.check_for_spikes({"BTC": 0.1})
        spikes = det.check_for_spikes({"BTC": 0.35})  # change = 0.25 < 0.3 threshold

        assert spikes == []
        mock_notifier.send_alert.assert_not_called()

        nm.stop()
