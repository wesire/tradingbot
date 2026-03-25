"""
Feature engineering pipeline for ML signal classification.

Transforms raw OHLCV data into a rich feature matrix ready for model training
or inference.  All heavy numeric work is done with pandas/numpy so that the
module remains fast even without a C-extension TA library installed.
"""
from __future__ import annotations

import logging
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def _sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period).mean()


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    tr = pd.concat(
        [
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


# ---------------------------------------------------------------------------
# Public class
# ---------------------------------------------------------------------------

class FeatureEngineer:
    """
    Generates ML-ready features from OHLCV data.

    Parameters
    ----------
    include_higher_tf:
        Whether to include pre-computed higher-timeframe features passed via
        ``higher_tf_data``.  These are *optional* columns appended when
        ``transform()`` is called with the ``higher_tf_data`` argument.
    """

    #: Ordered list of feature column names produced by ``transform()``.
    FEATURE_NAMES: List[str] = [
        # RSI
        "rsi_14",
        "rsi_21",
        # MACD
        "macd_line",
        "macd_signal",
        "macd_hist",
        # Bollinger Bands
        "bb_width",
        "bb_pct_b",
        # ATR
        "atr_14",
        "atr_ratio",
        # EMA crossover signals
        "ema_cross_9_21",
        "ema_cross_21_50",
        # Volume
        "volume_ratio",
        "volume_trend",
        # Price momentum
        "mom_1",
        "mom_5",
        "mom_10",
        "mom_20",
        # Volatility (rolling std of returns)
        "vol_10",
        "vol_20",
    ]

    #: Higher-timeframe feature names (appended when provided).
    HTF_FEATURE_NAMES: List[str] = [
        "htf_daily_rsi",
        "htf_weekly_trend",
    ]

    def __init__(self, include_higher_tf: bool = False) -> None:
        self.include_higher_tf = include_higher_tf

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def feature_names(self) -> List[str]:
        """Return feature column names for the current configuration."""
        names = list(self.FEATURE_NAMES)
        if self.include_higher_tf:
            names.extend(self.HTF_FEATURE_NAMES)
        return names

    def transform(
        self,
        df: pd.DataFrame,
        higher_tf_data: Optional[pd.DataFrame] = None,
    ) -> pd.DataFrame:
        """
        Compute all ML features from an OHLCV DataFrame.

        Parameters
        ----------
        df:
            DataFrame with columns ``open``, ``high``, ``low``, ``close``,
            ``volume``.  The index may be a DatetimeIndex or a plain integer
            index.
        higher_tf_data:
            Optional DataFrame with columns ``htf_daily_rsi`` and
            ``htf_weekly_trend``, aligned by date.  Only used when
            ``include_higher_tf=True``.

        Returns
        -------
        pandas.DataFrame
            Clean feature DataFrame (NaN rows dropped) ready for model input.
        """
        df = df.copy()
        self._validate_columns(df)

        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        features = pd.DataFrame(index=df.index)

        # --- RSI ----------------------------------------------------------
        features["rsi_14"] = _rsi(close, 14)
        features["rsi_21"] = _rsi(close, 21)

        # --- MACD ---------------------------------------------------------
        ema_12 = _ema(close, 12)
        ema_26 = _ema(close, 26)
        macd = ema_12 - ema_26
        macd_signal = _ema(macd, 9)
        features["macd_line"] = macd
        features["macd_signal"] = macd_signal
        features["macd_hist"] = macd - macd_signal

        # --- Bollinger Bands (20, 2σ) -------------------------------------
        bb_mid = _sma(close, 20)
        bb_std = close.rolling(20).std()
        bb_upper = bb_mid + 2 * bb_std
        bb_lower = bb_mid - 2 * bb_std
        features["bb_width"] = (bb_upper - bb_lower) / bb_mid.replace(0, np.nan)
        features["bb_pct_b"] = (close - bb_lower) / (bb_upper - bb_lower).replace(0, np.nan)

        # --- ATR ----------------------------------------------------------
        atr = _atr(high, low, close, 14)
        features["atr_14"] = atr
        features["atr_ratio"] = atr / close.replace(0, np.nan)

        # --- EMA crossovers -----------------------------------------------
        ema_9 = _ema(close, 9)
        ema_21 = _ema(close, 21)
        ema_50 = _ema(close, 50)
        # +1 if fast > slow, -1 if fast < slow
        features["ema_cross_9_21"] = np.sign(ema_9 - ema_21).astype(float)
        features["ema_cross_21_50"] = np.sign(ema_21 - ema_50).astype(float)

        # --- Volume features ----------------------------------------------
        vol_sma20 = _sma(volume, 20)
        features["volume_ratio"] = volume / vol_sma20.replace(0, np.nan)
        # 1 if increasing over last 5 bars, else -1
        features["volume_trend"] = np.sign(volume - volume.shift(5)).astype(float)

        # --- Price momentum (log returns) ---------------------------------
        log_ret = np.log(close / close.shift(1))
        for period in (1, 5, 10, 20):
            features[f"mom_{period}"] = log_ret.rolling(period).sum()

        # --- Volatility (rolling std of log returns) ----------------------
        for period in (10, 20):
            features[f"vol_{period}"] = log_ret.rolling(period).std()

        # --- Higher timeframe features ------------------------------------
        if self.include_higher_tf and higher_tf_data is not None:
            features = self._merge_htf(features, higher_tf_data)

        # --- Clean up NaN values ------------------------------------------
        features = features.ffill()
        features = features.dropna()

        logger.debug(
            "FeatureEngineer: produced %d rows × %d features",
            len(features),
            features.shape[1],
        )
        return features

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_columns(df: pd.DataFrame) -> None:
        required = {"open", "high", "low", "close", "volume"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"OHLCV DataFrame missing columns: {missing}")

    def _merge_htf(
        self,
        features: pd.DataFrame,
        higher_tf_data: pd.DataFrame,
    ) -> pd.DataFrame:
        """Merge higher-timeframe features, forward-filling to match the base index."""
        htf = higher_tf_data.reindex(
            features.index, method="ffill"
        )[self.HTF_FEATURE_NAMES]
        return features.join(htf)

    # ------------------------------------------------------------------
    # Convenience: build target labels from future returns
    # ------------------------------------------------------------------

    @staticmethod
    def build_labels(
        close: pd.Series,
        horizon: int = 5,
        long_threshold: float = 0.002,
        short_threshold: float = -0.002,
    ) -> Tuple[pd.Series, pd.Series]:
        """
        Derive simple long/short/neutral labels from future log returns.

        Parameters
        ----------
        close:
            Close price series aligned with the feature DataFrame.
        horizon:
            Number of bars to look forward.
        long_threshold / short_threshold:
            Minimum return to label a bar as ``long`` / ``short``.

        Returns
        -------
        (labels, future_returns)
            ``labels``: pd.Series with values ``long``, ``short``, ``neutral``.
            ``future_returns``: pd.Series of the raw forward log returns.
        """
        future_ret = np.log(close.shift(-horizon) / close)
        labels = pd.Series("neutral", index=close.index)
        labels[future_ret >= long_threshold] = "long"
        labels[future_ret <= short_threshold] = "short"
        return labels, future_ret
