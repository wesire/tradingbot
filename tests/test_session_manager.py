"""
Unit tests for SessionManager.
"""
from datetime import datetime, timezone

import pytest

from bot.strategy.session_manager import SessionManager


def _utc(hour: int, weekday: int = 1) -> datetime:
    """Create a UTC datetime with given hour and weekday (0=Mon, 6=Sun)."""
    # Find a reference Monday 2025-01-06
    base = datetime(2025, 1, 6, tzinfo=timezone.utc)  # Monday
    # Move to desired weekday
    delta_days = weekday - base.weekday()
    day = base.replace(hour=hour, minute=0, second=0, microsecond=0)
    from datetime import timedelta
    return day + timedelta(days=delta_days)


class TestSessionManager:
    def test_asian_session(self):
        mgr = SessionManager()
        # 04:00 UTC Monday → Asian
        dt = _utc(hour=4, weekday=0)
        session = mgr.get_current_session(at_time=dt)
        assert "asian" in session["active_sessions"]

    def test_london_session(self):
        mgr = SessionManager()
        # 10:00 UTC Monday → London only
        dt = _utc(hour=10, weekday=0)
        session = mgr.get_current_session(at_time=dt)
        assert "london" in session["active_sessions"]

    def test_new_york_session(self):
        mgr = SessionManager()
        # 18:00 UTC Monday → NY only
        dt = _utc(hour=18, weekday=0)
        session = mgr.get_current_session(at_time=dt)
        assert "new_york" in session["active_sessions"]

    def test_london_new_york_overlap(self):
        mgr = SessionManager()
        # 14:00 UTC → both London and NY active
        dt = _utc(hour=14, weekday=0)
        session = mgr.get_current_session(at_time=dt)
        assert "london" in session["active_sessions"]
        assert "new_york" in session["active_sessions"]

    def test_weekend_multiplier(self):
        mgr = SessionManager(weekend_multiplier=0.5)
        # Saturday = weekday 5
        dt = _utc(hour=12, weekday=5)
        multiplier = mgr.get_session_multiplier(at_time=dt)
        assert multiplier == pytest.approx(0.5)

    def test_weekend_trading_disabled(self):
        mgr = SessionManager(weekend_trading_enabled=False)
        dt = _utc(hour=12, weekday=6)  # Sunday
        assert mgr.should_trade(at_time=dt) is False

    def test_weekday_trading_enabled(self):
        mgr = SessionManager(weekend_trading_enabled=False)
        dt = _utc(hour=10, weekday=1)  # Tuesday London
        assert mgr.should_trade(at_time=dt) is True

    def test_multiplier_in_range(self):
        mgr = SessionManager()
        for hour in range(24):
            dt = _utc(hour=hour, weekday=2)
            m = mgr.get_session_multiplier(at_time=dt)
            assert 0.0 <= m <= 1.0

    def test_preferred_style_london(self):
        mgr = SessionManager()
        # 10:00 UTC Monday → London → breakout
        dt = _utc(hour=10, weekday=0)
        style = mgr.get_preferred_strategy_style(at_time=dt)
        # London multiplier = 1.0, New York not active yet → london wins
        assert style in ("breakout", "momentum", "mean_reversion")

    def test_preferred_style_new_york(self):
        mgr = SessionManager()
        # 18:00 UTC → NY only → momentum
        dt = _utc(hour=18, weekday=0)
        style = mgr.get_preferred_strategy_style(at_time=dt)
        assert style == "momentum"

    def test_weekend_style_mean_reversion(self):
        mgr = SessionManager(weekend_multiplier=0.5)
        dt = _utc(hour=14, weekday=5)  # Saturday
        session = mgr.get_current_session(at_time=dt)
        assert session["style"] == "mean_reversion"

    def test_get_current_session_has_required_keys(self):
        mgr = SessionManager()
        session = mgr.get_current_session()
        for key in ("name", "multiplier", "style", "description", "is_weekend", "active_sessions"):
            assert key in session
