"""
Tests for the ML Backtesting Framework and new ML API endpoints.

Covers:
- MLBacktester: demo result, metric calculation, edge cases
- API endpoints: /api/ml/status, /api/ml/feature-importance,
  POST /api/ml/backtest, /api/ml/predictions/recent
"""
from __future__ import annotations

import os
import pytest
import numpy as np
import pandas as pd

from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def ohlcv_df() -> pd.DataFrame:
    """250-row synthetic OHLCV DataFrame with a DatetimeIndex."""
    rng = np.random.default_rng(0)
    n = 250
    dates = pd.date_range("2025-01-01", periods=n, freq="5min")
    close = 40_000 + np.cumsum(rng.standard_normal(n) * 100)
    close = np.clip(close, 1.0, None)
    df = pd.DataFrame(
        {
            "open": close + rng.standard_normal(n) * 40,
            "high": close + np.abs(rng.standard_normal(n) * 80),
            "low": close - np.abs(rng.standard_normal(n) * 80),
            "close": close,
            "volume": rng.uniform(500, 5_000, n),
        },
        index=dates,
    )
    df["high"] = df[["open", "close", "high"]].max(axis=1)
    df["low"] = df[["open", "close", "low"]].min(axis=1)
    return df


@pytest.fixture
def client():
    """FastAPI test client."""
    from tv_gateway.main import app
    return TestClient(app)


# ---------------------------------------------------------------------------
# MLBacktester unit tests
# ---------------------------------------------------------------------------


class TestMLBacktesterDemoMode:
    """Tests that run without a real ML model (demo/mock mode)."""

    def test_import(self):
        from bot.ml.backtester import MLBacktester
        assert MLBacktester is not None

    def test_backtester_init_no_model(self, monkeypatch):
        monkeypatch.setenv("ML_MODEL_PATH", "")
        from bot.ml.backtester import MLBacktester
        bt = MLBacktester(model_path="")
        assert not bt.model_loaded

    def test_run_returns_demo_result(self, monkeypatch):
        monkeypatch.setenv("ML_MODEL_PATH", "")
        from bot.ml.backtester import MLBacktester, BacktestResult
        bt = MLBacktester(model_path="")
        result = bt.run()
        assert isinstance(result, BacktestResult)
        assert result.is_demo is True

    def test_demo_result_fields(self, monkeypatch):
        monkeypatch.setenv("ML_MODEL_PATH", "")
        from bot.ml.backtester import MLBacktester
        bt = MLBacktester(model_path="")
        result = bt.run(pair="ETH/USDT:USDT", timeframe="15m")
        assert 0.0 <= result.precision <= 1.0
        assert 0.0 <= result.recall <= 1.0
        assert 0.0 <= result.f1_score <= 1.0
        assert 0.0 <= result.accuracy <= 1.0
        assert result.total_predictions > 0
        assert result.pair == "ETH/USDT:USDT"
        assert result.timeframe == "15m"

    def test_demo_result_confusion_matrix(self, monkeypatch):
        monkeypatch.setenv("ML_MODEL_PATH", "")
        from bot.ml.backtester import MLBacktester
        bt = MLBacktester(model_path="")
        result = bt.run()
        cm = result.confusion_matrix
        assert cm.tp >= 0
        assert cm.fp >= 0
        assert cm.tn >= 0
        assert cm.fn >= 0

    def test_demo_result_rolling_accuracy(self, monkeypatch):
        monkeypatch.setenv("ML_MODEL_PATH", "")
        from bot.ml.backtester import MLBacktester
        bt = MLBacktester(model_path="")
        result = bt.run()
        assert len(result.rolling_accuracy) > 0
        for point in result.rolling_accuracy:
            assert 0.0 <= point.accuracy <= 1.0
            assert isinstance(point.window_start, str)

    def test_demo_result_confidence_distribution(self, monkeypatch):
        monkeypatch.setenv("ML_MODEL_PATH", "")
        from bot.ml.backtester import MLBacktester
        bt = MLBacktester(model_path="")
        result = bt.run()
        assert len(result.confidence_distribution) > 0
        for bucket in result.confidence_distribution:
            assert bucket.count >= 0
            assert "-" in bucket.bucket

    def test_demo_feature_importance(self, monkeypatch):
        monkeypatch.setenv("ML_MODEL_PATH", "")
        from bot.ml.backtester import MLBacktester
        bt = MLBacktester(model_path="")
        features, method = bt.get_feature_importance()
        assert method == "demo"
        assert len(features) > 0
        for f in features:
            assert "name" in f
            assert "importance" in f
            assert f["importance"] >= 0.0

    def test_demo_to_dict(self, monkeypatch):
        monkeypatch.setenv("ML_MODEL_PATH", "")
        from bot.ml.backtester import MLBacktester
        bt = MLBacktester(model_path="")
        result = bt.run()
        d = result.to_dict()
        required_keys = {
            "precision", "recall", "f1_score", "accuracy",
            "total_predictions", "confusion_matrix",
            "profit_with_ml", "profit_without_ml", "profit_improvement_pct",
            "rolling_accuracy", "confidence_distribution",
            "feature_importance", "feature_importance_method", "is_demo",
        }
        assert required_keys.issubset(d.keys())

    def test_run_with_date_params(self, monkeypatch):
        monkeypatch.setenv("ML_MODEL_PATH", "")
        from bot.ml.backtester import MLBacktester
        bt = MLBacktester(model_path="")
        result = bt.run(start_date="2025-01-01", end_date="2025-12-31")
        assert result.backtest_start == "2025-01-01"
        assert result.backtest_end == "2025-12-31"

    def test_nonexistent_model_path_falls_back_to_demo(self):
        from bot.ml.backtester import MLBacktester
        bt = MLBacktester(model_path="/nonexistent/path/model.joblib")
        assert not bt.model_loaded
        result = bt.run()
        assert result.is_demo is True


