"""
Twitter/X sentiment provider.

Uses Twitter API v2 recent search endpoint to fetch crypto-related tweets and
analyses them with VADER sentiment to produce a normalised score in [-1, 1].

Bearer token is read from the ``TWITTER_BEARER_TOKEN`` environment variable.
Results are cached for 15 minutes.  The provider respects Twitter's app-level
rate limit of 450 requests per 15-minute window.
"""
import os
import math
import time
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

import requests
from cachetools import TTLCache
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from .provider import SentimentProvider, SentimentData

logger = logging.getLogger(__name__)

# Number of seconds in Twitter's rate-limit window (15 minutes)
_TWITTER_WINDOW_SECONDS = 900
# Twitter app-level rate limit: 450 requests per 15-min window
_TWITTER_MAX_REQUESTS_PER_WINDOW = 450


class _RateLimiter:
    """Token-bucket–style rate limiter (minimum interval between calls)."""

    def __init__(self, requests_per_window: int, window_seconds: int) -> None:
        self._min_interval: float = window_seconds / max(1, requests_per_window)
        self._last_call: float = 0.0

    def wait(self) -> None:
        """Block until the next request is allowed."""
        elapsed = time.monotonic() - self._last_call
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_call = time.monotonic()


class TwitterSentimentProvider(SentimentProvider):
    """
    Sentiment provider backed by the Twitter/X API v2.

    Searches for recent tweets mentioning each asset using cashtags and
    hashtags, then applies VADER sentiment to the tweet text.  Engagement
    metrics (likes, retweets, replies) are used to weight each tweet's
    contribution to the final score.

    Attributes:
        SEARCH_URL: Twitter API v2 recent search endpoint.
        DEFAULT_CACHE_TTL: Seconds to cache results (900 s = 15 min).
        DEFAULT_MAX_RESULTS: Tweets to fetch per search query (10–100).
        ASSET_QUERIES: Per-asset search queries sent to the Twitter API.
    """

    SEARCH_URL = "https://api.twitter.com/2/tweets/search/recent"
    DEFAULT_CACHE_TTL = 900  # 15 minutes
    DEFAULT_MAX_RESULTS = 50

    ASSET_QUERIES: Dict[str, str] = {
        "BTC": "($BTC OR #Bitcoin) lang:en -is:retweet",
        "ETH": "($ETH OR #Ethereum) lang:en -is:retweet",
        "SOL": "($SOL OR #Solana) lang:en -is:retweet",
    }

    def __init__(
        self,
        bearer_token: Optional[str] = None,
        cache_ttl: int = DEFAULT_CACHE_TTL,
        max_requests_per_window: int = _TWITTER_MAX_REQUESTS_PER_WINDOW,
        max_results: int = DEFAULT_MAX_RESULTS,
        timeout: int = 10,
    ) -> None:
        """
        Initialise the provider.

        Args:
            bearer_token: Twitter API v2 bearer token.  Falls back to the
                ``TWITTER_BEARER_TOKEN`` environment variable when omitted.
            cache_ttl: Seconds to keep cached results (default 900 = 15 min).
            max_requests_per_window: Max requests per 15-min window
                (default 450 — Twitter app-level limit).
            max_results: Tweets to fetch per query (10–100, default 50).
            timeout: HTTP request timeout in seconds (default 10).
        """
        self.bearer_token = bearer_token or os.environ.get(
            "TWITTER_BEARER_TOKEN", ""
        )
        if not self.bearer_token:
            logger.warning(
                "TwitterSentimentProvider: no bearer token configured – "
                "set the TWITTER_BEARER_TOKEN environment variable."
            )
        self._cache: TTLCache = TTLCache(maxsize=64, ttl=cache_ttl)
        self._rate_limiter = _RateLimiter(
            max_requests_per_window, _TWITTER_WINDOW_SECONDS
        )
        self._max_results = max(10, min(100, max_results))
        self._timeout = timeout
        self._analyzer = SentimentIntensityAnalyzer()
        logger.info(
            "Initialized TwitterSentimentProvider "
            "(cache_ttl=%ds, max_results=%d)",
            cache_ttl,
            self._max_results,
        )

    # ------------------------------------------------------------------
    # SentimentProvider interface
    # ------------------------------------------------------------------

    def get_sentiment(
        self, asset: str, lookback_hours: int = 24
    ) -> List[SentimentData]:
        """
        Fetch and analyse Twitter/X sentiment for *asset*.

        Args:
            asset: Asset symbol, e.g. ``"BTC"`` or ``"BTC/USDT:USDT"``.
            lookback_hours: Kept for interface compatibility; the provider
                always fetches the most recent tweets (up to 7 days back).

        Returns:
            List of :class:`SentimentData` objects (empty list on error or
            when no bearer token is configured).
        """
        if not self.bearer_token:
            logger.debug(
                "TwitterSentimentProvider: skipping %s — no bearer token",
                asset,
            )
            return []

        base_asset = asset.split("/")[0] if "/" in asset else asset
        base_asset = base_asset.upper()

        cache_key = f"twitter:{base_asset}"
        if cache_key in self._cache:
            logger.debug(
                "Twitter: returning cached sentiment for %s", base_asset
            )
            return self._cache[cache_key]

        query = self.ASSET_QUERIES.get(base_asset)
        if not query:
            logger.warning(
                "TwitterSentimentProvider: no query defined for asset %s",
                base_asset,
            )
            return []

        try:
            tweets = self._fetch_tweets(query)
            sentiments = [
                self._tweet_to_sentiment(t, base_asset) for t in tweets
            ]
            sentiments = [s for s in sentiments if s is not None]
        except Exception as exc:
            logger.error(
                "TwitterSentimentProvider: failed to fetch %s: %s",
                base_asset,
                exc,
            )
            sentiments = []

        self._cache[cache_key] = sentiments
        logger.info(
            "Twitter: fetched %d sentiment items for %s",
            len(sentiments),
            base_asset,
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

    def _fetch_tweets(self, query: str) -> List[Dict[str, Any]]:
        """
        Call the Twitter API v2 recent search endpoint.

        Args:
            query: Twitter search query string.

        Returns:
            List of tweet data dicts from the API ``data`` key.

        Raises:
            requests.RequestException: on network or HTTP errors.
        """
        self._rate_limiter.wait()
        headers = {"Authorization": f"Bearer {self.bearer_token}"}
        params: Dict[str, Any] = {
            "query": query,
            "max_results": self._max_results,
            "tweet.fields": "created_at,public_metrics,lang",
        }
        response = requests.get(
            self.SEARCH_URL,
            headers=headers,
            params=params,
            timeout=self._timeout,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("data") or []

    def _tweet_to_sentiment(
        self, tweet: Dict[str, Any], asset: str
    ) -> Optional[SentimentData]:
        """
        Convert a Twitter API v2 tweet dict to a :class:`SentimentData` object.

        Engagement (likes + retweets + replies) weights each tweet's
        contribution: tweets with more engagement yield higher confidence.
        The VADER ``compound`` score is used as the sentiment score directly.

        Args:
            tweet: Raw tweet dict from the Twitter API v2 ``data`` array.
            asset: Base asset symbol (e.g. ``"BTC"``).

        Returns:
            A :class:`SentimentData` instance, or ``None`` if the tweet is
            malformed.
        """
        try:
            text: str = tweet.get("text", "")
            if not text:
                return None

            scores = self._analyzer.polarity_scores(text)
            compound: float = scores["compound"]  # already in [-1, 1]

            # Engagement weighting for confidence
            metrics: Dict[str, int] = tweet.get("public_metrics") or {}
            likes = int(metrics.get("like_count", 0))
            retweets = int(metrics.get("retweet_count", 0))
            replies = int(metrics.get("reply_count", 0))
            engagement = likes + retweets + replies

            # Confidence: baseline 0.3, boosted by engagement (log-scaled)
            engagement_boost = min(0.5, 0.1 * math.log1p(engagement))
            confidence = min(0.95, 0.3 + abs(compound) * 0.3 + engagement_boost)

            created_at_str: str = tweet.get("created_at", "")
            timestamp: Optional[datetime] = None
            if created_at_str:
                try:
                    timestamp = datetime.fromisoformat(
                        created_at_str.replace("Z", "+00:00")
                    )
                except ValueError:
                    pass

            return SentimentData(
                asset=asset,
                score=compound,
                confidence=confidence,
                headline=text[:200],  # truncate for storage
                source="twitter",
                timestamp=timestamp,
            )
        except (KeyError, TypeError, ValueError) as exc:
            logger.debug("Twitter: could not parse tweet: %s", exc)
            return None
