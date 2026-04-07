"""
ML Backtesting Framework for signal classification evaluation.

Replays historical OHLCV data through the feature engineering pipeline,
generates ML predictions for each window, and produces comprehensive
performance metrics including precision/recall/F1, profit impact,
rolling accuracy, and confidence distributions.

When no trained model is available the backtester returns realistic
demo/mock results so the dashboard always renders correctly.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from bot.data_loader import load_ohlcv_from_file

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional heavy imports
# ---------------------------------------------------------------------------
try:
    from sklearn.metrics import (  # type: ignore
        classification_report,
        confusion_matrix,
        precision_recall_fscore_support,
    )

    _HAS_SKLEARN = True
except ImportError:  # pragma: no cover
    _HAS_SKLEARN = False

try:
    import shap  # type: ignore

    _HAS_SHAP = True
except ImportError:
    _HAS_SHAP = False

try:
    import joblib  # type: ignore

    _HAS_JOBLIB = True
except ImportError:
    _HAS_JOBLIB = False


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ConfidenceBucket:
    bucket: str
    count: int


@dataclass
class RollingAccuracyPoint:
    window_start: str
    accuracy: float


@dataclass
class ConfusionMatrixData:
    tp: int
    fp: int
    tn: int
    fn: int


@dataclass
class BacktestResult:
    """Comprehensive ML backtest metrics."""

    # Classification metrics
    precision: float
    recall: float
    f1_score: float
    accuracy: float
    total_predictions: int

    # Confusion matrix
    confusion_matrix: ConfusionMatrixData

    # Profit impact
    profit_with_ml: float
    profit_without_ml: float
    profit_improvement_pct: float

    # Time-series accuracy
    rolling_accuracy: List[RollingAccuracyPoint]

    # Confidence distribution
    confidence_distribution: List[ConfidenceBucket]

    # Feature importance
    feature_importance: List[Dict[str, Any]]
    feature_importance_method: str

    # Metadata
    is_demo: bool = False
    model_version: Optional[str] = None
    backtest_start: Optional[str] = None
    backtest_end: Optional[str] = None
    pair: Optional[str] = None
    timeframe: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "precision": self.precision,
            "recall": self.recall,
            "f1_score": self.f1_score,
            "accuracy": self.accuracy,
            "total_predictions": self.total_predictions,
            "confusion_matrix": {
                "tp": self.confusion_matrix.tp,
                "fp": self.confusion_matrix.fp,
                "tn": self.confusion_matrix.tn,
                "fn": self.confusion_matrix.fn,
            },
            "profit_with_ml": self.profit_with_ml,
            "profit_without_ml": self.profit_without_ml,
            "profit_improvement_pct": self.profit_improvement_pct,
            "rolling_accuracy": [
                {"window_start": p.window_start, "accuracy": p.accuracy}
                for p in self.rolling_accuracy
            ],
            "confidence_distribution": [
                {"bucket": b.bucket, "count": b.count}
                for b in self.confidence_distribution
            ],
            "feature_importance": self.feature_importance,
            "feature_importance_method": self.feature_importance_method,
            "is_demo": self.is_demo,
            "model_version": self.model_version,
            "backtest_start": self.backtest_start,
            "backtest_end": self.backtest_end,
            "pair": self.pair,
            "timeframe": self.timeframe,
        }


# ---------------------------------------------------------------------------
# Demo / mock result builders
# ---------------------------------------------------------------------------


def _make_demo_rolling_accuracy(n_points: int = 20) -> List[RollingAccuracyPoint]:
    rng = np.random.default_rng(42)
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    points = []
    accuracy = 0.65
    for i in range(n_points):
        accuracy = float(np.clip(accuracy + rng.uniform(-0.04, 0.05), 0.45, 0.90))
        ts = (base + timedelta(days=i * 18)).strftime("%Y-%m-%dT%H:%M:%SZ")
        points.append(RollingAccuracyPoint(window_start=ts, accuracy=round(accuracy, 3)))
    return points


def _make_demo_confidence_distribution() -> List[ConfidenceBucket]:
    rng = np.random.default_rng(42)
    thresholds = ["0.5-0.6", "0.6-0.7", "0.7-0.8", "0.8-0.9", "0.9-1.0"]
    counts = [int(c) for c in rng.integers(200, 1400, size=len(thresholds))]
    return [ConfidenceBucket(bucket=t, count=c) for t, c in zip(thresholds, counts)]


def _make_demo_feature_importance() -> List[Dict[str, Any]]:
    features = [
        ("rsi_14", 0.155),
        ("macd_hist", 0.128),
        ("bb_pct_b", 0.112),
        ("volume_ratio", 0.098),
        ("atr_ratio", 0.087),
        ("ema_cross_9_21", 0.075),
        ("mom_5", 0.072),
        ("rsi_21", 0.065),
        ("vol_20", 0.058),
        ("macd_signal", 0.052),
        ("ema_cross_21_50", 0.047),
        ("bb_width", 0.043),
        ("volume_trend", 0.038),
        ("mom_10", 0.032),
        ("atr_14", 0.028),
    ]
    return [
        {
            "name": name,
            "importance": importance,
            "direction": "positive" if importance > 0.07 else "neutral",
        }
        for name, importance in features
    ]


def _build_demo_result(
    pair: str = "BTC/USDT:USDT",
    timeframe: str = "5m",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> BacktestResult:
    """Return realistic demo metrics when no real model/data is available."""
    return BacktestResult(
        precision=0.651,
        recall=0.583,
        f1_score=0.615,
        accuracy=0.721,
        total_predictions=5000,
        confusion_matrix=ConfusionMatrixData(tp=800, fp=430, tn=2770, fn=1000),
        profit_with_ml=12.5,
        profit_without_ml=8.2,
        profit_improvement_pct=52.4,
        rolling_accuracy=_make_demo_rolling_accuracy(),
        confidence_distribution=_make_demo_confidence_distribution(),
        feature_importance=_make_demo_feature_importance(),
        feature_importance_method="demo",
        is_demo=True,
        model_version=None,
        backtest_start=start_date or "2025-01-01",
        backtest_end=end_date or "2025-12-31",
        pair=pair,
        timeframe=timeframe,
    )


# ---------------------------------------------------------------------------
# MLBacktester
# ---------------------------------------------------------------------------


class MLBacktester:
    """
    Replays historical OHLCV data through the ML pipeline and computes
    comprehensive backtesting metrics.

    Parameters
    ----------
    model_path:
        Path to a saved SignalClassifier ``.joblib`` file.  Defaults to the
        ``ML_MODEL_PATH`` environment variable.  When ``None`` or the file
        does not exist the backtester uses demo data.
    rolling_window:
        Number of predictions per rolling-accuracy window (default 100).
    horizon:
        Forward-return look-ahead bars used to build ground-truth labels.
    """

    def __init__(
        self,
        model_path: Optional[str] = None,
        rolling_window: int = 100,
        horizon: int = 5,
    ) -> None:
        self.model_path = model_path or os.getenv("ML_MODEL_PATH", "")
        self.rolling_window = rolling_window
        self.horizon = horizon
        self._classifier: Any = None
        self._feature_engineer: Any = None
        self._model_loaded = False
        self._try_load_model()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def model_loaded(self) -> bool:
        return self._model_loaded

    def run(
        self,
        ohlcv_df: Optional[pd.DataFrame] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        pair: str = "BTC/USDT:USDT",
        timeframe: str = "5m",
    ) -> BacktestResult:
        """
        Run the backtest.

        Parameters
        ----------
        ohlcv_df:
            Historical OHLCV data (columns: open, high, low, close, volume).
            When ``None`` the backtester generates synthetic data.
        start_date / end_date:
            ISO date strings used for label filtering and result metadata.
        pair / timeframe:
            Stored in the result metadata.

        Returns
        -------
        BacktestResult
            Full metrics dict.  ``is_demo=True`` when demo data was used.
        """
        if not self._model_loaded:
            logger.info("No ML model loaded – returning demo backtest result")
            return _build_demo_result(pair, timeframe, start_date, end_date)

        try:
            return self._run_real_backtest(
                ohlcv_df, start_date, end_date, pair, timeframe
            )
        except Exception as exc:
            logger.warning("Backtest failed (%s) – falling back to demo result", exc)
            return _build_demo_result(pair, timeframe, start_date, end_date)

    def get_feature_importance(self) -> Tuple[List[Dict[str, Any]], str]:
        """
        Return (feature_importance_list, method_name).

        Uses SHAP if available and model is loaded, else built-in importances,
        else demo importances.
        """
        if not self._model_loaded or self._classifier is None:
            return _make_demo_feature_importance(), "demo"

        try:
            return self._compute_shap_importance(), "shap"
        except Exception:
            pass

        try:
            return self._compute_builtin_importance(), "built_in"
        except Exception:
            pass

        return _make_demo_feature_importance(), "demo"

    # ------------------------------------------------------------------
    # Internal: model loading
    # ------------------------------------------------------------------

    def _try_load_model(self) -> None:
        if not self.model_path or not os.path.exists(self.model_path):
            logger.debug("ML_MODEL_PATH not set or file absent – demo mode")
            return

        try:
            from bot.ml.feature_engineer import FeatureEngineer
            from bot.ml.signal_classifier import SignalClassifier

            clf = SignalClassifier()
            clf.load_model(self.model_path)
            self._classifier = clf
            self._feature_engineer = FeatureEngineer()
            self._model_loaded = True
            logger.info("MLBacktester: model loaded from %s", self.model_path)
        except Exception as exc:
            logger.warning("MLBacktester: failed to load model – %s", exc)

    # ------------------------------------------------------------------
    # Internal: real backtest
    # ------------------------------------------------------------------

    def _run_real_backtest(
        self,
        ohlcv_df: Optional[pd.DataFrame],
        start_date: Optional[str],
        end_date: Optional[str],
        pair: str,
        timeframe: str,
    ) -> BacktestResult:
        if ohlcv_df is None or ohlcv_df.empty:
            real_df = load_ohlcv_from_file(pair, timeframe)
            if real_df is not None and not real_df.empty:
                logger.info("Loaded real OHLCV data from file for %s %s (%d rows)", pair, timeframe, len(real_df))
                ohlcv_df = real_df
            else:
                logger.info("No real data file found for %s %s — using synthetic data", pair, timeframe)
                ohlcv_df = self._generate_synthetic_ohlcv(n=2000)

        # Slice by date if requested
        if start_date or end_date:
            ohlcv_df = self._filter_by_date(ohlcv_df, start_date, end_date)

        # Feature engineering
        features_df = self._feature_engineer.transform(ohlcv_df)

        # Build ground-truth labels aligned with feature rows
        close_aligned = ohlcv_df["close"].reindex(features_df.index)
        labels, _ = self._feature_engineer.build_labels(
            close_aligned, horizon=self.horizon
        )

        # Drop rows where we can't compute a forward return (tail)
        valid_mask = labels.index.isin(features_df.index) & labels.notna()
        valid_idx = features_df.index[features_df.index.isin(labels[valid_mask].index)]
        if len(valid_idx) < 20:
            logger.warning("Not enough valid rows for backtest – using demo")
            return _build_demo_result(pair, timeframe, start_date, end_date)

        X = features_df.loc[valid_idx]
        y_true = labels.loc[valid_idx]

        # Predictions and confidence
        predictions = []
        confidences = []
        for i in range(len(X)):
            row = X.iloc[[i]]
            pred, conf = self._classifier.predict(row)
            predictions.append(pred[0] if isinstance(pred, (list, np.ndarray)) else pred)
            confidences.append(float(conf[0]) if isinstance(conf, (list, np.ndarray)) else float(conf))

        y_pred = np.array(predictions)
        confs = np.array(confidences)
        y_true_arr = y_true.values

        # Classification metrics (binary: long vs not-long)
        metrics = self._compute_classification_metrics(y_true_arr, y_pred)
        cm = self._compute_confusion_matrix(y_true_arr, y_pred)

        # Profit simulation
        close_for_profit = close_aligned.loc[valid_idx]
        profit_with, profit_without = self._simulate_profit(
            close_for_profit, y_true_arr, y_pred, confs
        )
        improvement = (
            ((profit_with - profit_without) / abs(profit_without) * 100)
            if profit_without != 0
            else 0.0
        )

        # Rolling accuracy
        rolling_acc = self._compute_rolling_accuracy(y_true_arr, y_pred, valid_idx)

        # Confidence distribution
        conf_dist = self._compute_confidence_distribution(confs)

        # Feature importance
        fi_list, fi_method = self.get_feature_importance()

        model_version = getattr(self._classifier, "active_version", None)

        return BacktestResult(
            precision=metrics["precision"],
            recall=metrics["recall"],
            f1_score=metrics["f1"],
            accuracy=metrics["accuracy"],
            total_predictions=len(y_pred),
            confusion_matrix=cm,
            profit_with_ml=round(profit_with, 2),
            profit_without_ml=round(profit_without, 2),
            profit_improvement_pct=round(improvement, 1),
            rolling_accuracy=rolling_acc,
            confidence_distribution=conf_dist,
            feature_importance=fi_list,
            feature_importance_method=fi_method,
            is_demo=False,
            model_version=model_version,
            backtest_start=start_date,
            backtest_end=end_date,
            pair=pair,
            timeframe=timeframe,
        )

    # ------------------------------------------------------------------
    # Internal: metric computation helpers
    # ------------------------------------------------------------------

    def _compute_classification_metrics(
        self, y_true: np.ndarray, y_pred: np.ndarray
    ) -> Dict[str, float]:
        if _HAS_SKLEARN:
            try:
                p, r, f, _ = precision_recall_fscore_support(
                    y_true, y_pred, average="weighted", zero_division=0
                )
                accuracy = float(np.mean(y_true == y_pred))
                return {
                    "precision": round(float(p), 4),
                    "recall": round(float(r), 4),
                    "f1": round(float(f), 4),
                    "accuracy": round(accuracy, 4),
                }
            except Exception:
                pass

        # Fallback: manual weighted precision/recall
        accuracy = float(np.mean(y_true == y_pred))
        classes = np.unique(y_true)
        p_list, r_list, f_list, weights = [], [], [], []
        for cls in classes:
            mask_true = y_true == cls
            mask_pred = y_pred == cls
            tp = int(np.sum(mask_true & mask_pred))
            fp = int(np.sum(~mask_true & mask_pred))
            fn = int(np.sum(mask_true & ~mask_pred))
            prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1 = (
                2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
            )
            p_list.append(prec)
            r_list.append(rec)
            f_list.append(f1)
            weights.append(int(np.sum(mask_true)))

        w = np.array(weights, dtype=float)
        total = w.sum() or 1.0
        return {
            "precision": round(float(np.dot(p_list, w) / total), 4),
            "recall": round(float(np.dot(r_list, w) / total), 4),
            "f1": round(float(np.dot(f_list, w) / total), 4),
            "accuracy": round(accuracy, 4),
        }

    def _compute_confusion_matrix(
        self, y_true: np.ndarray, y_pred: np.ndarray
    ) -> ConfusionMatrixData:
        # Binary: treat "long" as positive class
        positive = "long"
        tp = int(np.sum((y_true == positive) & (y_pred == positive)))
        fp = int(np.sum((y_true != positive) & (y_pred == positive)))
        fn = int(np.sum((y_true == positive) & (y_pred != positive)))
        tn = int(np.sum((y_true != positive) & (y_pred != positive)))
        return ConfusionMatrixData(tp=tp, fp=fp, tn=tn, fn=fn)

    def _simulate_profit(
        self,
        close: pd.Series,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        confidences: np.ndarray,
    ) -> Tuple[float, float]:
        """
        Simplified P&L simulation.

        Without ML filter: take every "long" signal in the ground truth.
        With ML filter: only take trades where the ML predicts "long" AND
                        confidence >= min_confidence.
        """
        min_conf = getattr(self._classifier, "min_confidence", 0.5)
        close_arr = close.values
        pnl_without = 0.0
        pnl_with = 0.0

        for i in range(len(close_arr) - 1):
            future_ret = (close_arr[i + 1] - close_arr[i]) / close_arr[i]
            # Without ML: trade whenever true label is long
            if y_true[i] == "long":
                pnl_without += future_ret * 100
            # With ML: trade when model predicts long with sufficient confidence
            if y_pred[i] == "long" and confidences[i] >= min_conf:
                pnl_with += future_ret * 100

        return pnl_with, pnl_without

    def _compute_rolling_accuracy(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        index: pd.Index,
    ) -> List[RollingAccuracyPoint]:
        window = self.rolling_window
        n = len(y_true)
        if n < window:
            window = max(10, n // 2)

        points: List[RollingAccuracyPoint] = []
        step = max(1, (n - window) // 20)  # emit ~20 points
        for start in range(0, n - window + 1, step):
            end = start + window
            acc = float(np.mean(y_true[start:end] == y_pred[start:end]))
            ts_idx = index[start]
            if hasattr(ts_idx, "isoformat"):
                ts = ts_idx.isoformat()
            else:
                ts = str(ts_idx)
            points.append(RollingAccuracyPoint(window_start=ts, accuracy=round(acc, 4)))

        return points

    def _compute_confidence_distribution(
        self, confidences: np.ndarray
    ) -> List[ConfidenceBucket]:
        thresholds = [
            (0.5, 0.6, "0.5-0.6"),
            (0.6, 0.7, "0.6-0.7"),
            (0.7, 0.8, "0.7-0.8"),
            (0.8, 0.9, "0.8-0.9"),
            (0.9, 1.01, "0.9-1.0"),
        ]
        buckets = []
        for lo, hi, label in thresholds:
            count = int(np.sum((confidences >= lo) & (confidences < hi)))
            buckets.append(ConfidenceBucket(bucket=label, count=count))
        return buckets

    # ------------------------------------------------------------------
    # Internal: SHAP / built-in feature importance
    # ------------------------------------------------------------------

    def _compute_shap_importance(self) -> List[Dict[str, Any]]:
        if not _HAS_SHAP or self._classifier is None:
            raise RuntimeError("SHAP not available")

        model = getattr(self._classifier, "_model", None)
        if model is None:
            raise RuntimeError("No underlying model")

        feature_names = getattr(self._classifier, "feature_names", [])
        if not feature_names:
            raise RuntimeError("No feature names")

        # Generate small synthetic data for SHAP
        rng = np.random.default_rng(42)
        X_bg = rng.standard_normal((50, len(feature_names)))

        explainer = shap.TreeExplainer(model)
        shap_values = explainer.shap_values(X_bg)
        if isinstance(shap_values, list):
            importance = np.abs(np.array(shap_values)).mean(axis=(0, 1))
        else:
            importance = np.abs(shap_values).mean(axis=0)

        total = importance.sum() or 1.0
        importance_norm = (importance / total).tolist()
        result = []
        for name, imp in sorted(
            zip(feature_names, importance_norm), key=lambda x: x[1], reverse=True
        ):
            result.append(
                {
                    "name": name,
                    "importance": round(float(imp), 4),
                    "direction": "positive" if imp > 0.07 else "neutral",
                }
            )
        return result[:15]

    def _compute_builtin_importance(self) -> List[Dict[str, Any]]:
        model = getattr(self._classifier, "_model", None)
        if model is None:
            raise RuntimeError("No underlying model")

        if not hasattr(model, "feature_importances_"):
            raise RuntimeError("Model has no feature_importances_")

        feature_names = getattr(self._classifier, "feature_names", [])
        importances = model.feature_importances_
        total = importances.sum() or 1.0
        norm = importances / total

        result = []
        for name, imp in sorted(
            zip(feature_names, norm.tolist()), key=lambda x: x[1], reverse=True
        ):
            result.append(
                {
                    "name": name,
                    "importance": round(float(imp), 4),
                    "direction": "positive" if imp > 0.07 else "neutral",
                }
            )
        return result[:15]

    # ------------------------------------------------------------------
    # Internal: synthetic data generator
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_synthetic_ohlcv(n: int = 2000) -> pd.DataFrame:
        rng = np.random.default_rng(42)
        dates = pd.date_range("2025-01-01", periods=n, freq="5min")
        close = 40_000 + np.cumsum(rng.standard_normal(n) * 100)
        close = np.clip(close, 1, None)
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

    @staticmethod
    def _filter_by_date(
        df: pd.DataFrame,
        start_date: Optional[str],
        end_date: Optional[str],
    ) -> pd.DataFrame:
        if not isinstance(df.index, pd.DatetimeIndex):
            return df
        if start_date:
            df = df[df.index >= pd.Timestamp(start_date)]
        if end_date:
            df = df[df.index <= pd.Timestamp(end_date)]
        return df