class TestMLBacktesterHelpers:
    """Tests for internal helper methods."""

    def test_generate_synthetic_ohlcv(self):
        from bot.ml.backtester import MLBacktester
        df = MLBacktester._generate_synthetic_ohlcv(n=200)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 200
        assert set(df.columns) >= {"open", "high", "low", "close", "volume"}
        # high >= low always
        assert (df["high"] >= df["low"]).all()

    def test_filter_by_date(self, ohlcv_df):
        from bot.ml.backtester import MLBacktester
        # The fixture spans 2025-01-01 00:00 to ~20:45 (250 rows × 5 min).
        # Filter to only the first 4 hours to get a subset.
        filtered = MLBacktester._filter_by_date(ohlcv_df, "2025-01-01", "2025-01-01 04:00")
        assert len(filtered) < len(ohlcv_df)
        assert filtered.index.min() >= pd.Timestamp("2025-01-01")

    def test_filter_by_date_no_bounds(self, ohlcv_df):
        from bot.ml.backtester import MLBacktester
        filtered = MLBacktester._filter_by_date(ohlcv_df, None, None)
        assert len(filtered) == len(ohlcv_df)

    def test_compute_confidence_distribution(self):
        from bot.ml.backtester import MLBacktester
        bt = MLBacktester(model_path="")
        confs = np.array([0.52, 0.65, 0.71, 0.85, 0.92, 0.55, 0.78, 0.61])
        dist = bt._compute_confidence_distribution(confs)
        assert len(dist) == 5
        total = sum(b.count for b in dist)
        assert total == len(confs)

    def test_compute_confusion_matrix(self):
        from bot.ml.backtester import MLBacktester
        bt = MLBacktester(model_path="")
        y_true = np.array(["long", "short", "long", "neutral", "long"])
        y_pred = np.array(["long", "long", "long", "short", "short"])
        cm = bt._compute_confusion_matrix(y_true, y_pred)
        assert cm.tp == 2  # long predicted as long: indices 0 and 2
        assert cm.fn == 1  # long predicted as non-long: index 4
        assert cm.fp == 1  # non-long predicted as long: index 1

    def test_compute_classification_metrics(self):
        from bot.ml.backtester import MLBacktester
        bt = MLBacktester(model_path="")
        y_true = np.array(["long", "long", "short", "neutral"] * 10)
        y_pred = np.array(["long", "short", "short", "neutral"] * 10)
        metrics = bt._compute_classification_metrics(y_true, y_pred)
        assert 0.0 <= metrics["precision"] <= 1.0
        assert 0.0 <= metrics["recall"] <= 1.0
        assert 0.0 <= metrics["f1"] <= 1.0
        assert metrics["accuracy"] == pytest.approx(0.75)

    def test_demo_build_result_module_level(self):
        from bot.ml.backtester import _build_demo_result
        result = _build_demo_result("BTC/USDT:USDT", "5m", "2025-01-01", "2025-12-31")
        assert result.is_demo
        assert result.pair == "BTC/USDT:USDT"
        assert result.timeframe == "5m"

    def test_make_demo_feature_importance_module_level(self):
        from bot.ml.backtester import _make_demo_feature_importance
        fi = _make_demo_feature_importance()
        assert len(fi) > 0
        importances = [f["importance"] for f in fi]
        # Should be sorted descending
        assert importances == sorted(importances, reverse=True)


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


