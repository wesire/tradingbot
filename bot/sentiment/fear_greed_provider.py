"""
Fear & Greed Index sentiment provider.

Integrates with the Alternative.me Fear & Greed Index API to fetch the
current and historical sentiment index values (0-100) and maps them to a
normalised sentiment score in [-1, 1].

No API key is required.  Results are cached for 1 hour because the index
updates only once per day.

Score mapping:
    0-25   Extreme Fear   → -1.0 to -0.5
    25-45  Fear           → -0.5 to -0.2
    45-55  Neutral        → -0.2 to  0.2
    55-75  Greed          →  0.2 to  0.5
    75-100 Extreme Greed  →  0.5 to  1.0
"""
import logging
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import requests
from cachetools import TTLCache

from .provider import SentimentData, SentimentProvider

logger = logging.getLogger(__name__)

_API_URL = "https://api.alternative.me/fng/"
_CACHE_TTL = 3600  # 1 hour – the index updates once per day
_REQUEST_TIMEOUT = 10


def _map_fng_to_score(value: int) -> float:
    """Map a Fear & Greed value (0-100) to a normalised score [-1, 1].

    The mapping uses linear interpolation within each named zone:

    +-----------+-------+-------------------+
    | Zone      | Range | Score range       |
    +-----------+-------+-------------------+
    | E. Fear   | 0-25  | -1.0  to  -0.5   |
    | Fear      | 25-45 | -0.5  to  -0.2   |
    | Neutral   | 45-55 | -0.2  to   0.2   |
    | Greed     | 55-75 |  0.2  to   0.5   |
    | E. Greed  | 75-100|  0.5  to   1.0   |
    +-----------+-------+-------------------+
    """
    # Clamp to valid range
    v = max(0, min(100, value))

    zones: List[Tuple[int, int, float, float]] = [
        (0, 25, -1.0, -0.5),
        (25, 45, -0.5, -0.2),
        (45, 55, -0.2, 0.2),
        (55, 75, 0.2, 0.5),
        (75, 100, 0.5, 1.0),
    ]
    for low, high, score_low, score_high in zones:
        if low <= v <= high:
            if high == low:
                return score_low
            t = (v - low) / (high - low)
            return round(score_low + t * (score_high - score_low), 4)
    # Fallback (should never happen after clamping)
    return 0.0


def _classification_from_value(value: int) -> str:
    """Return the human-readable classification for a Fear & Greed value."""
    if value <= 25:
        return "Extreme Fear"
    if value <= 45:
        return "Fear"
    if value <= 55:
        return "Neutral"
    if value <= 75:
        return "Greed"
    return "Extreme Greed"


