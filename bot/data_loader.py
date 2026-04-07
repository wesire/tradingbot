"""
Shared utility for loading historical OHLCV data from local JSON files.

Data files live in ``bot/data/`` and follow the naming convention
produced by ``scripts/download_data.py``:

    <safe_pair>-<timeframe>.json

where ``safe_pair`` is the pair string with ``/`` and ``:`` removed, e.g.
``BTC/USDT:USDT`` → ``BTC_USDTUSDT``.

File format: a JSON array of 6-element arrays
    [[timestamp_ms, open, high, low, close, volume], ...]
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Resolve the data directory relative to this file so the path works both
# locally (project root) and inside Docker (WORKDIR /app).
_DATA_DIR = Path(__file__).parent / "data"


def _pair_to_filename_prefix(pair: str) -> str:
    """Convert a pair string to the safe filename prefix used by download_data.py.

    Examples
    --------
    >>> _pair_to_filename_prefix("BTC/USDT:USDT")
    'BTC_USDTUSDT'
    >>> _pair_to_filename_prefix("ETH/USDT")
    'ETH_USDT'
    """
    return pair.replace("/", "_").replace(":", "")


def load_ohlcv_from_file(
    pair: str,
    timeframe: str,
    data_dir: Optional[Path] = None,
) -> Optional[pd.DataFrame]:
    """Load OHLCV data from a local JSON file.

    Parameters
    ----------
    pair:
        Trading pair string, e.g. ``"BTC/USDT:USDT"``.
    timeframe:
        Candle timeframe, e.g. ``"5m"`` or ``"15m"``.
    data_dir:
        Directory to search for data files.  Defaults to ``bot/data/``
        relative to this module.

    Returns
    -------
    pd.DataFrame or None
        DataFrame with columns ``open, high, low, close, volume`` and a
        ``DatetimeIndex`` (UTC), or ``None`` if no file was found.
    """
    base_dir = data_dir if data_dir is not None else _DATA_DIR
    prefix = _pair_to_filename_prefix(pair)
    filename = f"{prefix}-{timeframe}.json"
    filepath = base_dir / filename

    if not filepath.exists():
        logger.debug("No data file found at %s", filepath)
        return None

    try:
        with open(filepath, "r") as fh:
            raw = json.load(fh)

        if not raw:
            logger.warning("Empty data file: %s", filepath)
            return None

        df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df.set_index("timestamp", inplace=True)
        df.sort_index(inplace=True)

        logger.info(
            "Loaded %d candles from %s (%s – %s)",
            len(df),
            filepath.name,
            df.index[0].isoformat(),
            df.index[-1].isoformat(),
        )
        return df

    except Exception as exc:
        logger.warning("Failed to load %s: %s", filepath, exc)
        return None
