"""
Unit tests for Fear & Greed Index provider.
"""
import pytest
from unittest.mock import MagicMock, patch

from bot.sentiment.fear_greed_provider import FearGreedProvider, _map_fng_to_score


# ---------------------------------------------------------------------------
# _map_fng_to_score
# ---------------------------------------------------------------------------

class TestMapFngToScore:
    def test_extreme_fear_lower_bound(self):
        assert _map_fng_to_score(0) == pytest.approx(-1.0)

    def test_extreme_fear_upper_bound(self):
        assert _map_fng_to_score(25) == pytest.approx(-0.5)

    def test_fear_midpoint(self):
        score = _map_fng_to_score(35)
        assert -0.5 <= score <= -0.2

    def test_neutral(self):
        score = _map_fng_to_score(50)
        assert -0.2 <= score <= 0.2

    def test_greed(self):
        score = _map_fng_to_score(65)
        assert 0.2 <= score <= 0.5

    def test_extreme_greed(self):
        assert _map_fng_to_score(100) == pytest.approx(1.0)

    def test_clamps_below_zero(self):
        assert _map_fng_to_score(-10) == pytest.approx(-1.0)

    def test_clamps_above_100(self):
        assert _map_fng_to_score(150) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_fng_response(value: int, classification: str = "Neutral"):
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "data": [
            {
                "value": str(value),
                "value_classification": classification,
                "timestamp": "1700000000",
            }
        ]
    }
    return mock_resp


# ---------------------------------------------------------------------------
# FearGreedProvider
# ---------------------------------------------------------------------------

class TestFearGreedProvider:
    def test_get_sentiment_happy_path(self):
        provider = FearGreedProvider()
        with patch("requests.get", return_value=_mock_fng_response(50, "Neutral")):
            results = provider.get_sentiment("BTC", lookback_hours=24)
        assert len(results) == 1
        sd = results[0]
        assert sd.asset == "BTC"
        assert -0.2 <= sd.score <= 0.2
        assert sd.source == "alternative.me/fng"

    def test_get_sentiment_extreme_fear(self):
        provider = FearGreedProvider()
        with patch("requests.get", return_value=_mock_fng_response(10, "Extreme Fear")):
            results = provider.get_sentiment("ETH", lookback_hours=24)
        assert results[0].score <= -0.5

    def test_get_sentiment_extreme_greed(self):
        provider = FearGreedProvider()
        with patch("requests.get", return_value=_mock_fng_response(90, "Extreme Greed")):
            results = provider.get_sentiment("SOL", lookback_hours=24)
        assert results[0].score >= 0.5

    def test_get_sentiment_api_error_returns_empty(self):
        provider = FearGreedProvider()
        with patch("requests.get", side_effect=Exception("timeout")):
            results = provider.get_sentiment("BTC", lookback_hours=24)
        assert results == []

    def test_get_multi_asset_sentiment(self):
        provider = FearGreedProvider()
        with patch("requests.get", return_value=_mock_fng_response(50)):
            result = provider.get_multi_asset_sentiment(["BTC", "ETH", "SOL"])
        assert set(result.keys()) == {"BTC", "ETH", "SOL"}
        for asset, sds in result.items():
            assert len(sds) == 1
            assert sds[0].asset == asset

    def test_get_current_value(self):
        provider = FearGreedProvider()
        with patch("requests.get", return_value=_mock_fng_response(72)):
            value = provider.get_current_value()
        assert value == 72

    def test_get_current_value_api_error(self):
        provider = FearGreedProvider()
        with patch("requests.get", side_effect=Exception("network error")):
            value = provider.get_current_value()
        assert value is None

    def test_is_extreme_fear(self):
        provider = FearGreedProvider(extreme_fear_threshold=25)
        with patch("requests.get", return_value=_mock_fng_response(15)):
            assert provider.is_extreme_fear() is True

    def test_is_not_extreme_fear(self):
        provider = FearGreedProvider(extreme_fear_threshold=25)
        with patch("requests.get", return_value=_mock_fng_response(50)):
            assert provider.is_extreme_fear() is False

    def test_is_extreme_greed(self):
        provider = FearGreedProvider(extreme_greed_threshold=75)
        with patch("requests.get", return_value=_mock_fng_response(90)):
            assert provider.is_extreme_greed() is True

    def test_should_pause_longs_delegates(self):
        provider = FearGreedProvider()
        with patch.object(provider, "is_extreme_fear", return_value=True):
            assert provider.should_pause_longs() is True

    def test_should_pause_shorts_delegates(self):
        provider = FearGreedProvider()
        with patch.object(provider, "is_extreme_greed", return_value=True):
            assert provider.should_pause_shorts() is True

    def test_caching(self):
        provider = FearGreedProvider(cache_ttl=60)
        with patch("requests.get", return_value=_mock_fng_response(50)) as mock_get:
            provider.get_sentiment("BTC")
            provider.get_sentiment("ETH")  # Should use cache
        assert mock_get.call_count == 1  # Only one real HTTP call

    def test_get_historical_values(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "data": [
                {"value": "50", "value_classification": "Neutral", "timestamp": "1700000000"},
                {"value": "30", "value_classification": "Fear", "timestamp": "1699900000"},
            ]
        }
        provider = FearGreedProvider()
        with patch("requests.get", return_value=mock_resp):
            history = provider.get_historical_values(days=2)
        assert len(history) == 2
        assert history[0]["value"] == 50
        assert "score" in history[0]
