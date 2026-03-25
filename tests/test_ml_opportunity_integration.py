"""
Tests for ML enrichment of OpportunityScorer.

Verifies that:
- Opportunity dataclass has ml_confidence, ml_signal, ml_explanation fields
- Fields are None when no ML components are configured (graceful degradation)
- Fields are populated when ML components are provided
"""
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from bot.opportunities.scorer import Opportunity, OpportunityScorer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TECH_DATA = {
    "rsi": 30,
    "price_vs_ema": True,
    "filters_passed": True,
    "volume_above_avg": True,
    "close": 40000.0,
    "atr": 200.0,
}

REGIME_DATA = {
    "bullish": True,
    "bearish": False,
    "adx": 35,
}


def make_ohlcv(n: int = 150) -> pd.DataFrame:
    np.random.seed(1)
    dates = pd.date_range("2024-01-01", periods=n, freq="5min")
    close = 40_000 + np.cumsum(np.random.randn(n) * 80)
    df = pd.DataFrame(
        {
            "open": close + np.random.randn(n) * 30,
            "high": close + np.abs(np.random.randn(n) * 60),
            "low": close - np.abs(np.random.randn(n) * 60),
            "close": close,
            "volume": np.random.uniform(500, 5000, n),
        },
        index=dates,
    )
    df["high"] = df[["open", "close", "high"]].max(axis=1)
    df["low"] = df[["open", "close", "low"]].min(axis=1)
    return df


# ---------------------------------------------------------------------------
# Tests: Opportunity dataclass
# ---------------------------------------------------------------------------

class TestOpportunityDataclass:
    def test_ml_fields_default_to_none(self):
        opp = Opportunity(
            pair="BTC/USDT",
            side="long",
            confidence=0.7,
            entry_zone="39000-40000",
            invalidation="38000",
            risk_reward=2.0,
            timeframe="5m",
            technical_score=0.8,
            regime_score=0.7,
            sentiment_score=0.6,
            liquidity_score=0.7,
            rationale=["test"],
            last_updated="2024-01-01T00:00:00",
        )
        assert opp.ml_confidence is None
        assert opp.ml_signal is None
        assert opp.ml_explanation is None

    def test_ml_fields_in_to_dict(self):
        opp = Opportunity(
            pair="BTC/USDT",
            side="long",
            confidence=0.7,
            entry_zone="39000-40000",
            invalidation="38000",
            risk_reward=2.0,
            timeframe="5m",
            technical_score=0.8,
            regime_score=0.7,
            sentiment_score=0.6,
            liquidity_score=0.7,
            rationale=["test"],
            last_updated="2024-01-01T00:00:00",
            ml_confidence=0.82,
            ml_signal="long",
            ml_explanation="Top drivers: rsi_14 (+0.4)",
        )
        d = opp.to_dict()
        assert d["ml_confidence"] == 0.82
        assert d["ml_signal"] == "long"
        assert "rsi_14" in d["ml_explanation"]


# ---------------------------------------------------------------------------
# Tests: OpportunityScorer without ML
# ---------------------------------------------------------------------------

class TestOpportunityScorerNoML:
    def test_score_returns_opportunity_without_ml(self):
        scorer = OpportunityScorer()
        opp = scorer.score_opportunity(
            pair="BTC/USDT",
            timeframe="5m",
            technical_data=TECH_DATA,
            regime_data=REGIME_DATA,
        )
        assert opp is not None
        assert opp.ml_confidence is None
        assert opp.ml_signal is None
        assert opp.ml_explanation is None

    def test_score_with_ohlcv_but_no_classifier(self):
        scorer = OpportunityScorer()
        df = make_ohlcv()
        opp = scorer.score_opportunity(
            pair="BTC/USDT",
            timeframe="5m",
            technical_data=TECH_DATA,
            regime_data=REGIME_DATA,
            ohlcv_df=df,
        )
        assert opp is not None
        assert opp.ml_confidence is None


# ---------------------------------------------------------------------------
# Tests: OpportunityScorer with ML components (mocked)
# ---------------------------------------------------------------------------

class TestOpportunityScorerWithML:
    @pytest.fixture
    def mock_classifier(self):
        clf = MagicMock()
        clf.predict.return_value = ("long", 0.78)
        clf._model = MagicMock()
        return clf

    @pytest.fixture
    def mock_feature_engineer(self):
        import pandas as pd
        fe = MagicMock()
        fe.transform.return_value = pd.DataFrame(
            {"rsi_14": [55.0], "macd_hist": [0.1]},
            index=pd.date_range("2024-01-01", periods=1, freq="5min"),
        )
        fe.feature_names = ["rsi_14", "macd_hist"]
        return fe

    def test_ml_fields_populated(self, mock_classifier, mock_feature_engineer):
        scorer = OpportunityScorer(
            ml_classifier=mock_classifier,
            feature_engineer=mock_feature_engineer,
        )
        df = make_ohlcv()
        opp = scorer.score_opportunity(
            pair="BTC/USDT",
            timeframe="5m",
            technical_data=TECH_DATA,
            regime_data=REGIME_DATA,
            ohlcv_df=df,
        )
        assert opp is not None
        assert opp.ml_signal == "long"
        assert abs(opp.ml_confidence - 0.78) < 0.01

    def test_ml_error_is_graceful(self, mock_feature_engineer):
        clf = MagicMock()
        clf.predict.side_effect = RuntimeError("inference error")
        clf._model = MagicMock()

        scorer = OpportunityScorer(
            ml_classifier=clf,
            feature_engineer=mock_feature_engineer,
        )
        df = make_ohlcv()
        # Should not raise; ML fields should be None
        opp = scorer.score_opportunity(
            pair="BTC/USDT",
            timeframe="5m",
            technical_data=TECH_DATA,
            regime_data=REGIME_DATA,
            ohlcv_df=df,
        )
        assert opp is not None
        assert opp.ml_confidence is None
        assert opp.ml_signal is None

    def test_empty_features_skips_ml(self, mock_classifier):
        import pandas as pd
        fe = MagicMock()
        fe.transform.return_value = pd.DataFrame()  # empty

        scorer = OpportunityScorer(
            ml_classifier=mock_classifier,
            feature_engineer=fe,
        )
        df = make_ohlcv()
        opp = scorer.score_opportunity(
            pair="BTC/USDT",
            timeframe="5m",
            technical_data=TECH_DATA,
            regime_data=REGIME_DATA,
            ohlcv_df=df,
        )
        assert opp is not None
        assert opp.ml_confidence is None
