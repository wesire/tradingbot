"""
Tests for the ML signal enhancement module.

Covers:
- FeatureEngineer: feature generation, NaN handling, column validation
- SignalClassifier: train/predict/save/load cycle, feature importance
- ModelExplainer: format_explanation (SHAP backend only when installed)
- ModelMonitor: logging, reporting, calibration
"""
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def ohlcv_df() -> pd.DataFrame:
    """
    100-row OHLCV DataFrame with enough data for all rolling windows
    (requires at least 50 bars for EMA-50).
    """
    np.random.seed(0)
    n = 150
    dates = pd.date_range("2024-01-01", periods=n, freq="5min")
    close = 40_000 + np.cumsum(np.random.randn(n) * 80)
    df = pd.DataFrame(
        {
            "open": close + np.random.randn(n) * 30,
            "high": close + np.abs(np.random.randn(n) * 60),
            "low": close - np.abs(np.random.randn(n) * 60),
            "close": close,
            "volume": np.random.uniform(500, 5_000, n),
        },
        index=dates,
    )
    # Ensure high >= open/close and low <= open/close
    df["high"] = df[["open", "close", "high"]].max(axis=1)
    df["low"] = df[["open", "close", "low"]].min(axis=1)
    return df


@pytest.fixture
def feature_engineer():
    from bot.ml.feature_engineer import FeatureEngineer
    return FeatureEngineer()


@pytest.fixture
def features_df(feature_engineer, ohlcv_df):
    return feature_engineer.transform(ohlcv_df)


# ---------------------------------------------------------------------------
# FeatureEngineer tests
# ---------------------------------------------------------------------------

class TestFeatureEngineer:
    def test_returns_dataframe(self, feature_engineer, ohlcv_df):
        result = feature_engineer.transform(ohlcv_df)
        assert isinstance(result, pd.DataFrame)

    def test_no_nan_in_output(self, features_df):
        assert not features_df.isnull().any().any(), "Output contains NaN values"

    def test_expected_columns_present(self, features_df):
        from bot.ml.feature_engineer import FeatureEngineer
        expected = set(FeatureEngineer.FEATURE_NAMES)
        assert expected.issubset(set(features_df.columns))

    def test_feature_names_property(self, feature_engineer):
        names = feature_engineer.feature_names
        assert isinstance(names, list)
        assert len(names) > 0

    def test_rsi_in_valid_range(self, features_df):
        assert (features_df["rsi_14"] >= 0).all()
        assert (features_df["rsi_14"] <= 100).all()

    def test_ema_cross_values_are_sign(self, features_df):
        unique = set(features_df["ema_cross_9_21"].unique())
        assert unique.issubset({-1.0, 0.0, 1.0})

    def test_missing_columns_raises(self, feature_engineer):
        bad_df = pd.DataFrame({"close": [1, 2, 3]})
        with pytest.raises(ValueError, match="missing columns"):
            feature_engineer.transform(bad_df)

    def test_volume_ratio_positive(self, features_df):
        assert (features_df["volume_ratio"] > 0).all()

    def test_build_labels(self, ohlcv_df):
        from bot.ml.feature_engineer import FeatureEngineer
        labels, ret = FeatureEngineer.build_labels(ohlcv_df["close"])
        assert set(labels.unique()).issubset({"long", "short", "neutral"})
        assert len(labels) == len(ohlcv_df)

    def test_higher_tf_not_included_by_default(self, features_df):
        from bot.ml.feature_engineer import FeatureEngineer
        htf_cols = set(FeatureEngineer.HTF_FEATURE_NAMES)
        assert not htf_cols.intersection(set(features_df.columns))


# ---------------------------------------------------------------------------
# SignalClassifier tests
# ---------------------------------------------------------------------------

