"""
Unit tests for EconomicCalendarFilter.
"""
from datetime import datetime, timedelta, timezone

import pytest

from bot.sentiment.economic_calendar import EconomicCalendarFilter


def _make_event(name: str, impact: str, offset_minutes: int = 0) -> dict:
    """Return an event dict with event_time = now + offset_minutes."""
    return {
        "name": name,
        "impact": impact,
        "event_time": datetime.now(timezone.utc) + timedelta(minutes=offset_minutes),
        "currency": "USD",
        "description": "",
    }


class TestEconomicCalendarFilter:
    def test_disabled_never_pauses(self):
        cal = EconomicCalendarFilter(
            enabled=False,
            _events=[_make_event("CPI", "HIGH", offset_minutes=0)],
        )
        assert cal.should_pause_trading() is False

    def test_high_impact_within_before_window(self):
        # Event is 15 minutes in the future, before-window is 30 minutes
        cal = EconomicCalendarFilter(
            enabled=True,
            pause_window_before_minutes=30,
            pause_window_after_minutes=15,
            min_impact="HIGH",
            _events=[_make_event("CPI", "HIGH", offset_minutes=15)],
        )
        assert cal.should_pause_trading() is True

    def test_high_impact_within_after_window(self):
        # Event was 10 minutes ago, after-window is 15 minutes
        cal = EconomicCalendarFilter(
            enabled=True,
            pause_window_before_minutes=30,
            pause_window_after_minutes=15,
            min_impact="HIGH",
            _events=[_make_event("FOMC", "HIGH", offset_minutes=-10)],
        )
        assert cal.should_pause_trading() is True

    def test_high_impact_outside_window(self):
        # Event is 120 minutes away, before-window is 30 minutes
        cal = EconomicCalendarFilter(
            enabled=True,
            pause_window_before_minutes=30,
            pause_window_after_minutes=15,
            min_impact="HIGH",
            _events=[_make_event("NFP", "HIGH", offset_minutes=120)],
        )
        assert cal.should_pause_trading() is False

    def test_low_impact_ignored_when_min_is_high(self):
        cal = EconomicCalendarFilter(
            enabled=True,
            min_impact="HIGH",
            _events=[_make_event("ISM Manufacturing", "LOW", offset_minutes=5)],
        )
        assert cal.should_pause_trading() is False

    def test_medium_impact_passes_medium_filter(self):
        cal = EconomicCalendarFilter(
            enabled=True,
            pause_window_before_minutes=30,
            pause_window_after_minutes=15,
            min_impact="MEDIUM",
            _events=[_make_event("Retail Sales", "MEDIUM", offset_minutes=10)],
        )
        assert cal.should_pause_trading() is True

    def test_get_upcoming_events_sorted(self):
        now = datetime.now(timezone.utc)
        events = [
            {"name": "NFP", "impact": "HIGH", "event_time": now + timedelta(hours=3), "currency": "USD", "description": ""},
            {"name": "CPI", "impact": "HIGH", "event_time": now + timedelta(hours=1), "currency": "USD", "description": ""},
        ]
        cal = EconomicCalendarFilter(enabled=True, _events=events)
        upcoming = cal.get_upcoming_events(hours=24)
        assert len(upcoming) == 2
        assert upcoming[0]["name"] == "CPI"
        assert upcoming[1]["name"] == "NFP"

    def test_get_upcoming_events_filters_past(self):
        now = datetime.now(timezone.utc)
        events = [
            {"name": "Past Event", "impact": "HIGH", "event_time": now - timedelta(hours=2), "currency": "USD", "description": ""},
            {"name": "Future Event", "impact": "HIGH", "event_time": now + timedelta(hours=1), "currency": "USD", "description": ""},
        ]
        cal = EconomicCalendarFilter(enabled=True, _events=events)
        upcoming = cal.get_upcoming_events(hours=24)
        assert len(upcoming) == 1
        assert upcoming[0]["name"] == "Future Event"

    def test_get_upcoming_events_disabled_returns_empty(self):
        cal = EconomicCalendarFilter(
            enabled=False,
            _events=[_make_event("CPI", "HIGH", offset_minutes=30)],
        )
        assert cal.get_upcoming_events() == []

    def test_get_event_impact(self):
        cal = EconomicCalendarFilter()
        event = {"name": "test", "impact": "HIGH"}
        assert cal.get_event_impact(event) == "HIGH"

    def test_minutes_until_in_upcoming(self):
        cal = EconomicCalendarFilter(
            enabled=True,
            _events=[_make_event("CPI", "HIGH", offset_minutes=45)],
        )
        upcoming = cal.get_upcoming_events(hours=2)
        assert len(upcoming) == 1
        assert 40 <= upcoming[0]["minutes_until"] <= 50

    def test_invalid_min_impact_raises(self):
        with pytest.raises(ValueError):
            EconomicCalendarFilter(min_impact="CRITICAL")
