"""
Sentiment spike detector – monitors sentiment scores over a sliding window
and emits ``SentimentSpike`` events when significant changes are detected.
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Deque, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Severity thresholds
# ---------------------------------------------------------------------------
_SEVERITY_MINOR = 0.3   # default spike_threshold
_SEVERITY_MAJOR = 0.5
_SEVERITY_EXTREME = 0.7


def _classify_severity(change: float) -> str:
    abs_change = abs(change)
    if abs_change >= _SEVERITY_EXTREME:
        return "extreme"
    if abs_change >= _SEVERITY_MAJOR:
        return "major"
    return "minor"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SentimentSpike:
    """Represents a detected sentiment spike for a single asset."""

    asset: str
    old_score: float
    new_score: float
    change: float
    direction: str          # "bullish" | "bearish"
    severity: str           # "minor" | "major" | "extreme"
    timestamp: datetime
    sources_contributing: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "asset": self.asset,
            "old_score": round(self.old_score, 4),
            "new_score": round(self.new_score, 4),
            "change": round(self.change, 4),
            "direction": self.direction,
            "severity": self.severity,
            "timestamp": self.timestamp.isoformat(),
            "sources_contributing": self.sources_contributing,
        }

    def format_alert(self) -> str:
        """Return a human-readable alert message."""
        emoji = "🚨" if self.severity == "extreme" else ("⚠️" if self.severity == "major" else "ℹ️")
        sources_str = ", ".join(self.sources_contributing) if self.sources_contributing else "Unknown"
        return (
            f"{emoji} {self.asset} Sentiment Spike: "
            f"{self.old_score:+.2f} → {self.new_score:+.2f} "
            f"({self.direction.upper()}) | "
            f"Sources: {sources_str} | "
            f"Severity: {self.severity.upper()}"
        )


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------

class SentimentSpikeDetector:
    """
    Monitors sentiment scores over a sliding window and detects spikes.

    Parameters
    ----------
    spike_threshold:
        Minimum absolute score change within the window to trigger a spike
        (default 0.3 on the -1…+1 scale).
    window_minutes:
        Width of the sliding window in minutes (default 60).
    cooldown_minutes:
        Minimum time between successive alerts for the *same* asset
        (default 30).
    max_history:
        Maximum number of recent spikes to keep in memory.
    """

    def __init__(
        self,
        spike_threshold: float = 0.3,
        window_minutes: int = 60,
        cooldown_minutes: int = 30,
        max_history: int = 200,
    ) -> None:
        self.spike_threshold = spike_threshold
        self.window_seconds = window_minutes * 60
        self.cooldown_seconds = cooldown_minutes * 60
        self.max_history = max_history

        # score_history[asset] = deque of (monotonic_timestamp, score)
        self._score_history: Dict[str, Deque[Tuple[float, float]]] = defaultdict(
            lambda: deque(maxlen=1_000)
        )
        # last_alert_time[asset] = monotonic timestamp of last spike alert
        self._last_alert_time: Dict[str, float] = {}

        # Full spike history (capped at max_history)
        self._spike_history: Deque[SentimentSpike] = deque(maxlen=max_history)

        logger.info(
            "SentimentSpikeDetector initialised: threshold=%.2f "
            "window=%dm cooldown=%dm",
            spike_threshold,
            window_minutes,
            cooldown_minutes,
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def check_for_spikes(
        self,
        current_scores: Dict[str, float],
        sources: Optional[List[str]] = None,
    ) -> List[SentimentSpike]:
        """
        Record current scores and return any newly detected spikes.

        Parameters
        ----------
        current_scores:
            Mapping of asset → current sentiment score (-1…+1).
        sources:
            Human-readable list of provider names that contributed to
            these scores (for inclusion in spike messages).

        Returns
        -------
        List[SentimentSpike]
            Zero or more newly detected spikes (may be empty).
        """
        now_mono = time.monotonic()
        now_wall = datetime.now(timezone.utc)
        sources = sources or []
        spikes: List[SentimentSpike] = []

        for asset, new_score in current_scores.items():
            # Record new reading
            self._score_history[asset].append((now_mono, new_score))

            # Trim readings outside the window
            cutoff = now_mono - self.window_seconds
            history = self._score_history[asset]
            while history and history[0][0] < cutoff:
                history.popleft()

            if len(history) < 2:
                continue  # Not enough data yet

            # Find the oldest score still inside the window
            old_score = history[0][1]
            change = new_score - old_score

            if abs(change) < self.spike_threshold:
                continue  # Change too small

            # Apply per-asset cooldown
            if self._is_in_cooldown(asset, now_mono):
                logger.debug(
                    "Spike suppressed for %s (in cooldown) – change=%.3f",
                    asset,
                    change,
                )
                continue

            direction = "bullish" if change > 0 else "bearish"
            severity = _classify_severity(change)

            spike = SentimentSpike(
                asset=asset,
                old_score=old_score,
                new_score=new_score,
                change=change,
                direction=direction,
                severity=severity,
                timestamp=now_wall,
                sources_contributing=list(sources),
            )
            spikes.append(spike)
            self._spike_history.append(spike)
            self._last_alert_time[asset] = now_mono
            logger.info("Sentiment spike detected: %s", spike.format_alert())

        return spikes

    def get_recent_spikes(self, hours: int = 24) -> List[SentimentSpike]:
        """Return spikes detected within the last *hours* hours."""
        cutoff = time.monotonic() - hours * 3600
        # Correlate wall-clock with monotonic by offsetting
        # We rely on wall-clock timestamps stored on the spike object.
        from datetime import timedelta
        cutoff_wall = datetime.now(timezone.utc) - timedelta(hours=hours)
        return [s for s in self._spike_history if s.timestamp >= cutoff_wall]

    def get_active_cooldowns(self) -> List[Dict]:
        """Return assets currently in a spike-alert cooldown."""
        now = time.monotonic()
        result = []
        for asset, last_t in self._last_alert_time.items():
            remaining = self.cooldown_seconds - (now - last_t)
            if remaining > 0:
                result.append({
                    "asset": asset,
                    "cooldown_remaining_seconds": round(remaining),
                })
        return result

    def get_config(self) -> Dict:
        """Return current detector configuration."""
        return {
            "spike_threshold": self.spike_threshold,
            "window_minutes": self.window_seconds // 60,
            "cooldown_minutes": self.cooldown_seconds // 60,
            "max_history": self.max_history,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _is_in_cooldown(self, asset: str, now_mono: float) -> bool:
        last = self._last_alert_time.get(asset)
        if last is None:
            return False
        return (now_mono - last) < self.cooldown_seconds
