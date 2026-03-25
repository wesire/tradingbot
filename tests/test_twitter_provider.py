"""
Unit tests for TwitterSentimentProvider.

All HTTP calls are mocked; no real network access is required.
"""
import time
import pytest
from unittest.mock import MagicMock, patch

from bot.sentiment.twitter_provider import TwitterSentimentProvider
from bot.sentiment.provider import SentimentData


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tweet(
    text="Bitcoin is surging! $BTC to the moon 🚀",
    created_at="2026-01-15T10:30:00Z",
    like_count=50,
    retweet_count=20,
    reply_count=5,
):
    return {
        "id": "123456789",
        "text": text,
        "created_at": created_at,
        "public_metrics": {
            "like_count": like_count,
            "retweet_count": retweet_count,
            "reply_count": reply_count,
            "quote_count": 2,
        },
        "lang": "en",
    }


def _make_twitter_response(tweets):
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "data": tweets,
        "meta": {"result_count": len(tweets)},
    }
    return mock_resp


def _provider(**kwargs):
    kwargs.setdefault("bearer_token", "test_bearer_token")
    kwargs.setdefault("cache_ttl", 1)
    return TwitterSentimentProvider(**kwargs)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestTwitterSentimentProvider:

    @patch("bot.sentiment.twitter_provider.requests.get")
    def test_returns_sentiment_data(self, mock_get):
        """Provider converts API tweets into SentimentData objects."""
        tweets = [
            _make_tweet("Bitcoin rally continues $BTC", like_count=100),
            _make_tweet("ETH showing strength $ETH", like_count=50),
        ]
        mock_get.return_value = _make_twitter_response(tweets)

        provider = _provider()
        results = provider.get_sentiment("BTC")

        assert len(results) == 2
        assert all(isinstance(r, SentimentData) for r in results)
        assert all(r.asset == "BTC" for r in results)
        assert all(r.source == "twitter" for r in results)
        assert all(-1.0 <= r.score <= 1.0 for r in results)
        assert all(0.0 <= r.confidence <= 1.0 for r in results)

    @patch("bot.sentiment.twitter_provider.requests.get")
    def test_asset_normalisation(self, mock_get):
        """Provider normalises 'BTC/USDT:USDT' to 'BTC'."""
        mock_get.return_value = _make_twitter_response(
            [_make_tweet("$BTC pumping!")]
        )
        provider = _provider()
        results = provider.get_sentiment("BTC/USDT:USDT")

        assert results[0].asset == "BTC"
        # Verify the correct query was used (BTC query)
        call_params = mock_get.call_args[1]["params"]
        assert "BTC" in call_params["query"] or "$BTC" in call_params["query"]

    @patch("bot.sentiment.twitter_provider.requests.get")
    def test_caching(self, mock_get):
        """Second call within TTL returns cached data, no extra HTTP call."""
        tweets = [_make_tweet()]
        mock_get.return_value = _make_twitter_response(tweets)

        provider = _provider(cache_ttl=60)
        provider.get_sentiment("BTC")
        provider.get_sentiment("BTC")

        assert mock_get.call_count == 1

    @patch("bot.sentiment.twitter_provider.requests.get")
    def test_cache_expires(self, mock_get):
        """After TTL expiry, a new HTTP call is made."""
        tweets = [_make_tweet()]
        mock_get.return_value = _make_twitter_response(tweets)

        provider = _provider(cache_ttl=1)
        provider.get_sentiment("BTC")
        time.sleep(1.1)
        provider.get_sentiment("BTC")

        assert mock_get.call_count == 2

    @patch("bot.sentiment.twitter_provider.requests.get")
    def test_http_error_returns_empty(self, mock_get):
        """Network errors return an empty list (graceful fallback)."""
        import requests as req_module
        mock_get.side_effect = req_module.RequestException("network error")

        provider = _provider()
        results = provider.get_sentiment("BTC")

        assert results == []

    def test_no_bearer_token_returns_empty(self):
        """Provider returns empty list immediately when no token configured."""
        provider = TwitterSentimentProvider(bearer_token="")
        results = provider.get_sentiment("BTC")
        assert results == []

    @patch("bot.sentiment.twitter_provider.requests.get")
    def test_unknown_asset_returns_empty(self, mock_get):
        """Unknown asset without a query mapping returns empty list."""
        provider = _provider()
        results = provider.get_sentiment("UNKNOWN_COIN")
        assert results == []
        mock_get.assert_not_called()

    @patch("bot.sentiment.twitter_provider.requests.get")
    def test_empty_api_response_returns_empty(self, mock_get):
        """API returning no data field returns empty list."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {}
        mock_get.return_value = mock_resp

        provider = _provider()
        results = provider.get_sentiment("ETH")
        assert results == []

    @patch("bot.sentiment.twitter_provider.requests.get")
    def test_multi_asset_sentiment(self, mock_get):
        """get_multi_asset_sentiment fetches all requested assets."""
        mock_get.return_value = _make_twitter_response(
            [_make_tweet("Crypto pumping")]
        )
        provider = _provider()
        results = provider.get_multi_asset_sentiment(["BTC", "ETH", "SOL"])

        assert set(results.keys()) == {"BTC", "ETH", "SOL"}
        assert mock_get.call_count == 3

    @patch("bot.sentiment.twitter_provider.requests.get")
    def test_positive_sentiment_tweet(self, mock_get):
        """Clearly positive tweet yields positive compound score."""
        mock_get.return_value = _make_twitter_response(
            [_make_tweet("Bitcoin is amazing! Great buy opportunity! 🚀🎉")]
        )
        provider = _provider()
        results = provider.get_sentiment("BTC")
        assert results[0].score > 0

    @patch("bot.sentiment.twitter_provider.requests.get")
    def test_negative_sentiment_tweet(self, mock_get):
        """Clearly negative tweet yields negative compound score."""
        mock_get.return_value = _make_twitter_response(
            [_make_tweet("Bitcoin is crashing! Terrible news! $BTC disaster")]
        )
        provider = _provider()
        results = provider.get_sentiment("BTC")
        assert results[0].score < 0

    @patch("bot.sentiment.twitter_provider.requests.get")
    def test_engagement_boosts_confidence(self, mock_get):
        """High-engagement tweet has higher confidence than low-engagement."""
        high_eng = _make_tweet("$BTC moon!", like_count=1000, retweet_count=500)
        low_eng = _make_tweet("$BTC ok", like_count=0, retweet_count=0)
        mock_get.return_value = _make_twitter_response([high_eng])
        provider = _provider()
        high_result = provider.get_sentiment("BTC")[0]

        # Clear cache and fetch low engagement
        provider._cache.clear()
        mock_get.return_value = _make_twitter_response([low_eng])
        low_result = provider.get_sentiment("BTC")[0]

        assert high_result.confidence >= low_result.confidence

    @patch("bot.sentiment.twitter_provider.requests.get")
    def test_headline_truncated_to_200_chars(self, mock_get):
        """Headline is truncated to 200 characters."""
        long_text = "x" * 300
        mock_get.return_value = _make_twitter_response([_make_tweet(long_text)])
        provider = _provider()
        results = provider.get_sentiment("BTC")
        assert len(results[0].headline) <= 200

    @patch("bot.sentiment.twitter_provider.requests.get")
    def test_malformed_tweet_skipped(self, mock_get):
        """Tweets with empty text are skipped."""
        tweets = [
            {"id": "1", "text": "", "public_metrics": {}},
            _make_tweet("Normal tweet $BTC"),
        ]
        mock_get.return_value = _make_twitter_response(tweets)
        provider = _provider()
        results = provider.get_sentiment("BTC")
        # Only the non-empty tweet should survive
        assert len(results) == 1
