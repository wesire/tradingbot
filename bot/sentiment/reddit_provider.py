"""
Reddit sentiment provider.

Scrapes recent posts from crypto subreddits via Reddit's public JSON API and
analyses post titles with VADER to produce a normalised sentiment score in
[-1, 1].

No credentials are required for the public API.  Optional Reddit API
credentials (``REDDIT_CLIENT_ID``, ``REDDIT_CLIENT_SECRET``) are reserved
for future PRAW-based enhancements.  ``REDDIT_USER_AGENT`` may be set to
customise the User-Agent header sent to Reddit.

Results are cached for 30 minutes to stay well within Reddit's rate limits.
"""
import os
import time
import logging
from typing import List, Dict, Optional
from datetime import datetime, timezone

import requests
from cachetools import TTLCache
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

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


class RedditSentimentProvider(SentimentProvider):
    """
    Sentiment provider that scrapes Reddit crypto subreddits.

    Uses Reddit's public JSON API (no credentials required) and analyses post
    titles with VADER to derive a sentiment score in [-1, 1].

    Attributes:
        SUBREDDITS: Default subreddits to scrape.
        DEFAULT_CACHE_TTL: Seconds to cache results (1800 s = 30 min).
        DEFAULT_REQUESTS_PER_MINUTE: Conservative rate limit.
        POST_LIMIT: Maximum posts to fetch per subreddit per request.
        ASSET_KEYWORDS: Per-asset keyword lists used for relevance filtering.
    """

    SUBREDDITS = ["CryptoCurrency", "Bitcoin"]
    DEFAULT_CACHE_TTL = 1800  # 30 minutes
    DEFAULT_REQUESTS_PER_MINUTE = 10
    POST_LIMIT = 100

    ASSET_KEYWORDS: Dict[str, List[str]] = {
        "BTC": ["bitcoin", "btc", "$btc"],
        "ETH": ["ethereum", "eth", "$eth", "ether"],
        "SOL": ["solana", "sol", "$sol"],
    }

    def __init__(
        self,
        subreddits: Optional[List[str]] = None,
        cache_ttl: int = DEFAULT_CACHE_TTL,
        requests_per_minute: int = DEFAULT_REQUESTS_PER_MINUTE,
        timeout: int = 10,
        user_agent: Optional[str] = None,
    ) -> None:
        """
        Initialise the provider.

        Args:
            subreddits: Subreddits to scrape.  Defaults to
                ``["CryptoCurrency", "Bitcoin"]``.
            cache_ttl: Seconds to keep cached results (default 1800 = 30 min).
            requests_per_minute: Max requests per minute (default 10).
            timeout: HTTP request timeout in seconds (default 10).
            user_agent: Custom User-Agent header.  Falls back to
                ``REDDIT_USER_AGENT`` env var, then a safe default string.
        """
        self._subreddits = subreddits or list(self.SUBREDDITS)
        self._cache: TTLCache = TTLCache(maxsize=64, ttl=cache_ttl)
        self._rate_limiter = _RateLimiter(requests_per_minute)
        self._timeout = timeout
        self._user_agent = (
            user_agent
            or os.environ.get(
                "REDDIT_USER_AGENT", "TradingBot/1.0 Sentiment Scraper"
            )
        )
        self._analyzer = SentimentIntensityAnalyzer()
        logger.info(
            "Initialized RedditSentimentProvider "
            "(subreddits=%s, cache_ttl=%ds, rpm=%d)",
            self._subreddits,
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
        Fetch and analyse Reddit sentiment for *asset*.

        Args:
            asset: Asset symbol, e.g. ``"BTC"`` or ``"BTC/USDT:USDT"``.
            lookback_hours: Kept for interface compatibility; the provider
                always fetches the most recent hot posts.

        Returns:
            List of :class:`SentimentData` objects (empty list on error).
        """
        base_asset = asset.split("/")[0] if "/" in asset else asset
        base_asset = base_asset.upper()
        keywords = self.ASSET_KEYWORDS.get(base_asset, [base_asset.lower()])

        cache_key = f"reddit:{base_asset}"
        if cache_key in self._cache:
            logger.debug(
                "Reddit: returning cached sentiment for %s", base_asset
            )
            return self._cache[cache_key]

        all_sentiments: List[SentimentData] = []
        for subreddit in self._subreddits:
            try:
                posts = self._fetch_posts(subreddit)
                relevant = self._filter_relevant(posts, keywords)
                for post in relevant:
                    all_sentiments.append(
                        self._analyse_post(post, base_asset, subreddit)
                    )
            except Exception as exc:
                logger.error(
                    "RedditSentimentProvider: failed to fetch r/%s: %s",
                    subreddit,
                    exc,
                )

        self._cache[cache_key] = all_sentiments
        logger.info(
            "Reddit: fetched %d relevant posts for %s",
            len(all_sentiments),
            base_asset,
        )
        return all_sentiments

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

    def _fetch_posts(self, subreddit: str) -> List[Dict]:
        """
        Fetch hot posts from a subreddit via the public JSON API.

        Args:
            subreddit: Subreddit name (without the ``r/`` prefix).

        Returns:
            List of raw post data dicts (the ``data`` field of each child).

        Raises:
            requests.RequestException: on network or HTTP errors.
        """
        self._rate_limiter.wait()
        url = f"https://www.reddit.com/r/{subreddit}/hot.json"
        headers = {"User-Agent": self._user_agent}
        params = {"limit": self.POST_LIMIT}
        response = requests.get(
            url, headers=headers, params=params, timeout=self._timeout
        )
        response.raise_for_status()
        data = response.json()
        children = data.get("data", {}).get("children", [])
        return [child.get("data", {}) for child in children]

    @staticmethod
    def _filter_relevant(
        posts: List[Dict], keywords: List[str]
    ) -> List[Dict]:
        """Return only posts whose titles contain at least one keyword."""
        result = []
        for post in posts:
            title: str = post.get("title", "").lower()
            if any(kw in title for kw in keywords):
                result.append(post)
        return result

    def _analyse_post(
        self, post: Dict, asset: str, subreddit: str
    ) -> SentimentData:
        """
        Run VADER on a post title and return a :class:`SentimentData` object.

        The VADER ``compound`` score is already in [-1, 1].  Confidence is
        proportional to how strongly non-neutral the score is, with a
        baseline of 0.3.

        Args:
            post: Raw post data dict from Reddit.
            asset: Base asset symbol (e.g. ``"BTC"``).
            subreddit: Source subreddit name (for the ``source`` field).

        Returns:
            :class:`SentimentData` for this post.
        """
        title: str = post.get("title", "")
        scores = self._analyzer.polarity_scores(title)
        compound: float = scores["compound"]  # already in [-1, 1]

        # Confidence: baseline 0.3, rises with score magnitude
        confidence = min(0.95, 0.3 + abs(compound) * 0.5)

        created_utc = post.get("created_utc")
        timestamp: Optional[datetime] = None
        if created_utc:
            try:
                timestamp = datetime.fromtimestamp(
                    float(created_utc), tz=timezone.utc
                )
            except (ValueError, OSError):
                pass

        return SentimentData(
            asset=asset,
            score=compound,
            confidence=confidence,
            headline=title,
            source=f"reddit/r/{subreddit}",
            timestamp=timestamp,
        )
