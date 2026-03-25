"""
ML signal classifier wrapping XGBoost (with scikit-learn fallback).

Supports training, cross-validated evaluation, prediction with confidence
scores, model versioning via joblib, and feature importance reporting.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional heavy imports
# ---------------------------------------------------------------------------
try:
    import joblib  # type: ignore
    _HAS_JOBLIB = True
except ImportError:
    _HAS_JOBLIB = False
    logger.warning("joblib not installed – model save/load disabled")

try:
    from xgboost import XGBClassifier  # type: ignore
    _HAS_XGBOOST = True
except ImportError:
    _HAS_XGBOOST = False
    logger.warning("xgboost not installed – using sklearn GradientBoostingClassifier")

try:
    from sklearn.ensemble import GradientBoostingClassifier  # type: ignore
    from sklearn.model_selection import StratifiedKFold, cross_validate  # type: ignore
    from sklearn.preprocessing import LabelEncoder  # type: ignore
    _HAS_SKLEARN = True
except ImportError:
    _HAS_SKLEARN = False
    logger.warning("scikit-learn not installed – SignalClassifier unavailable")

# ---------------------------------------------------------------------------
# Label constants
# ---------------------------------------------------------------------------
LABELS = ("long", "short", "neutral")
_LABEL_TO_INT = {lbl: i for i, lbl in enumerate(LABELS)}
_INT_TO_LABEL = {i: lbl for i, lbl in enumerate(LABELS)}


class SignalClassifier:
    """
    Gradient-boosted signal classifier for trading signals.

    Wraps XGBoost when available, falls back to scikit-learn's
    ``GradientBoostingClassifier``.

    Parameters
    ----------
    model_dir:
        Directory used for saving / loading versioned model files.
    min_confidence:
        Minimum predicted probability to emit a non-neutral signal.
    hyperparams:
        Optional dict to override default model hyperparameters.
    """

    _DEFAULT_XGB_PARAMS: Dict[str, Any] = {
        "n_estimators": 300,
        "max_depth": 4,
        "learning_rate": 0.05,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "reg_alpha": 0.1,
        "reg_lambda": 1.0,
        "use_label_encoder": False,
        "eval_metric": "mlogloss",
        "random_state": 42,
        "n_jobs": -1,
    }

    _DEFAULT_SKL_PARAMS: Dict[str, Any] = {
        "n_estimators": 300,
        "max_depth": 4,
        "learning_rate": 0.05,
        "subsample": 0.8,
        "random_state": 42,
    }

    def __init__(
        self,
        model_dir: str = "models",
        min_confidence: float = 0.50,
        hyperparams: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not _HAS_SKLEARN:
            raise RuntimeError(
                "scikit-learn is required for SignalClassifier. "
                "Install it with: pip install scikit-learn"
            )

        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.min_confidence = min_confidence

        self._model: Any = None
        self._label_encoder = LabelEncoder()
        self._label_encoder.fit(list(LABELS))
        self._feature_names: List[str] = []
        self._active_version: Optional[str] = None

        # Build model
        params = hyperparams or {}
        if _HAS_XGBOOST:
            merged = {**self._DEFAULT_XGB_PARAMS, **params}
            # Remove XGBoost-specific key when using older API
            merged.pop("use_label_encoder", None)
            self._model = XGBClassifier(**merged)
        else:
            merged = {**self._DEFAULT_SKL_PARAMS, **params}
            self._model = GradientBoostingClassifier(**merged)

        logger.info(
            "SignalClassifier initialized (backend=%s)",
            "xgboost" if _HAS_XGBOOST else "sklearn",
        )

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def train(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        cv_folds: int = 5,
    ) -> Dict[str, float]:
        """
        Train the classifier and return cross-validated metrics.

        Parameters
        ----------
        X:
            Feature matrix (rows = observations).
        y:
            Target labels (``"long"``, ``"short"``, ``"neutral"``).
        cv_folds:
            Number of folds for StratifiedKFold cross-validation.

        Returns
        -------
        dict
            ``accuracy_mean``, ``accuracy_std``, ``f1_mean``, ``f1_std``.
        """
        self._feature_names = list(X.columns)
        y_enc = self._label_encoder.transform(y)

        cv = StratifiedKFold(n_splits=cv_folds, shuffle=True, random_state=42)
        cv_results = cross_validate(
            self._model,
            X.values,
            y_enc,
            cv=cv,
            scoring=["accuracy", "f1_macro"],
            return_train_score=False,
        )

        # Train on full dataset
        self._model.fit(X.values, y_enc)

        metrics = {
            "accuracy_mean": float(cv_results["test_accuracy"].mean()),
            "accuracy_std": float(cv_results["test_accuracy"].std()),
            "f1_mean": float(cv_results["test_f1_macro"].mean()),
            "f1_std": float(cv_results["test_f1_macro"].std()),
        }

        logger.info(
            "Training complete: accuracy=%.3f±%.3f  f1=%.3f±%.3f",
            metrics["accuracy_mean"],
            metrics["accuracy_std"],
            metrics["f1_mean"],
            metrics["f1_std"],
        )
        return metrics

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    def predict(self, X: pd.DataFrame) -> Tuple[str, float]:
        """
        Predict signal for the *most recent* row in ``X``.

        Returns
        -------
        (signal, confidence)
            ``signal`` is ``"long"``, ``"short"``, or ``"neutral"``.
            ``confidence`` is the model's predicted probability for that class.
        """
        self._check_fitted()
        proba = self._model.predict_proba(X.values[-1:, :])[0]
        class_idx = int(np.argmax(proba))
        confidence = float(proba[class_idx])
        label = self._label_encoder.inverse_transform([class_idx])[0]

        if confidence < self.min_confidence:
            return "neutral", confidence

        return str(label), confidence

    def predict_proba(self, X: pd.DataFrame) -> Dict[str, float]:
        """
        Return the full probability distribution for the *most recent* row.

        Returns
        -------
        dict
            ``{"long": p0, "short": p1, "neutral": p2}``
        """
        self._check_fitted()
        proba = self._model.predict_proba(X.values[-1:, :])[0]
        classes = self._label_encoder.inverse_transform(
            range(len(proba))
        )
        return {str(c): float(p) for c, p in zip(classes, proba)}

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save_model(self, path: Optional[str] = None) -> str:
        """
        Persist the model to disk using joblib.

        Parameters
        ----------
        path:
            Full file path.  If ``None``, a timestamped filename is
            generated inside ``model_dir``.

        Returns
        -------
        str
            Resolved path to the saved model file.
        """
        if not _HAS_JOBLIB:
            raise RuntimeError("joblib is required for save_model()")
        self._check_fitted()

        if path is None:
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
            fname = f"signal_classifier_{ts}.joblib"
            path = str(self.model_dir / fname)

        payload = {
            "model": self._model,
            "label_encoder": self._label_encoder,
            "feature_names": self._feature_names,
            "min_confidence": self.min_confidence,
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }
        joblib.dump(payload, path)
        self._active_version = path

        # Update "latest" symlink / pointer file
        latest_ptr = self.model_dir / "signal_classifier_latest.json"
        latest_ptr.write_text(json.dumps({"path": path}))

        logger.info("Model saved to %s", path)
        return path

    def load_model(self, path: str) -> None:
        """
        Load a previously saved model from disk.

        Parameters
        ----------
        path:
            Path to a ``.joblib`` file produced by :meth:`save_model`.
        """
        if not _HAS_JOBLIB:
            raise RuntimeError("joblib is required for load_model()")

        payload = joblib.load(path)
        self._model = payload["model"]
        self._label_encoder = payload["label_encoder"]
        self._feature_names = payload.get("feature_names", [])
        self.min_confidence = payload.get("min_confidence", self.min_confidence)
        self._active_version = path
        logger.info("Model loaded from %s", path)

    # ------------------------------------------------------------------
    # Feature importance
    # ------------------------------------------------------------------

    def get_feature_importance(self) -> Dict[str, float]:
        """
        Return a dict mapping feature name → importance score.

        For XGBoost the ``gain`` metric is used; for sklearn the built-in
        ``feature_importances_`` attribute is used.
        """
        self._check_fitted()
        if _HAS_XGBOOST and isinstance(self._model, XGBClassifier):
            raw = self._model.get_booster().get_score(importance_type="gain")
            # XGBoost uses f0, f1, … as default feature names when trained on
            # numpy arrays.  Map back to human-readable names if available.
            if self._feature_names:
                mapped: Dict[str, float] = {}
                for k, v in raw.items():
                    try:
                        idx = int(k[1:])
                        fname = self._feature_names[idx]
                    except (ValueError, IndexError):
                        fname = k
                    mapped[fname] = float(v)
                return mapped
            return {k: float(v) for k, v in raw.items()}
        else:
            importances = self._model.feature_importances_
            names = (
                self._feature_names
                if self._feature_names and len(self._feature_names) == len(importances)
                else [f"f{i}" for i in range(len(importances))]
            )
            return dict(zip(names, importances.tolist()))

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_fitted(self) -> bool:
        """True once :meth:`train` or :meth:`load_model` has been called."""
        if self._model is None:
            return False
        try:
            # sklearn convention
            from sklearn.utils.validation import check_is_fitted  # type: ignore
            check_is_fitted(self._model)
            return True
        except Exception:
            return False

    @property
    def active_version(self) -> Optional[str]:
        """Path of the currently active model file, or ``None``."""
        return self._active_version

    @property
    def feature_names(self) -> List[str]:
        """Feature names used during training."""
        return list(self._feature_names)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_fitted(self) -> None:
        if not self.is_fitted:
            raise RuntimeError("Model is not fitted. Call train() or load_model() first.")
