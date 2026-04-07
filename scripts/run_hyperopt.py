#!/usr/bin/env python3
"""
Hyperparameter optimization for the ML signal classifier.

Performs a randomized grid search over XGBoost / GradientBoosting
hyperparameters using stratified k-fold cross-validation, then saves
the best model to disk.

Usage:
    python scripts/run_hyperopt.py [options]
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("run_hyperopt")

# Number of forward bars used to compute training labels.
FORWARD_BARS = 10


# ---------------------------------------------------------------------------
# Data helpers (shared with train_model.py)
# ---------------------------------------------------------------------------


def _load_ohlcv_from_disk(data_dir: Path) -> pd.DataFrame | None:
    """Try to load OHLCV CSV/JSON files from bot/data/."""
    frames = []
    for ext in ("*.csv", "*.json"):
        for fpath in sorted(data_dir.glob(ext)):
            try:
                df = (
                    pd.read_csv(fpath)
                    if fpath.suffix == ".csv"
                    else pd.read_json(fpath)
                )
                if {"open", "high", "low", "close", "volume"}.issubset(
                    {c.lower() for c in df.columns}
                ):
                    df.columns = [c.lower() for c in df.columns]
                    frames.append(df[["open", "high", "low", "close", "volume"]])
            except Exception as exc:
                logger.debug("Skipping %s: %s", fpath, exc)
    if frames:
        combined = pd.concat(frames, ignore_index=True).dropna()
        logger.info("Loaded %d OHLCV rows from %s", len(combined), data_dir)
        return combined
    return None


def _generate_synthetic_ohlcv(n_bars: int = 5000, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic OHLCV data when real data is absent."""
    rng = np.random.default_rng(seed)
    returns = rng.normal(0.0002, 0.015, size=n_bars)
    close = 45_000.0 * np.exp(np.cumsum(returns))
    noise = rng.uniform(0.001, 0.005, size=n_bars)
    high = close * (1 + noise)
    low = close * (1 - noise)
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    volume = rng.uniform(500, 5000, size=n_bars)
    df = pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume}
    )
    logger.info("Generated %d rows of synthetic OHLCV data", n_bars)
    return df


