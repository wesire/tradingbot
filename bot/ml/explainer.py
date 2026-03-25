"""
Model explainability using SHAP (SHapley Additive exPlanations).

Falls back gracefully when SHAP is not installed.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

try:
    import shap  # type: ignore
    _HAS_SHAP = True
except ImportError:
    _HAS_SHAP = False
    logger.warning(
        "shap not installed – ModelExplainer will return placeholder values. "
        "Install with: pip install shap"
    )


class ModelExplainer:
    """
    Wraps SHAP to explain individual predictions and global feature importance.

    Uses ``shap.TreeExplainer`` for tree-based models (XGBoost, LightGBM,
    sklearn GradientBoosting) which is orders of magnitude faster than the
    model-agnostic KernelExplainer.
    """

    def __init__(self) -> None:
        self._explainer: Optional[Any] = None
        self._last_model: Optional[Any] = None

    # ------------------------------------------------------------------
    # Core methods
    # ------------------------------------------------------------------

    def explain_prediction(
        self,
        model: Any,
        X_single: pd.DataFrame,
    ) -> Dict[str, float]:
        """
        Compute SHAP values for a single observation.

        Parameters
        ----------
        model:
            A fitted tree-based classifier with a ``predict_proba`` method
            (e.g. ``XGBClassifier``, ``GradientBoostingClassifier``).
        X_single:
            DataFrame with exactly **one** row and the same columns used
            during training.

        Returns
        -------
        dict
            ``{feature_name: shap_value, …}`` for the predicted class.
            Returns ``{}`` when SHAP is unavailable.
        """
        if not _HAS_SHAP:
            return {}

        explainer = self._get_explainer(model)
        shap_values = explainer.shap_values(X_single.values)

        # For multi-output (per-class) SHAP, pick the class with highest
        # predicted probability.
        if isinstance(shap_values, list):
            proba = model.predict_proba(X_single.values)
            predicted_class = int(np.argmax(proba[0]))
            sv = shap_values[predicted_class][0]
        else:
            sv = shap_values[0]

        feature_names = list(X_single.columns)
        return dict(zip(feature_names, sv.tolist()))

    def get_global_importance(
        self,
        model: Any,
        X: pd.DataFrame,
    ) -> Dict[str, float]:
        """
        Compute mean absolute SHAP values over a dataset as global importance.

        Parameters
        ----------
        model:
            Fitted tree model.
        X:
            Feature matrix (multiple rows).

        Returns
        -------
        dict
            ``{feature_name: mean_abs_shap, …}`` sorted descending by value.
        """
        if not _HAS_SHAP:
            return {}

        explainer = self._get_explainer(model)
        shap_values = explainer.shap_values(X.values)

        if isinstance(shap_values, list):
            # Average importance across all classes
            abs_mean = np.mean(
                [np.abs(sv).mean(axis=0) for sv in shap_values], axis=0
            )
        else:
            abs_mean = np.abs(shap_values).mean(axis=0)

        feature_names = list(X.columns)
        importance = dict(zip(feature_names, abs_mean.tolist()))
        return dict(
            sorted(importance.items(), key=lambda kv: kv[1], reverse=True)
        )

    @staticmethod
    def format_explanation(
        shap_values: Dict[str, float],
        feature_names: List[str],
        top_n: int = 3,
    ) -> str:
        """
        Produce a human-readable explanation string from SHAP values.

        Parameters
        ----------
        shap_values:
            Dict returned by :meth:`explain_prediction`.
        feature_names:
            Ordered list of feature names (used to filter ``shap_values``).
        top_n:
            Number of top features to include in the explanation.

        Returns
        -------
        str
            Plain-text explanation, e.g.
            ``"Top drivers: rsi_14 (+0.42), macd_hist (-0.31), vol_20 (+0.18)"``
        """
        if not shap_values:
            return "No SHAP explanation available."

        # Only include requested features and sort by absolute value
        relevant = {k: v for k, v in shap_values.items() if k in feature_names}
        if not relevant:
            relevant = shap_values

        sorted_items = sorted(
            relevant.items(), key=lambda kv: abs(kv[1]), reverse=True
        )[:top_n]

        parts = [
            f"{name} ({'+' if val >= 0 else ''}{val:.3f})"
            for name, val in sorted_items
        ]
        return "Top drivers: " + ", ".join(parts)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_explainer(self, model: Any) -> Any:
        """Return (or build) a cached TreeExplainer for *model*."""
        if self._last_model is not model or self._explainer is None:
            self._explainer = shap.TreeExplainer(model)
            self._last_model = model
        return self._explainer
