"""
Session-aware trading: identifies current forex/crypto session and provides
position-size multipliers and preferred strategy styles.

Sessions:
    Asian   00:00–08:00 UTC — low volatility → mean reversion preferred
    London  08:00–16:00 UTC — high volatility → breakout / trend preferred
    New York 13:00–21:00 UTC — highest volatility → momentum preferred
    Weekend  Sat–Sun         — thin liquidity → reduced sizing or no trading

London and New York overlap 13:00–16:00 UTC and are both active; the higher
of the two multipliers is applied.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# Session definitions: (start_hour, end_hour, multiplier, style)
_SESSIONS: Dict[str, Dict[str, Any]] = {
    "asian": {
        "start_utc": 0,
        "end_utc": 8,
        "multiplier": 0.7,
        "style": "mean_reversion",
        "description": "Asian session (00:00–08:00 UTC) — low volatility",
    },
    "london": {
        "start_utc": 8,
        "end_utc": 16,
        "multiplier": 1.0,
        "style": "breakout",
        "description": "London session (08:00–16:00 UTC) — high volatility",
    },
    "new_york": {
        "start_utc": 13,
        "end_utc": 21,
        "multiplier": 1.0,
        "style": "momentum",
        "description": "New York session (13:00–21:00 UTC) — highest volatility",
    },
    "off_hours": {
        "start_utc": 21,
        "end_utc": 24,
        "multiplier": 0.5,
        "style": "mean_reversion",
        "description": "Off hours (21:00–00:00 UTC) — low activity",
    },
}

_WEEKEND_MULTIPLIER = 0.5


class SessionManager:
    """
    Determines the current trading session and associated parameters.

    Multiple sessions can be active simultaneously (e.g. London/NY overlap).
    In that case the session with the highest multiplier takes precedence.

    Attributes:
        SESSIONS: Dict of all supported sessions.
    """

    SESSIONS = _SESSIONS

    def __init__(
        self,
        weekend_multiplier: float = _WEEKEND_MULTIPLIER,
        weekend_trading_enabled: bool = True,
    ) -> None:
        """
        Initialise the session manager.

        Args:
            weekend_multiplier: Position size multiplier applied on Sat/Sun.
            weekend_trading_enabled: If False, ``get_session_multiplier``
                returns 0.0 on weekends (effectively pauses trading).
        """
        self.weekend_multiplier = weekend_multiplier
        self.weekend_trading_enabled = weekend_trading_enabled
        logger.info(
            "Initialized SessionManager "
            "(weekend_multiplier=%.2f, weekend_trading=%s)",
            weekend_multiplier,
            weekend_trading_enabled,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_weekend(dt: datetime) -> bool:
        """Return True if the given UTC datetime falls on a weekend."""
        return dt.weekday() >= 5  # Saturday=5, Sunday=6

    @staticmethod
    def _get_active_sessions(hour: int) -> list:
        """Return list of session names active at the given UTC hour."""
        active = []
        for name, cfg in _SESSIONS.items():
            if cfg["start_utc"] <= hour < cfg["end_utc"]:
                active.append(name)
        return active

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def get_current_session(
        self,
        at_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Return the current (or dominant) session and its characteristics.

        When multiple sessions overlap, the one with the highest multiplier
        is returned.

        Args:
            at_time: UTC datetime to evaluate (defaults to now).

        Returns:
            Dict with keys: ``name``, ``multiplier``, ``style``,
            ``description``, ``is_weekend``, ``active_sessions``.
        """
        now = at_time or datetime.now(timezone.utc)
        hour = now.hour
        is_weekend = self._is_weekend(now)

        active_names = self._get_active_sessions(hour)

        if not active_names:
            active_names = ["off_hours"]

        # Pick session with highest multiplier
        best_session_name = max(
            active_names,
            key=lambda n: _SESSIONS.get(n, {}).get("multiplier", 0.0),
        )
        best_session = dict(_SESSIONS.get(best_session_name, _SESSIONS["off_hours"]))
        best_session["name"] = best_session_name
        best_session["is_weekend"] = is_weekend
        best_session["active_sessions"] = active_names

        if is_weekend:
            best_session["multiplier"] = (
                self.weekend_multiplier if self.weekend_trading_enabled else 0.0
            )
            best_session["style"] = "mean_reversion"
            best_session["description"] = (
                f"Weekend — thin liquidity (multiplier={best_session['multiplier']})"
            )

        return best_session

    def get_session_multiplier(
        self,
        at_time: Optional[datetime] = None,
    ) -> float:
        """
        Return the position size multiplier for the current session.

        Args:
            at_time: UTC datetime to evaluate (defaults to now).

        Returns:
            Float multiplier (0.0 = no trading, 1.0 = full sizing).
        """
        return float(self.get_current_session(at_time)["multiplier"])

    def get_preferred_strategy_style(
        self,
        at_time: Optional[datetime] = None,
    ) -> str:
        """
        Return the preferred strategy style for the current session.

        Args:
            at_time: UTC datetime to evaluate (defaults to now).

        Returns:
            One of ``"mean_reversion"``, ``"breakout"``, or ``"momentum"``.
        """
        return str(self.get_current_session(at_time)["style"])

    def should_trade(
        self,
        at_time: Optional[datetime] = None,
    ) -> bool:
        """
        Return True if trading is permitted in the current session.

        Trading is blocked on weekends when ``weekend_trading_enabled=False``.

        Args:
            at_time: UTC datetime to evaluate (defaults to now).

        Returns:
            bool.
        """
        return self.get_session_multiplier(at_time) > 0.0
