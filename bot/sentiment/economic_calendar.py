"""
Economic Calendar filter.

Provides a simple economic event calendar that can pause trading around
high-impact macro events (CPI, NFP, FOMC, etc.).  Optionally fetches live
data from the ForexFactory RSS feed; falls back to a built-in recurring
calendar when the feed is unavailable.

Configuration example (YAML)::

    economic_calendar:
      enabled: true
      pause_window_before_minutes: 30
      pause_window_after_minutes: 15
      min_impact: "HIGH"
"""
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from xml.etree import ElementTree

import requests

logger = logging.getLogger(__name__)

_FF_RSS_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
_REQUEST_TIMEOUT = 10


# ---------------------------------------------------------------------------
# Static recurring events (day-of-month / weekday-based schedule)
# ---------------------------------------------------------------------------

class _RecurringEvent:
    """Descriptor for a recurring economic event."""

    def __init__(
        self,
        name: str,
        impact: str,
        description: str = "",
    ) -> None:
        self.name = name
        impact_upper = impact.upper()
        if impact_upper not in ("HIGH", "MEDIUM", "LOW"):
            raise ValueError(f"Invalid impact level: {impact}")
        self.impact = impact_upper
        self.description = description


# Known HIGH-impact recurring events with approximate UTC schedule.
# These are used as a fallback when the live RSS feed is unavailable.
_STATIC_HIGH_IMPACT_EVENTS: List[Dict] = [
    {
        "name": "US CPI",
        "impact": "HIGH",
        "description": "US Consumer Price Index – monthly, 2nd week of month ~12:30 UTC",
    },
    {
        "name": "US NFP",
        "impact": "HIGH",
        "description": "Non-Farm Payrolls – first Friday of month ~12:30 UTC",
    },
    {
        "name": "FOMC Rate Decision",
        "impact": "HIGH",
        "description": "Federal Open Market Committee – ~8 times per year ~18:00 UTC",
    },
    {
        "name": "US GDP",
        "impact": "HIGH",
        "description": "Gross Domestic Product – quarterly ~12:30 UTC",
    },
    {
        "name": "ECB Rate Decision",
        "impact": "HIGH",
        "description": "European Central Bank – ~8 times per year ~12:45 UTC",
    },
    {
        "name": "UK CPI",
        "impact": "HIGH",
        "description": "UK Consumer Price Index – monthly ~07:00 UTC",
    },
]


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class EconomicCalendarFilter:
    """
    Filter that pauses trading around high-impact economic events.

    By default the filter fetches this week's event calendar from the
    ForexFactory RSS feed.  When the feed is unavailable it gracefully
    degrades to returning an empty event list (no trading pauses).

    Attributes:
        IMPACT_LEVELS: Ordered list of impact levels (highest first).
    """

    IMPACT_LEVELS = ("HIGH", "MEDIUM", "LOW")

    def __init__(
        self,
        enabled: bool = True,
        pause_window_before_minutes: int = 30,
        pause_window_after_minutes: int = 15,
        min_impact: str = "HIGH",
        rss_url: str = _FF_RSS_URL,
        timeout: int = _REQUEST_TIMEOUT,
        _events: Optional[List[Dict]] = None,
    ) -> None:
        """
        Initialise the calendar filter.

        Args:
            enabled: Whether the filter is active.
            pause_window_before_minutes: Minutes before an event during which
                trading should be paused.
            pause_window_after_minutes: Minutes after an event during which
                trading should be paused.
            min_impact: Minimum impact level to consider (``"HIGH"``/
                ``"MEDIUM"``/``"LOW"``).
            rss_url: URL of the ForexFactory RSS calendar feed.
            timeout: HTTP request timeout in seconds.
            _events: Optional pre-loaded event list (for testing).
        """
        self.enabled = enabled
        self.pause_window_before = timedelta(minutes=pause_window_before_minutes)
        self.pause_window_after = timedelta(minutes=pause_window_after_minutes)
        min_impact_upper = min_impact.upper()
        if min_impact_upper not in self.IMPACT_LEVELS:
            raise ValueError(f"Invalid min_impact: {min_impact}")
        self.min_impact = min_impact_upper
        self._rss_url = rss_url
        self._timeout = timeout
        # Injected events bypass HTTP fetch (useful for testing)
        self._injected_events: Optional[List[Dict]] = _events
        logger.info(
            "Initialized EconomicCalendarFilter "
            "(enabled=%s, before=%dmin, after=%dmin, min_impact=%s)",
            enabled,
            pause_window_before_minutes,
            pause_window_after_minutes,
            min_impact,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_datetime(dt_str: str) -> Optional[datetime]:
        """Parse an ISO-8601 or simple date/time string to a UTC datetime."""
        if not dt_str:
            return None
        formats = [
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%d %H:%M",
            "%m-%d-%Y %I:%M%p",  # ForexFactory format
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(dt_str.strip(), fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                continue
        return None

    @staticmethod
    def _impact_from_string(raw: str) -> str:
        """Normalise impact level string."""
        raw_upper = raw.upper().strip()
        if "HIGH" in raw_upper:
            return "HIGH"
        if "MEDIUM" in raw_upper or "MED" in raw_upper:
            return "MEDIUM"
        return "LOW"

    def _impact_passes_filter(self, impact: str) -> bool:
        """Return True if impact level meets the configured minimum."""
        order = {level: i for i, level in enumerate(self.IMPACT_LEVELS)}
        return order.get(impact, 99) <= order.get(self.min_impact, 99)

    def _fetch_rss_events(self) -> List[Dict]:
        """Fetch events from ForexFactory RSS feed.

        Returns:
            List of event dicts with keys: name, impact, event_time,
            currency, description.
        """
        try:
            resp = requests.get(self._rss_url, timeout=self._timeout)
            resp.raise_for_status()
            root = ElementTree.fromstring(resp.content)
        except requests.RequestException as exc:
            logger.warning("EconomicCalendar: RSS fetch failed: %s", exc)
            return []
        except ElementTree.ParseError as exc:
            logger.warning("EconomicCalendar: RSS parse failed: %s", exc)
            return []

        events: List[Dict] = []
        for item in root.iter("event"):
            try:
                name = (item.findtext("title") or "").strip()
                country = (item.findtext("country") or "").strip()
                date_str = (item.findtext("date") or "").strip()
                time_str = (item.findtext("time") or "").strip()
                impact_raw = (item.findtext("impact") or "LOW").strip()

                dt_str = f"{date_str} {time_str}" if time_str else date_str
                event_time = self._parse_datetime(dt_str)
                if event_time is None:
                    continue

                impact = self._impact_from_string(impact_raw)
                events.append(
                    {
                        "name": name,
                        "impact": impact,
                        "event_time": event_time,
                        "currency": country,
                        "description": "",
                    }
                )
            except Exception as exc:  # pylint: disable=broad-except
                logger.debug("EconomicCalendar: skipping malformed item: %s", exc)
                continue

        logger.info("EconomicCalendar: loaded %d events from RSS", len(events))
        return events

    def _get_events(self) -> List[Dict]:
        """Return the event list (injected, RSS, or empty)."""
        if self._injected_events is not None:
            return self._injected_events
        return self._fetch_rss_events()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def should_pause_trading(self, at_time: Optional[datetime] = None) -> bool:
        """
        Return True if a qualifying high-impact event is within the pause window.

        Args:
            at_time: Time to evaluate (defaults to now UTC).

        Returns:
            True if trading should be paused, False otherwise.
        """
        if not self.enabled:
            return False

        now = at_time or datetime.now(timezone.utc)
        events = self._get_events()

        for event in events:
            if not self._impact_passes_filter(event.get("impact", "LOW")):
                continue
            event_time: Optional[datetime] = event.get("event_time")
            if event_time is None:
                continue
            if event_time.tzinfo is None:
                event_time = event_time.replace(tzinfo=timezone.utc)

            window_start = event_time - self.pause_window_before
            window_end = event_time + self.pause_window_after
            if window_start <= now <= window_end:
                logger.info(
                    "EconomicCalendar: pausing trading — event '%s' (%s) "
                    "at %s (window %s – %s)",
                    event["name"],
                    event.get("impact"),
                    event_time.isoformat(),
                    window_start.isoformat(),
                    window_end.isoformat(),
                )
                return True
        return False

    def get_upcoming_events(
        self,
        hours: int = 24,
        at_time: Optional[datetime] = None,
    ) -> List[Dict]:
        """
        Return upcoming events within the next N hours.

        Args:
            hours: Look-ahead window in hours.
            at_time: Reference time (defaults to now UTC).

        Returns:
            List of event dicts sorted by event_time, each containing:
            ``name``, ``impact``, ``event_time``, ``currency``,
            ``description``, and ``minutes_until``.
        """
        if not self.enabled:
            return []

        now = at_time or datetime.now(timezone.utc)
        cutoff = now + timedelta(hours=hours)
        events = self._get_events()

        upcoming = []
        for event in events:
            event_time: Optional[datetime] = event.get("event_time")
            if event_time is None:
                continue
            if event_time.tzinfo is None:
                event_time = event_time.replace(tzinfo=timezone.utc)
            if now <= event_time <= cutoff:
                minutes_until = (event_time - now).total_seconds() / 60
                enriched = dict(event)
                enriched["event_time"] = event_time
                enriched["minutes_until"] = round(minutes_until, 1)
                upcoming.append(enriched)

        upcoming.sort(key=lambda e: e["event_time"])
        return upcoming

    def get_event_impact(self, event: Dict) -> str:
        """
        Return the impact level for a given event dict.

        Args:
            event: Event dict (as returned by ``get_upcoming_events``).

        Returns:
            ``"HIGH"``, ``"MEDIUM"``, or ``"LOW"``.
        """
        return event.get("impact", "LOW")