class TestMLStatusEndpoint:
    def test_status_200(self, client):
        response = client.get("/api/ml/status")
        assert response.status_code == 200

    def test_status_schema(self, client):
        data = client.get("/api/ml/status").json()
        assert "model_loaded" in data
        assert "features_count" in data
        assert "is_demo" in data
        assert isinstance(data["model_loaded"], bool)
        assert isinstance(data["features_count"], int)
        assert data["features_count"] > 0

    def test_status_no_model_is_demo(self, client, monkeypatch):
        monkeypatch.setenv("ML_MODEL_PATH", "")
        response = client.get("/api/ml/status")
        data = response.json()
        assert data["is_demo"] is True
        assert data["model_loaded"] is False


class TestMLFeatureImportanceEndpoint:
    def test_feature_importance_200(self, client):
        response = client.get("/api/ml/feature-importance")
        assert response.status_code == 200

    def test_feature_importance_schema(self, client):
        data = client.get("/api/ml/feature-importance").json()
        assert "features" in data
        assert "method" in data
        assert isinstance(data["features"], list)
        assert len(data["features"]) > 0

    def test_feature_importance_items_have_required_keys(self, client):
        data = client.get("/api/ml/feature-importance").json()
        for f in data["features"]:
            assert "name" in f
            assert "importance" in f
            assert f["importance"] >= 0.0

    def test_feature_importance_no_model_returns_demo(self, client, monkeypatch):
        monkeypatch.setenv("ML_MODEL_PATH", "")
        data = client.get("/api/ml/feature-importance").json()
        assert data["method"] in ("demo", "built_in", "shap")


class TestMLBacktestEndpoint:
    def test_backtest_post_200(self, client):
        response = client.post(
            "/api/ml/backtest",
            json={"start_date": "2025-01-01", "end_date": "2025-12-31",
                  "pair": "BTC/USDT:USDT", "timeframe": "5m"},
        )
        assert response.status_code == 200

    def test_backtest_response_schema(self, client):
        data = client.post("/api/ml/backtest", json={}).json()
        assert data["success"] is True
        metrics = data["metrics"]
        for key in ("precision", "recall", "f1_score", "accuracy",
                    "total_predictions", "confusion_matrix",
                    "profit_with_ml", "profit_without_ml",
                    "rolling_accuracy", "confidence_distribution"):
            assert key in metrics, f"Missing key: {key}"

    def test_backtest_confusion_matrix_keys(self, client):
        data = client.post("/api/ml/backtest", json={}).json()
        cm = data["metrics"]["confusion_matrix"]
        for key in ("tp", "fp", "tn", "fn"):
            assert key in cm

    def test_backtest_rolling_accuracy_list(self, client):
        data = client.post("/api/ml/backtest", json={}).json()
        ra = data["metrics"]["rolling_accuracy"]
        assert isinstance(ra, list)
        if ra:
            assert "window_start" in ra[0]
            assert "accuracy" in ra[0]

    def test_backtest_empty_body(self, client):
        response = client.post("/api/ml/backtest", content=b"")
        assert response.status_code == 200

    def test_backtest_no_model_returns_demo(self, client, monkeypatch):
        monkeypatch.setenv("ML_MODEL_PATH", "")
        data = client.post("/api/ml/backtest", json={}).json()
        assert data["success"] is True
        assert data["metrics"]["is_demo"] is True


class TestMLRecentPredictionsEndpoint:
    def test_predictions_200(self, client):
        response = client.get("/api/ml/predictions/recent")
        assert response.status_code == 200

    def test_predictions_schema(self, client):
        data = client.get("/api/ml/predictions/recent").json()
        assert "predictions" in data
        assert "total" in data
        assert "is_demo" in data
        assert isinstance(data["predictions"], list)

    def test_predictions_no_model_returns_demo_data(self, client, monkeypatch):
        monkeypatch.setenv("ML_MODEL_PATH", "")
        data = client.get("/api/ml/predictions/recent").json()
        assert data["is_demo"] is True
        assert len(data["predictions"]) > 0

    def test_predictions_item_schema(self, client, monkeypatch):
        monkeypatch.setenv("ML_MODEL_PATH", "")
        data = client.get("/api/ml/predictions/recent").json()
        pred = data["predictions"][0]
        for key in ("timestamp", "pair", "signal", "confidence",
                    "actual_outcome", "features_used"):
            assert key in pred

    def test_predictions_limit_param(self, client, monkeypatch):
        monkeypatch.setenv("ML_MODEL_PATH", "")
        data = client.get("/api/ml/predictions/recent?limit=5").json()
        assert len(data["predictions"]) <= 5
