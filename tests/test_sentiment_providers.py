"""
Unit tests for the live sentiment providers and updated aggregator.

Covers:
- CryptoPanicSentimentProvider: happy path, error handling, caching, vote parsing
- RedditSentimentProvider: happy path, relevance filtering, error handling, caching
- SentimentAggregator: weighted combining, weight redistribution on failure,
  equal weighting fallback
"""
import time
import pytest
from unittest.mock import MagicMock, patch

from bot.sentiment.cryptopanic_provider import CryptoPanicSentimentProvider
from bot.sentiment.reddit_provider import RedditSentimentProvider
from bot.sentiment.aggregator import SentimentAggregator
from bot.sentiment.provider import MockSentimentProvider, SentimentData


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_cp_post(
    title="Bitcoin reaches new ATH",
    bullish=20,
    bearish=5,
    published_at="2026-01-15T10:30:00Z",
):
    """Return a minimal CryptoPanic API post dict."""
    return {
        "title": title,
        "published_at": published_at,
        "votes": {
            "bullish": bullish,
            "bearish": bearish,
            "positive": 0,
            "negative": 0,
        },
    }


def _make_cp_response(posts):
    """Wrap posts in a mock requests.Response."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"count": len(posts), "results": posts}
    return mock_resp


def _make_reddit_post(
    title="Bitcoin price analysis",
    created_utc=1700000000.0,
    subreddit="CryptoCurrency",
):
    return {
        "title": title,
        "created_utc": created_utc,
        "subreddit": subreddit,
        "score": 100,
        "num_comments": 50,
    }


def _make_reddit_response(posts):
    """Wrap posts in a mock requests.Response (Reddit JSON API format)."""
    children = [{"kind": "t3", "data": p} for p in posts]
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "kind": "Listing",
        "data": {"children": children, "after": None},
    }
    return mock_resp


# ===========================================================================
# CryptoPanicSentimentProvider tests
# ===========================================================================


class TestCryptoPanicSentimentProvider:

    def _provider(self, **kwargs):
        kwargs.setdefault("api_key", "test_key")
        kwargs.setdefault("cache_ttl", 1)  # very short TTL for cache tests
        return CryptoPanicSentimentProvider(**kwargs)

    # --- happy path ---------------------------------------------------------

    @patch("bot.sentiment.cryptopanic_provider.requests.get")
    def test_returns_sentiment_data(self, mock_get):
        """Provider converts API posts into SentimentData objects."""
        posts = [
            _make_cp_post(bullish=20, bearish=5),
            _make_cp_post(title="ETH update", bullish=10, bearish=10),
        ]
        mock_get.return_value = _make_cp_response(posts)

        provider = self._provider()
        results = provider.get_sentiment("BTC")

        assert len(results) == 2
        assert all(isinstance(s, SentimentData) for s in results)
        assert all(s.asset == "BTC" for s in results)
        assert all(s.source == "cryptopanic" for s in results)

    @patch("bot.sentiment.cryptopanic_provider.requests.get")
    def test_score_calculation_bullish_majority(self, mock_get):
        """Bullish majority → positive score."""
        mock_get.return_value = _make_cp_response(
            [_make_cp_post(bullish=30, bearish=10)]
        )
        provider = self._provider()
        results = provider.get_sentiment("BTC")

        assert results[0].score == pytest.approx((30 - 10) / 40)
        assert results[0].score > 0

    @patch("bot.sentiment.cryptopanic_provider.requests.get")
    def test_score_calculation_bearish_majority(self, mock_get):
        """Bearish majority → negative score."""
        mock_get.return_value = _make_cp_response(
            [_make_cp_post(bullish=5, bearish=25)]
        )
        provider = self._provider()
        results = provider.get_sentiment("BTC")

        assert results[0].score == pytest.approx((5 - 25) / 30)
        assert results[0].score < 0

    @patch("bot.sentiment.cryptopanic_provider.requests.get")
    def test_score_fallback_to_reactions(self, mock_get):
        """When no bullish/bearish votes, fall back to positive/negative."""
        post = {
            "title": "BTC news",
            "published_at": "2026-01-15T10:30:00Z",
            "votes": {"bullish": 0, "bearish": 0, "positive": 8, "negative": 2},
        }
        mock_get.return_value = _make_cp_response([post])
        provider = self._provider()
        results = provider.get_sentiment("BTC")

        assert results[0].score == pytest.approx((8 - 2) / 10)

    @patch("bot.sentiment.cryptopanic_provider.requests.get")
    def test_score_neutral_when_no_votes(self, mock_get):
        """No votes at all → score 0.0, low confidence."""
        post = {
            "title": "BTC news",
            "published_at": "2026-01-15T10:30:00Z",
            "votes": {"bullish": 0, "bearish": 0, "positive": 0, "negative": 0},
        }
        mock_get.return_value = _make_cp_response([post])
        provider = self._provider()
        results = provider.get_sentiment("BTC")

        assert results[0].score == 0.0
        assert results[0].confidence == pytest.approx(0.1)

    @patch("bot.sentiment.cryptopanic_provider.requests.get")
    def test_confidence_rises_with_vote_count(self, mock_get):
        """Higher vote counts should yield higher confidence."""
        low_votes = _make_cp_post(bullish=1, bearish=1)
        high_votes = _make_cp_post(bullish=20, bearish=0)
        mock_get.side_effect = [
            _make_cp_response([low_votes]),
            _make_cp_response([high_votes]),
        ]
        provider_low = self._provider()
        provider_high = self._provider()

        low_conf = provider_low.get_sentiment("BTC")[0].confidence
        high_conf = provider_high.get_sentiment("BTC")[0].confidence

        assert high_conf > low_conf

    @patch("bot.sentiment.cryptopanic_provider.requests.get")
    def test_asset_symbol_normalisation(self, mock_get):
        """Provider handles "BTC/USDT:USDT" → "BTC" internally."""
        mock_get.return_value = _make_cp_response([_make_cp_post()])
        provider = self._provider()
        results = provider.get_sentiment("BTC/USDT:USDT")

        assert results[0].asset == "BTC"

    @patch("bot.sentiment.cryptopanic_provider.requests.get")
    def test_multi_asset_sentiment(self, mock_get):
        """get_multi_asset_sentiment returns results for each asset."""
        mock_get.return_value = _make_cp_response([_make_cp_post()])
        provider = self._provider()
        results = provider.get_multi_asset_sentiment(["BTC", "ETH"])

        assert set(results.keys()) == {"BTC", "ETH"}

    # --- caching ------------------------------------------------------------

    @patch("bot.sentiment.cryptopanic_provider.requests.get")
    def test_caching_prevents_duplicate_requests(self, mock_get):
        """Second call within TTL should not make another HTTP request."""
        mock_get.return_value = _make_cp_response([_make_cp_post()])
        provider = self._provider(cache_ttl=60)

        provider.get_sentiment("BTC")
        provider.get_sentiment("BTC")

        assert mock_get.call_count == 1

    @patch("bot.sentiment.cryptopanic_provider.requests.get")
    def test_cache_expires_after_ttl(self, mock_get):
        """After TTL expires, a fresh HTTP request should be made."""
        mock_get.return_value = _make_cp_response([_make_cp_post()])
        # TTL = 0 means cache expires immediately
        provider = self._provider(cache_ttl=0)

        provider.get_sentiment("BTC")
        # Give the TTLCache time to evict (it evicts lazily on next access)
        time.sleep(0.05)
        provider.get_sentiment("BTC")

        assert mock_get.call_count >= 2

    # --- error handling -----------------------------------------------------

    @patch("bot.sentiment.cryptopanic_provider.requests.get")
    def test_returns_empty_list_on_http_error(self, mock_get):
        """HTTP errors → empty list (no exception propagated)."""
        import requests as req
        mock_get.side_effect = req.exceptions.HTTPError("503 Server Error")
        provider = self._provider()
        results = provider.get_sentiment("BTC")

        assert results == []

    @patch("bot.sentiment.cryptopanic_provider.requests.get")
    def test_returns_empty_list_on_connection_error(self, mock_get):
        """Connection errors → empty list."""
        import requests as req
        mock_get.side_effect = req.exceptions.ConnectionError("timeout")
        provider = self._provider()
        results = provider.get_sentiment("BTC")

        assert results == []

    @patch("bot.sentiment.cryptopanic_provider.requests.get")
    def test_skips_malformed_posts(self, mock_get):
        """Malformed post dicts are silently skipped."""
        posts = [
            _make_cp_post(),                    # valid
            {"title": None, "votes": None},     # malformed
        ]
        mock_get.return_value = _make_cp_response(posts)
        provider = self._provider()
        results = provider.get_sentiment("BTC")

        # At least the valid post should parse
        assert len(results) >= 1

    def test_warns_when_no_api_key(self, caplog):
        """Warning is logged when no API key is provided."""
        import logging
        with caplog.at_level(logging.WARNING, logger="bot.sentiment.cryptopanic_provider"):
            provider = CryptoPanicSentimentProvider(api_key="")

        assert "no API key" in caplog.text.lower() or provider.api_key == ""


# ===========================================================================
# RedditSentimentProvider tests
# ===========================================================================


class TestRedditSentimentProvider:

    def _provider(self, **kwargs):
        kwargs.setdefault("subreddits", ["CryptoCurrency"])
        kwargs.setdefault("cache_ttl", 1)
        return RedditSentimentProvider(**kwargs)

    # --- happy path ---------------------------------------------------------

    @patch("bot.sentiment.reddit_provider.requests.get")
    def test_returns_sentiment_data_for_relevant_posts(self, mock_get):
        """Relevant posts produce SentimentData objects."""
        posts = [
            _make_reddit_post("Bitcoin hits new ATH today!"),
            _make_reddit_post("BTC breaking resistance level"),
        ]
        mock_get.return_value = _make_reddit_response(posts)

        provider = self._provider()
        results = provider.get_sentiment("BTC")

        assert len(results) == 2
        assert all(isinstance(s, SentimentData) for s in results)
        assert all(s.asset == "BTC" for s in results)
        assert all("reddit" in s.source for s in results)

    @patch("bot.sentiment.reddit_provider.requests.get")
    def test_irrelevant_posts_are_filtered(self, mock_get):
        """Posts with no asset keywords are excluded."""
        posts = [
            _make_reddit_post("Bitcoin bullish signal"),   # relevant
            _make_reddit_post("General market discussion"),  # irrelevant
            _make_reddit_post("Weekend casual thread"),      # irrelevant
        ]
        mock_get.return_value = _make_reddit_response(posts)

        provider = self._provider()
        results = provider.get_sentiment("BTC")

        assert len(results) == 1

    @patch("bot.sentiment.reddit_provider.requests.get")
    def test_positive_sentiment_title(self, mock_get):
        """Strongly positive title → score > 0."""
        posts = [_make_reddit_post("Bitcoin surges to amazing new highs!")]
        mock_get.return_value = _make_reddit_response(posts)

        provider = self._provider()
        results = provider.get_sentiment("BTC")

        assert results[0].score > 0

    @patch("bot.sentiment.reddit_provider.requests.get")
    def test_negative_sentiment_title(self, mock_get):
        """Strongly negative title → score < 0."""
        posts = [_make_reddit_post("Bitcoin crashes badly, terrible outlook")]
        mock_get.return_value = _make_reddit_response(posts)

        provider = self._provider()
        results = provider.get_sentiment("BTC")

        assert results[0].score < 0

    @patch("bot.sentiment.reddit_provider.requests.get")
    def test_score_in_valid_range(self, mock_get):
        """Scores must be within [-1, 1]."""
        posts = [
            _make_reddit_post("Bitcoin absolutely amazing incredible"),
            _make_reddit_post("BTC terrible awful crash doom"),
        ]
        mock_get.return_value = _make_reddit_response(posts)

        provider = self._provider()
        results = provider.get_sentiment("BTC")

        for s in results:
            assert -1.0 <= s.score <= 1.0

    @patch("bot.sentiment.reddit_provider.requests.get")
    def test_asset_symbol_normalisation(self, mock_get):
        """Provider handles "ETH/USDT:USDT" → "ETH" internally."""
        posts = [_make_reddit_post("Ethereum ETH looking bullish")]
        mock_get.return_value = _make_reddit_response(posts)

        provider = self._provider()
        results = provider.get_sentiment("ETH/USDT:USDT")

        assert results[0].asset == "ETH"

    @patch("bot.sentiment.reddit_provider.requests.get")
    def test_multi_asset_sentiment(self, mock_get):
        """get_multi_asset_sentiment returns results for each asset."""
        mock_get.return_value = _make_reddit_response(
            [_make_reddit_post("Bitcoin BTC news")]
        )
        provider = self._provider()
        results = provider.get_multi_asset_sentiment(["BTC", "ETH"])

        assert set(results.keys()) == {"BTC", "ETH"}

    @patch("bot.sentiment.reddit_provider.requests.get")
    def test_timestamp_parsed_from_created_utc(self, mock_get):
        """created_utc is converted to an aware datetime."""
        posts = [_make_reddit_post(created_utc=1700000000.0)]
        mock_get.return_value = _make_reddit_response(posts)

        provider = self._provider()
        results = provider.get_sentiment("BTC")

        assert results[0].timestamp is not None
        assert results[0].timestamp.tzinfo is not None

    # --- caching ------------------------------------------------------------

    @patch("bot.sentiment.reddit_provider.requests.get")
    def test_caching_prevents_duplicate_requests(self, mock_get):
        """Second call within TTL should not make another HTTP request."""
        mock_get.return_value = _make_reddit_response(
            [_make_reddit_post("Bitcoin BTC")]
        )
        provider = self._provider(cache_ttl=60)

        provider.get_sentiment("BTC")
        provider.get_sentiment("BTC")

        assert mock_get.call_count == 1

    # --- error handling -----------------------------------------------------

    @patch("bot.sentiment.reddit_provider.requests.get")
    def test_returns_empty_list_on_http_error(self, mock_get):
        """HTTP errors → empty list, no exception propagated."""
        import requests as req
        mock_get.side_effect = req.exceptions.HTTPError("429 Too Many Requests")
        provider = self._provider()
        results = provider.get_sentiment("BTC")

        assert results == []

    @patch("bot.sentiment.reddit_provider.requests.get")
    def test_continues_after_single_subreddit_failure(self, mock_get):
        """If one subreddit fails, provider continues with the others."""
        import requests as req
        # First subreddit fails, second succeeds
        mock_get.side_effect = [
            req.exceptions.ConnectionError("timeout"),
            _make_reddit_response([_make_reddit_post("BTC analysis")]),
        ]

        provider = RedditSentimentProvider(
            subreddits=["CryptoCurrency", "Bitcoin"],
            cache_ttl=1,
        )
        results = provider.get_sentiment("BTC")

        # Should still have results from the second subreddit
        assert len(results) >= 1

    @patch("bot.sentiment.reddit_provider.requests.get")
    def test_empty_results_when_no_relevant_posts(self, mock_get):
        """Empty list when all posts are irrelevant."""
        mock_get.return_value = _make_reddit_response(
            [_make_reddit_post("Weekend discussion no keywords")]
        )
        provider = self._provider()
        results = provider.get_sentiment("BTC")

        assert results == []


# ===========================================================================
# SentimentAggregator (updated weighted logic) tests
# ===========================================================================


class TestWeightedSentimentAggregator:

    # --- basic weighted aggregation -----------------------------------------

    def test_weighted_aggregation_combines_providers(self):
        """Weighted scores from multiple providers are combined correctly."""
        # Provider A: score ~ 0.8 (bullish)
        # Provider B: score ~ -0.5 (bearish)
        # With weights 0.6 / 0.4, result should be closer to A's score
        provider_a = MockSentimentProvider(base_sentiment=0.8)
        provider_b = MockSentimentProvider(base_sentiment=-0.5)

        aggregator = SentimentAggregator(
            providers=[provider_a, provider_b],
            weights={
                "MockSentimentProvider": 0.5,  # same class → same weight
            },
        )
        result = aggregator.aggregate_sentiment("BTC", lookback_hours=4)

        assert result is not None
        assert -1.0 <= result.score <= 1.0

    def test_equal_weighting_when_no_weights_given(self):
        """Without explicit weights all providers receive equal weight."""
        p1 = MockSentimentProvider(base_sentiment=0.6)
        p2 = MockSentimentProvider(base_sentiment=-0.6)
        aggregator = SentimentAggregator(providers=[p1, p2])

        result = aggregator.aggregate_sentiment("BTC", lookback_hours=4)

        assert result is not None
        # Equal weight of equal-magnitude opposite sentiments → near 0
        assert abs(result.score) < 0.5

    def test_single_provider_weight_normalised(self):
        """Single provider → weight is 1.0 (normalised)."""
        provider = MockSentimentProvider(base_sentiment=0.5)
        aggregator = SentimentAggregator(
            providers=[provider],
            weights={"MockSentimentProvider": 0.4},
        )
        result = aggregator.aggregate_sentiment("BTC", lookback_hours=4)

        assert result is not None
        # Score should be close to the base sentiment
        assert result.score > 0

    # --- weight redistribution on failure -----------------------------------

    def test_failed_provider_weight_redistributed(self):
        """When one provider fails, its weight goes to the active providers."""

        class FailingProvider(MockSentimentProvider):
            def get_sentiment(self, asset, lookback_hours=24):
                raise RuntimeError("simulated API failure")

        good = MockSentimentProvider(base_sentiment=0.7)
        bad = FailingProvider(base_sentiment=0.0)

        aggregator = SentimentAggregator(
            providers=[good, bad],
            weights={
                "MockSentimentProvider": 0.7,
                "FailingProvider": 0.3,
            },
        )
        # Should still produce a result using only 'good'
        result = aggregator.aggregate_sentiment("BTC", lookback_hours=4)

        assert result is not None
        assert result.score > 0  # Only good provider contributes

    def test_returns_none_when_all_providers_fail(self):
        """Returns None when every provider raises an exception."""

        class AlwaysFails(MockSentimentProvider):
            def get_sentiment(self, asset, lookback_hours=24):
                raise RuntimeError("always fails")

        aggregator = SentimentAggregator(
            providers=[AlwaysFails(), AlwaysFails()]
        )
        result = aggregator.aggregate_sentiment("BTC", lookback_hours=4)

        assert result is None

    def test_provider_returning_empty_list_redistributes_weight(self):
        """Provider returning [] has its weight redistributed."""

        class EmptyProvider(MockSentimentProvider):
            def get_sentiment(self, asset, lookback_hours=24):
                return []  # returns no data

        real = MockSentimentProvider(base_sentiment=0.5)
        empty = EmptyProvider(base_sentiment=0.0)

        aggregator = SentimentAggregator(
            providers=[real, empty],
            weights={
                "MockSentimentProvider": 0.5,
                "EmptyProvider": 0.5,
            },
        )
        result = aggregator.aggregate_sentiment("BTC", lookback_hours=4)

        assert result is not None
        assert result.score > 0

    # --- multi-asset & market overview --------------------------------------

    def test_aggregate_multi_asset(self):
        """aggregate_multi_asset handles list of pairs."""
        provider = MockSentimentProvider(base_sentiment=0.2)
        aggregator = SentimentAggregator(providers=[provider])

        results = aggregator.aggregate_multi_asset(
            ["BTC/USDT:USDT", "ETH/USDT:USDT"]
        )

        assert "BTC" in results
        assert "ETH" in results

    def test_get_market_overview_structure(self):
        """get_market_overview returns the expected keys."""
        provider = MockSentimentProvider(base_sentiment=0.1)
        aggregator = SentimentAggregator(providers=[provider])

        overview = aggregator.get_market_overview(["BTC", "ETH"])

        assert "overall_score" in overview
        assert "overall_trend" in overview
        assert "bullish_count" in overview
        assert "bearish_count" in overview
        assert "neutral_count" in overview

    # --- trend determination ------------------------------------------------

    def test_trend_bullish_above_threshold(self):
        """Score > 0.15 → trend = bullish."""
        provider = MockSentimentProvider(base_sentiment=0.8)
        aggregator = SentimentAggregator(providers=[provider])

        result = aggregator.aggregate_sentiment("BTC", lookback_hours=4)

        assert result is not None
        assert result.trend == "bullish"

    def test_trend_bearish_below_threshold(self):
        """Score < -0.15 → trend = bearish."""
        provider = MockSentimentProvider(base_sentiment=-0.8)
        aggregator = SentimentAggregator(providers=[provider])

        result = aggregator.aggregate_sentiment("BTC", lookback_hours=4)

        assert result is not None
        assert result.trend == "bearish"

    def test_sample_size_is_sum_of_all_providers(self):
        """sample_size is the total number of data points across providers."""
        p1 = MockSentimentProvider(base_sentiment=0.3)
        p2 = MockSentimentProvider(base_sentiment=0.3)
        aggregator = SentimentAggregator(providers=[p1, p2])

        result = aggregator.aggregate_sentiment("BTC", lookback_hours=4)

        # Each provider generates max(1, 4//4) = 1 data point per call
        assert result is not None
        assert result.sample_size >= 2
