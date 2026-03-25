"""
CryptoPanic sentiment provider.

Integrates with the CryptoPanic API to fetch recent crypto news posts and
derives a normalised sentiment score from the bullish/bearish vote data.

API key is read from the ``CRYPTOPANIC_API_KEY`` environment variable.
Results are cached for 15 minutes to stay within the ~5 req/min API limit.
"""
import os
import time
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

import requests
from cachetools import TTLCache

from .provider import SentimentProvider, SentimentData

logger = logging.getLogger(__name__)


class _RateLimiter:
    """Token-bucket–style rate limiter (minimum interval between calls)."""

    def __init__(self, requests_per_minute: int) -> None:
        self._min_interval: float = 60.0 / max(1, requests_per_minute)
        self._last_call: float = 0.0

    def wait(self) -> None:
        """Block until the next request is allowed."""
        elapsed = time.monotonic() - self._last_call
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_call = time.monotonic()


class CryptoPanicSentimentProvider(SentimentProvider):
    """
    Sentiment provider backed by the CryptoPanic news API.

    Fetches recent crypto news posts for BTC, ETH, and SOL and derives a
    sentiment score in [-1, 1] from the bullish/bearish vote counts attached
    to each post.

    Attributes:
        BASE_URL: CryptoPanic v1 posts endpoint.
        DEFAULT_REQUESTS_PER_MINUTE: Conservative rate limit (5 req/min).
        DEFAULT_CACHE_TTL: Seconds to cache results (900 s = 15 min).
        CURRENCY_MAP: Maps bot asset symbols to CryptoPanic currency codes.
    """

    BASE_URL = "https://cryptopanic.com/api/v1/posts/"
    DEFAULT_REQUESTS_PER_MINUTE = 5
    DEFAULT_CACHE_TTL = 900  # 15 minutes

    CURRENCY_MAP: Dict[str, str] = {
        "BTC": "BTC",
        "ETH": "ETH",
        "SOL": "SOL",
    }

    def __init__(
        self,
        api_key: Optional[str] = None,
        cache_ttl: int = DEFAULT_CACHE_TTL,
        requests_per_minute: int = DEFAULT_REQUESTS_PER_MINUTE,
        timeout: int = 10,
    ) -> None:
        """
        Initialise the provider.

        Args:
            api_key: CryptoPanic auth token.  Falls back to the
                ``CRYPTOPANIC_API_KEY`` environment variable when omitted.
            cache_ttl: Seconds to keep cached results (default 900 = 15 min).
            requests_per_minute: Max requests per minute (default 5).
            timeout: HTTP request timeout in seconds (default 10).
        """
        self.api_key = api_key or os.environ.get("CRYPTOPANIC_API_KEY", "")
        if not self.api_key:
            logger.warning(
                "CryptoPanicSentimentProvider: no API key configured – "
                "set the CRYPTOPANIC_API_KEY environment variable."
            )
        self._cache: TTLCache = TTLCache(maxsize=64, ttl=cache_ttl)
        self._rate_limiter = _RateLimiter(requests_per_minute)
        self._timeout = timeout
        logger.info(
            "Initialized CryptoPanicSentimentProvider "
            "(cache_ttl=%ds, rpm=%d)",
            cache_ttl,
            requests_per_minute,
        )

    # ------------------------------------------------------------------
    # SentimentProvider interface
    # ------------------------------------------------------------------

    def get_sentiment(
        self, asset: str, lookback_hours: int = 24
    ) -> List[SentimentData]:
        """
        Fetch sentiment data for *asset* from CryptoPanic.

        Args:
            asset: Asset symbol, e.g. ``"BTC"`` or ``"BTC/USDT:USDT"``.
            lookback_hours: Kept for interface compatibility; the provider
                always fetches the most recent page of posts.

        Returns:
            List of :class:`SentimentData` objects (empty list on error).
        """
        base_asset = asset.split("/")[0] if "/" in asset else asset
        base_asset = base_asset.upper()
        currency = self.CURRENCY_MAP.get(base_asset, base_asset)

        cache_key = f"cryptopanic:{currency}"
        if cache_key in self._cache:
            logger.debug(
                "CryptoPanic: returning cached sentiment for %s", currency
            )
            return self._cache[cache_key]

        try:
            posts = self._fetch_posts(currency)
            sentiments = [
                self._post_to_sentiment(p, base_asset) for p in posts
            ]
            sentiments = [s for s in sentiments if s is not None]
        except Exception as exc:
            logger.error(
                "CryptoPanicSentimentProvider: failed to fetch %s: %s",
                currency,
                exc,
            )
            sentiments = []

        self._cache[cache_key] = sentiments
        logger.info(
            "CryptoPanic: fetched %d sentiment items for %s",
            len(sentiments),
            currency,
        )
        return sentiments

    def get_multi_asset_sentiment(
        self,
        assets: List[str],
        lookback_hours: int = 24,
    ) -> Dict[str, List[SentimentData]]:
        """Fetch sentiment for multiple assets."""
        return {
            asset: self.get_sentiment(asset, lookback_hours)
            for asset in assets
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch_posts(self, currency: str) -> List[Dict[str, Any]]:
        """
        Call the CryptoPanic API and return raw post dictionaries.

        Args:
            currency: CryptoPanic currency code (e.g. ``"BTC"``).

        Returns:
            List of post dicts from the ``results`` key of the API response.

        Raises:
            requests.RequestException: on network or HTTP errors.
        """
        self._rate_limiter.wait()
        params: Dict[str, Any] = {
            "auth_token": self.api_key,
            "currencies": currency,
            "public": "true",
            "kind": "news",
        }
        response = requests.get(
            self.BASE_URL, params=params, timeout=self._timeout
        )
        response.raise_for_status()
        data = response.json()
        return data.get("results", [])

    @staticmethod
    def _post_to_sentiment(
        post: Dict[str, Any], asset: str
    ) -> Optional[SentimentData]:
        """
        Convert a CryptoPanic post dict to a :class:`SentimentData` object.

        The score is computed from the ``bullish`` and ``bearish`` vote counts.
        If no directional votes are present the ``positive``/``negative``
        reaction counts are used as a fallback.  If there are no votes at all
        the score is 0.0 with low confidence.

        Args:
            post: Raw post dict from the CryptoPanic API.
            asset: Base asset symbol (e.g. ``"BTC"``).

        Returns:
            A :class:`SentimentData` instance, or ``None`` if the post is
            malformed.
        """
        try:
            votes: Dict[str, int] = post.get("votes") or {}
            bullish = int(votes.get("bullish", 0))
            bearish = int(votes.get("bearish", 0))
            total_votes = bullish + bearish

            if total_votes > 0:
                score = (bullish - bearish) / total_votes
                # Confidence rises with vote count, capped at 0.95
                confidence = min(0.95, 0.3 + 0.05 * total_votes)
            else:
                # Fall back to generic positive/negative reaction counts
                positive = int(votes.get("positive", 0))
                negative = int(votes.get("negative", 0))
                reaction_total = positive + negative
                if reaction_total > 0:
                    score = (positive - negative) / reaction_total
                    confidence = min(0.95, 0.2 + 0.03 * reaction_total)
                else:
                    score = 0.0
                    confidence = 0.1

            title: str = post.get("title", "")
            published_at_str: str = post.get("published_at", "")
            timestamp: Optional[datetime] = None
            if published_at_str:
                try:
                    timestamp = datetime.fromisoformat(
                        published_at_str.replace("Z", "+00:00")
                    )
                except ValueError:
                    pass

            return SentimentData(
                asset=asset,
                score=score,
                confidence=confidence,
                headline=title,
                source="cryptopanic",
                timestamp=timestamp,
            )
        except (KeyError, TypeError, ValueError) as exc:
            logger.debug("CryptoPanic: could not parse post: %s", exc)
            return None