def _make_labels(
    close: pd.Series,
    forward_bars: int = FORWARD_BARS,
    threshold: float = 0.005,
) -> pd.Series:
    """Create forward-return labels: 'long' / 'short' / 'neutral'."""
    fwd_return = close.shift(-forward_bars) / close - 1
    labels = pd.Series("neutral", index=close.index)
    labels[fwd_return > threshold] = "long"
    labels[fwd_return < -threshold] = "short"
    return labels


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    from bot.config.default_config import config

    default_output = os.getenv(
        "ML_MODEL_PATH",
        str(PROJECT_ROOT / "models" / "signal_classifier_latest.joblib"),
    )

    parser = argparse.ArgumentParser(
        description="Hyperparameter optimization for the ML signal classifier."
    )
    parser.add_argument(
        "--timeframe",
        default=config.PRIMARY_TIMEFRAME,
        help="Timeframe label stored in result metadata (default: %(default)s)",
    )
    parser.add_argument(
        "--n-iter",
        type=int,
        default=20,
        help="Number of random hyperparameter combinations to try (default: 20)",
    )
    parser.add_argument(
        "--cv-folds",
        type=int,
        default=3,
        help="Number of stratified CV folds (default: 3)",
    )
    parser.add_argument(
        "--output",
        default=default_output,
        help=f"Path to save the best model (default: {default_output})",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=None,
        help="Alias for --n-iter (kept for backwards compatibility)",
    )

    args = parser.parse_args()

    # --epochs is an alias for --n-iter (legacy CLI compat)
    n_iter = args.epochs if args.epochs is not None else args.n_iter

    print(f"{'='*60}")
    print("HYPERPARAMETER OPTIMIZATION")
    print("=" * 60)
    print(f"Timeframe:   {args.timeframe}")
    print(f"Iterations:  {n_iter}")
    print(f"CV folds:    {args.cv_folds}")
    print(f"Output:      {args.output}")
    print()

    # ------------------------------------------------------------------
    # 1. Imports
    # ------------------------------------------------------------------
    try:
        from sklearn.model_selection import (  # type: ignore
            RandomizedSearchCV,
            StratifiedKFold,
        )
        from sklearn.preprocessing import LabelEncoder  # type: ignore
        from sklearn.utils.class_weight import compute_sample_weight  # type: ignore
    except ImportError as exc:
        logger.error("scikit-learn is required: %s", exc)
        sys.exit(1)

    try:
        from bot.ml import FeatureEngineer, SignalClassifier
    except ImportError as exc:
        logger.error("Could not import ML modules: %s", exc)
        sys.exit(1)

    # ------------------------------------------------------------------
    # 2. Load / generate OHLCV data
    # ------------------------------------------------------------------
    data_dir = PROJECT_ROOT / "bot" / "data"
    ohlcv = _load_ohlcv_from_disk(data_dir)
    if ohlcv is None or len(ohlcv) < 200:
        logger.info("Insufficient on-disk data — using synthetic training data.")
        ohlcv = _generate_synthetic_ohlcv()

    # ------------------------------------------------------------------
    # 3. Feature engineering + labels
    # ------------------------------------------------------------------
    fe = FeatureEngineer()
    features = fe.transform(ohlcv)
    if features.empty:
        logger.error("Feature engineering produced an empty DataFrame — aborting.")
        sys.exit(1)

    labels = _make_labels(ohlcv["close"], forward_bars=FORWARD_BARS)
    aligned_idx = features.index.intersection(labels.index)
    X = features.loc[aligned_idx]
    y = labels.loc[aligned_idx]
    if len(X) > FORWARD_BARS:
        X = X.iloc[:-FORWARD_BARS]
        y = y.iloc[:-FORWARD_BARS]

    le = LabelEncoder()
    le.fit(["long", "short", "neutral"])
    y_enc = le.transform(y)

    logger.info(
        "Dataset: %d samples | long=%d short=%d neutral=%d",
        len(y),
        (y == "long").sum(),
        (y == "short").sum(),
        (y == "neutral").sum(),
    )

    # Per-sample weights to address class imbalance
    sample_weights = compute_sample_weight(class_weight="balanced", y=y_enc)

    # ------------------------------------------------------------------
    # 4. Define the search space
    # ------------------------------------------------------------------
    try:
        from xgboost import XGBClassifier  # type: ignore

        base_estimator = XGBClassifier(
            eval_metric="mlogloss",
            random_state=42,
            n_jobs=-1,
        )
        param_dist: dict = {
            "n_estimators": [100, 200, 300, 500],
            "max_depth": [3, 4, 5, 6],
            "learning_rate": [0.01, 0.03, 0.05, 0.1, 0.2],
            "subsample": [0.6, 0.7, 0.8, 1.0],
            "colsample_bytree": [0.6, 0.7, 0.8, 1.0],
            "min_child_weight": [1, 3, 5, 7],
            "reg_alpha": [0.0, 0.1, 0.5, 1.0],
            "reg_lambda": [0.5, 1.0, 2.0],
        }
        fit_params = {"sample_weight": sample_weights}
        logger.info("Using XGBoost backend")
    except ImportError:
        from sklearn.ensemble import GradientBoostingClassifier  # type: ignore

        base_estimator = GradientBoostingClassifier(random_state=42)
        param_dist = {
            "n_estimators": [100, 200, 300],
            "max_depth": [3, 4, 5],
            "learning_rate": [0.01, 0.05, 0.1, 0.2],
            "subsample": [0.6, 0.8, 1.0],
            "min_samples_split": [2, 5, 10],
        }
        fit_params = {"sample_weight": sample_weights}
        logger.info("XGBoost not available — using GradientBoostingClassifier")

    # ------------------------------------------------------------------
    # 5. Randomized search with stratified CV
    # ------------------------------------------------------------------
    cv = StratifiedKFold(n_splits=args.cv_folds, shuffle=True, random_state=42)

    print(f"Running RandomizedSearchCV with {n_iter} iterations × {args.cv_folds} folds…")

    search = RandomizedSearchCV(
        estimator=base_estimator,
        param_distributions=param_dist,
        n_iter=n_iter,
        cv=cv,
        scoring="f1_macro",
        refit=True,
        verbose=1,
        random_state=42,
        n_jobs=-1,
    )

    # Passing fit_params via .fit() is the sklearn 1.4+ way; sklearn slices
    # sample_weight per fold so class balancing applies throughout CV scoring.
    search.fit(X.values, y_enc, **fit_params)

    best_params = search.best_params_
    best_score = search.best_score_

    print()
    print(f"{'='*60}")
    print("BEST PARAMETERS")
    print("=" * 60)
    for k, v in sorted(best_params.items()):
        print(f"  {k}: {v}")
    print(f"\nBest CV f1_macro: {best_score:.4f}")

    # ------------------------------------------------------------------
    # 6. Retrain with best params + class-balanced weights on full data
    # ------------------------------------------------------------------
    print()
    print("Retraining final model on full dataset with best parameters…")
    clf = SignalClassifier(
        model_dir=str(Path(args.output).parent),
        hyperparams=best_params,
    )
    metrics = clf.train(X, y, cv_folds=args.cv_folds)
    logger.info("Final model metrics: %s", metrics)

    # ------------------------------------------------------------------
    # 7. Save
    # ------------------------------------------------------------------
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    clf.save_model(str(output_path))

    print()
    print(f"{'='*60}")
    print("FINAL METRICS")
    print("=" * 60)
    print(f"  accuracy_mean: {metrics['accuracy_mean']:.4f} ± {metrics['accuracy_std']:.4f}")
    print(f"  f1_mean:       {metrics['f1_mean']:.4f} ± {metrics['f1_std']:.4f}")
    print(f"\nModel saved to: {output_path}")
    print("Set ML_MODEL_PATH in your .env to enable live ML inference.")

    print(f"\n{'='*60}")
    print("Hyperopt complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