class FearGreedProvider(SentimentProvider):
    """
    Sentiment provider backed by the Alternative.me Fear & Greed Index.

    The Fear & Greed Index is a macro sentiment signal that captures overall
    market psychology.  It is asset-agnostic: the same score is applied to
    all requested crypto assets because the index measures the crypto market
    as a whole.

    Attributes:
        API_URL: Alternative.me Fear & Greed Index endpoint.
        DEFAULT_CACHE_TTL: Seconds to cache results (3600 s = 1 hour).
        REGIME_THRESHOLDS: Index values at which trading should be gated.
    """

    API_URL = _API_URL
    DEFAULT_CACHE_TTL = _CACHE_TTL

    # Configurable regime-gate thresholds (class defaults, can be overridden)
    EXTREME_FEAR_THRESHOLD = 25   # Pause or restrict long entries below this
    EXTREME_GREED_THRESHOLD = 75  # Pause or restrict short entries above this

    def __init__(
        self,
        cache_ttl: int = DEFAULT_CACHE_TTL,
        extreme_fear_threshold: int = EXTREME_FEAR_THRESHOLD,
        extreme_greed_threshold: int = EXTREME_GREED_THRESHOLD,
        timeout: int = _REQUEST_TIMEOUT,
    ) -> None:
        """
        Initialise the provider.

        Args:
            cache_ttl: Cache time-to-live in seconds.
            extreme_fear_threshold: Index values at or below this are treated
                as Extreme Fear; can be used to pause long entries.
            extreme_greed_threshold: Index values at or above this are treated
                as Extreme Greed; can be used to pause short entries.
            timeout: HTTP request timeout in seconds.
        """
        self._cache: TTLCache = TTLCache(maxsize=4, ttl=cache_ttl)
        self.extreme_fear_threshold = extreme_fear_threshold
        self.extreme_greed_threshold = extreme_greed_threshold
        self._timeout = timeout
        logger.info(
            "Initialized FearGreedProvider (cache_ttl=%ds, "
            "fear_gate=%d, greed_gate=%d)",
            cache_ttl,
            extreme_fear_threshold,
            extreme_greed_threshold,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch_fng(self, limit: int = 1) -> List[Dict]:
        """Fetch Fear & Greed data from the API.

        Args:
            limit: Number of historical data points to retrieve (1 = today).

        Returns:
            List of raw data dicts from the API response.

        Raises:
            requests.RequestException: On network or HTTP errors.
        """
        cache_key = f"fng_{limit}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        params = {"limit": limit, "format": "json", "date_format": "us"}
        resp = requests.get(
            self.API_URL,
            params=params,
            timeout=self._timeout,
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
        self._cache[cache_key] = data
        return data

    @staticmethod
    def _to_sentiment_data(asset: str, entry: Dict) -> SentimentData:
        """Convert a single API entry to a SentimentData object."""
        try:
            value = int(entry.get("value", 50))
        except (TypeError, ValueError):
            value = 50

        score = _map_fng_to_score(value)
        classification = entry.get("value_classification") or _classification_from_value(value)

        # Parse timestamp
        ts_raw = entry.get("timestamp")
        if ts_raw:
            try:
                ts = datetime.fromtimestamp(float(ts_raw), tz=timezone.utc)
            except (TypeError, ValueError, OSError):
                ts = datetime.now(timezone.utc)
        else:
            ts = datetime.now(timezone.utc)

        return SentimentData(
            asset=asset,
            score=score,
            confidence=0.85,  # Index is a well-established signal
            headline=f"Fear & Greed Index: {value} ({classification})",
            source="alternative.me/fng",
            timestamp=ts,
        )

    # ------------------------------------------------------------------
    # SentimentProvider interface
    # ------------------------------------------------------------------

    def get_sentiment(
        self,
        asset: str,
        lookback_hours: int = 24,
    ) -> List[SentimentData]:
        """
        Return Fear & Greed sentiment for the given asset.

        Because the index is market-wide, the same value is returned
        regardless of the requested asset.

        Args:
            asset: Asset symbol (e.g. "BTC").  Not used for the API call
                but stored in returned SentimentData objects.
            lookback_hours: Number of past hours to cover.  Translated to
                a number of historical daily data points (max 30).

        Returns:
            List of SentimentData with one entry per available day.
        """
        limit = max(1, min(30, lookback_hours // 24 + 1))
        try:
            entries = self._fetch_fng(limit=limit)
        except requests.RequestException as exc:
            logger.error("FearGreedProvider: API error: %s", exc)
            return []
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("FearGreedProvider: unexpected error: %s", exc)
            return []

        results = [self._to_sentiment_data(asset, e) for e in entries]
        logger.debug(
            "FearGreedProvider: fetched %d entries for %s",
            len(results),
            asset,
        )
        return results

    def get_multi_asset_sentiment(
        self,
        assets: List[str],
        lookback_hours: int = 24,
    ) -> Dict[str, List[SentimentData]]:
        """
        Return Fear & Greed sentiment for multiple assets.

        The same macro index is used for every asset; individual lists share
        the same underlying data.

        Args:
            assets: List of asset symbols.
            lookback_hours: Number of past hours to cover.

        Returns:
            Dict mapping each asset to a list of SentimentData.
        """
        limit = max(1, min(30, lookback_hours // 24 + 1))
        try:
            entries = self._fetch_fng(limit=limit)
        except requests.RequestException as exc:
            logger.error("FearGreedProvider: API error: %s", exc)
            return {a: [] for a in assets}
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("FearGreedProvider: unexpected error: %s", exc)
            return {a: [] for a in assets}

        result: Dict[str, List[SentimentData]] = {}
        for asset in assets:
            result[asset] = [self._to_sentiment_data(asset, e) for e in entries]
        return result

    # ------------------------------------------------------------------
    # Regime-gate helpers
    # ------------------------------------------------------------------

    def get_current_value(self) -> Optional[int]:
        """Return the most recent Fear & Greed index value (0-100).

        Returns:
            Integer value or None if the API call failed.
        """
        try:
            entries = self._fetch_fng(limit=1)
            if entries:
                return int(entries[0].get("value", 50))
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("FearGreedProvider.get_current_value error: %s", exc)
        return None

    def get_current_score(self) -> Optional[float]:
        """Return the current normalised score in [-1, 1].

        Returns:
            Float score or None if the API call failed.
        """
        value = self.get_current_value()
        if value is None:
            return None
        return _map_fng_to_score(value)

    def is_extreme_fear(self) -> bool:
        """Return True if the index is in the Extreme Fear zone.

        Can be used as a regime gate: pause long entries when True.
        """
        value = self.get_current_value()
        if value is None:
            return False
        return value <= self.extreme_fear_threshold

    def is_extreme_greed(self) -> bool:
        """Return True if the index is in the Extreme Greed zone.

        Can be used as a regime gate: pause short entries when True.
        """
        value = self.get_current_value()
        if value is None:
            return False
        return value >= self.extreme_greed_threshold

    def should_pause_longs(self) -> bool:
        """Return True if current sentiment suggests pausing long entries."""
        return self.is_extreme_fear()

    def should_pause_shorts(self) -> bool:
        """Return True if current sentiment suggests pausing short entries."""
        return self.is_extreme_greed()

    def get_historical_values(self, days: int = 30) -> List[Dict]:
        """
        Return historical Fear & Greed values for the past N days.

        Args:
            days: Number of historical days to retrieve (max 30).

        Returns:
            List of dicts with keys ``value``, ``classification``,
            ``timestamp``, and ``score``.
        """
        limit = max(1, min(30, days))
        try:
            entries = self._fetch_fng(limit=limit)
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("FearGreedProvider.get_historical_values error: %s", exc)
            return []

        results = []
        for e in entries:
            try:
                value = int(e.get("value", 50))
            except (TypeError, ValueError):
                value = 50
            results.append(
                {
                    "value": value,
                    "classification": e.get("value_classification")
                    or _classification_from_value(value),
                    "timestamp": e.get("timestamp"),
                    "score": _map_fng_to_score(value),
                }
            )
        return results
