"""
ML Signal Classifier Training Script.

Loads backtest metrics from artifacts/metrics.csv and/or generates synthetic
OHLCV training data, engineers features, trains a SignalClassifier, and saves
the resulting model to models/signal_classifier_latest.joblib.

Usage:
    python scripts/train_model.py [--output PATH]

The output path defaults to models/signal_classifier_latest.joblib and can
also be set via the ML_MODEL_PATH environment variable.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Ensure the project root is importable regardless of working directory.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("train_model")

# Number of bars to look ahead when computing forward-return labels.
# Must be kept in sync with the value passed to `_make_labels()`.
FORWARD_BARS = 10


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def _load_ohlcv_from_disk(data_dir: Path) -> pd.DataFrame | None:
    """Try to load OHLCV CSV/JSON files from bot/data/."""
    frames = []
    for ext in ("*.csv", "*.json"):
        for fpath in sorted(data_dir.glob(ext)):
            try:
                df = pd.read_csv(fpath) if fpath.suffix == ".csv" else pd.read_json(fpath)
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
    """Generate synthetic OHLCV data for training when real data is absent."""
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


def _make_labels(close: pd.Series, forward_bars: int = 10, threshold: float = 0.005) -> pd.Series:
    """
    Create forward-return labels: 'long' / 'short' / 'neutral'.

    A bar is labelled 'long' when the close price rises more than *threshold*
    over the next *forward_bars* bars, 'short' when it falls more, and
    'neutral' otherwise.
    """
    fwd_return = close.shift(-forward_bars) / close - 1
    labels = pd.Series("neutral", index=close.index)
    labels[fwd_return > threshold] = "long"
    labels[fwd_return < -threshold] = "short"
    return labels


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Train the ML signal classifier.")
    default_output = os.getenv(
        "ML_MODEL_PATH", str(PROJECT_ROOT / "models" / "signal_classifier_latest.joblib")
    )
    parser.add_argument(
        "--output",
        default=default_output,
        help=f"Path to save the trained model (default: {default_output})",
    )
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # 1. Load or generate OHLCV data
    # ------------------------------------------------------------------
    data_dir = PROJECT_ROOT / "bot" / "data"
    ohlcv = _load_ohlcv_from_disk(data_dir)
    if ohlcv is None or len(ohlcv) < 200:
        logger.info("Insufficient on-disk data — using synthetic training data.")
        ohlcv = _generate_synthetic_ohlcv()

    # ------------------------------------------------------------------
    # 2. Engineer features
    # ------------------------------------------------------------------
    try:
        from bot.ml import FeatureEngineer
    except ImportError as exc:
        logger.error("Could not import FeatureEngineer: %s", exc)
        sys.exit(1)

    fe = FeatureEngineer()
    features = fe.transform(ohlcv)
    if features.empty:
        logger.error("Feature engineering produced an empty DataFrame — aborting.")
        sys.exit(1)

    labels = _make_labels(ohlcv["close"], forward_bars=FORWARD_BARS)
    # Align indices after feature engineering may drop leading NaN rows
    aligned_idx = features.index.intersection(labels.index)
    X = features.loc[aligned_idx]
    y = labels.loc[aligned_idx]
    # Drop the last `FORWARD_BARS` rows where the forward label is undefined
    if len(X) > FORWARD_BARS:
        X = X.iloc[:-FORWARD_BARS]
        y = y.iloc[:-FORWARD_BARS]

    logger.info(
        "Training set: %d samples | long=%d short=%d neutral=%d",
        len(y),
        (y == "long").sum(),
        (y == "short").sum(),
        (y == "neutral").sum(),
    )

    # ------------------------------------------------------------------
    # 3. Train the signal classifier
    # ------------------------------------------------------------------
    try:
        from bot.ml import SignalClassifier
    except ImportError as exc:
        logger.error("Could not import SignalClassifier: %s", exc)
        sys.exit(1)

    clf = SignalClassifier(model_dir=str(output_path.parent))
    metrics = clf.train(X, y)

    logger.info("Training complete — metrics: %s", metrics)

    # ------------------------------------------------------------------
    # 4. Save model
    # ------------------------------------------------------------------
    clf.save_model(str(output_path))
    logger.info("Model saved to %s", output_path)
    print(f"\nModel saved to: {output_path}")
    print("Set ML_MODEL_PATH in your .env to enable live ML inference.")


if __name__ == "__main__":
    main()