class TestSignalClassifier:
    @pytest.fixture
    def classifier(self, tmp_path):
        from bot.ml.signal_classifier import SignalClassifier
        return SignalClassifier(model_dir=str(tmp_path), min_confidence=0.0)

    @pytest.fixture
    def trained_classifier(self, classifier, features_df):
        from bot.ml.feature_engineer import FeatureEngineer
        # Build target labels aligned with feature rows
        close = features_df.index.map(
            lambda ts: features_df.loc[ts, "rsi_14"]  # dummy – using close proxy
        )
        # Synthetic labels: 50 long, 50 short, rest neutral
        n = len(features_df)
        labels_arr = ["neutral"] * n
        for i in range(min(50, n)):
            labels_arr[i] = "long" if i % 2 == 0 else "short"
        y = pd.Series(labels_arr, index=features_df.index)
        classifier.train(features_df, y, cv_folds=2)
        return classifier

    def test_is_fitted_after_train(self, trained_classifier):
        assert trained_classifier.is_fitted

    def test_predict_returns_valid_signal(self, trained_classifier, features_df):
        signal, confidence = trained_classifier.predict(features_df)
        assert signal in ("long", "short", "neutral")
        assert 0.0 <= confidence <= 1.0

    def test_predict_proba_sums_to_one(self, trained_classifier, features_df):
        proba = trained_classifier.predict_proba(features_df)
        assert abs(sum(proba.values()) - 1.0) < 1e-5
        assert set(proba.keys()) == {"long", "short", "neutral"}

    def test_train_returns_metrics(self, classifier, features_df):
        n = len(features_df)
        # Use mixed labels so XGBoost sees all classes in every CV fold
        cycle = ["long", "short", "neutral"]
        labels_arr = [cycle[i % 3] for i in range(n)]
        y = pd.Series(labels_arr, index=features_df.index)
        metrics = classifier.train(features_df, y, cv_folds=2)
        assert "accuracy_mean" in metrics
        assert 0.0 <= metrics["accuracy_mean"] <= 1.0

    def test_save_and_load(self, trained_classifier, features_df, tmp_path):
        path = str(tmp_path / "model.joblib")
        saved_path = trained_classifier.save_model(path)
        assert os.path.exists(saved_path)

        from bot.ml.signal_classifier import SignalClassifier
        new_clf = SignalClassifier(model_dir=str(tmp_path), min_confidence=0.0)
        new_clf.load_model(saved_path)
        assert new_clf.is_fitted

        sig, conf = new_clf.predict(features_df)
        assert sig in ("long", "short", "neutral")

    def test_feature_importance(self, trained_classifier):
        importance = trained_classifier.get_feature_importance()
        assert isinstance(importance, dict)
        assert len(importance) > 0
        assert all(v >= 0 for v in importance.values())

    def test_predict_before_train_raises(self, classifier, features_df):
        with pytest.raises(RuntimeError, match="not fitted"):
            classifier.predict(features_df)

    def test_latest_pointer_written(self, trained_classifier, tmp_path):
        trained_classifier.save_model()
        ptr = tmp_path / "signal_classifier_latest.json"
        assert ptr.exists()
        data = json.loads(ptr.read_text())
        assert "path" in data


# ---------------------------------------------------------------------------
# ModelExplainer tests
# ---------------------------------------------------------------------------

class TestModelExplainer:
    def test_format_explanation_no_shap(self):
        from bot.ml.explainer import ModelExplainer
        explainer = ModelExplainer()
        result = explainer.format_explanation({}, ["rsi_14", "macd_hist"])
        assert "No SHAP" in result

    def test_format_explanation_with_values(self):
        from bot.ml.explainer import ModelExplainer
        explainer = ModelExplainer()
        shap_vals = {"rsi_14": 0.4, "macd_hist": -0.3, "vol_20": 0.1}
        result = explainer.format_explanation(shap_vals, list(shap_vals.keys()), top_n=2)
        assert "rsi_14" in result
        assert "macd_hist" in result
        assert "Top drivers" in result

    def test_format_explanation_top_n_limit(self):
        from bot.ml.explainer import ModelExplainer
        explainer = ModelExplainer()
        shap_vals = {f"feat_{i}": float(i) for i in range(10)}
        result = explainer.format_explanation(shap_vals, list(shap_vals.keys()), top_n=3)
        assert result.count(",") == 2  # 3 items = 2 commas


# ---------------------------------------------------------------------------
# ModelMonitor tests
# ---------------------------------------------------------------------------

class TestModelMonitor:
    @pytest.fixture
    def monitor(self, tmp_path):
        from bot.ml.model_monitor import ModelMonitor
        return ModelMonitor(
            log_path=str(tmp_path / "monitor.jsonl"),
            accuracy_threshold=0.5,
            window=50,
        )

    def test_log_prediction_creates_file(self, monitor, tmp_path):
        monitor.log_prediction("long", "long", 0.8)
        log = tmp_path / "monitor.jsonl"
        assert log.exists()

    def test_get_performance_report_empty(self, monitor):
        report = monitor.get_performance_report()
        assert report["n_predictions"] == 0
        assert report["accuracy"] is None

    def test_accuracy_computed_correctly(self, monitor):
        for _ in range(8):
            monitor.log_prediction("long", "long", 0.9)
        for _ in range(2):
            monitor.log_prediction("long", "short", 0.6)

        report = monitor.get_performance_report()
        assert report["n_predictions"] == 10
        assert abs(report["accuracy"] - 0.8) < 0.01

    def test_prediction_distribution(self, monitor):
        for _ in range(6):
            monitor.log_prediction("long", "long", 0.8)
        for _ in range(4):
            monitor.log_prediction("short", "short", 0.7)

        report = monitor.get_performance_report()
        dist = report["prediction_distribution"]
        assert abs(dist.get("long", 0) - 0.6) < 0.01
        assert abs(dist.get("short", 0) - 0.4) < 0.01

    def test_calibration_buckets(self, monitor):
        for _ in range(10):
            monitor.log_prediction("long", "long", 0.85)

        report = monitor.get_performance_report()
        assert isinstance(report["confidence_calibration"], dict)

    def test_window_limits_entries(self, monitor):
        for i in range(60):
            monitor.log_prediction("long", "long", 0.7)

        assert len(monitor._recent) <= monitor.window

    def test_log_roundtrip(self, monitor, tmp_path):
        """Entries written to disk should be loadable by a fresh monitor."""
        monitor.log_prediction("short", "neutral", 0.55)
        monitor.log_prediction("neutral", "neutral", 0.60)

        from bot.ml.model_monitor import ModelMonitor
        monitor2 = ModelMonitor(
            log_path=str(tmp_path / "monitor.jsonl"), window=50
        )
        assert len(monitor2._recent) == 2
