"""
Correlation manager for portfolio risk analysis.

Calculates rolling pairwise correlations between active trading pairs and
provides helpers for exposure concentration and position sizing.
"""
import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class CorrelationManager:
    """
    Calculate and use rolling pairwise correlations for portfolio risk.

    Attributes:
        DEFAULT_CORRELATION_THRESHOLD: Threshold above which two positions
            are considered highly correlated and sizing should be reduced.
        DEFAULT_LOOKBACK_DAYS: Default look-back window for correlation calc.
    """

    DEFAULT_CORRELATION_THRESHOLD: float = 0.7
    DEFAULT_LOOKBACK_DAYS: int = 30

    def __init__(
        self,
        correlation_threshold: float = DEFAULT_CORRELATION_THRESHOLD,
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    ) -> None:
        """
        Initialise the manager.

        Args:
            correlation_threshold: Pairs with |correlation| above this value
                are considered highly correlated (default 0.7).
            lookback_days: Default window used when computing correlations.
        """
        self.correlation_threshold = correlation_threshold
        self.lookback_days = lookback_days
        # price_data: {pair: pd.Series of close prices (index = datetime)}
        self._price_data: Dict[str, pd.Series] = {}
        logger.info(
            "Initialized CorrelationManager "
            "(threshold=%.2f, lookback=%dd)",
            correlation_threshold,
            lookback_days,
        )

    # ------------------------------------------------------------------
    # Data ingestion
    # ------------------------------------------------------------------

    def update_prices(self, pair: str, prices: pd.Series) -> None:
        """
        Store or update price series for a trading pair.

        Args:
            pair: Trading pair symbol (e.g. ``"BTC/USDT"``).
            prices: Pandas Series of close prices with a datetime index.
        """
        self._price_data[pair] = prices.sort_index()
        logger.debug("CorrelationManager: updated prices for %s (%d rows)", pair, len(prices))

    # ------------------------------------------------------------------
    # Core methods
    # ------------------------------------------------------------------

    def get_correlation_matrix(
        self,
        lookback_days: Optional[int] = None,
    ) -> pd.DataFrame:
        """
        Return the pairwise correlation matrix for all tracked pairs.

        Args:
            lookback_days: Number of calendar days of data to use.
                Falls back to ``self.lookback_days`` when None.

        Returns:
            DataFrame of pairwise Pearson correlations.  Returns an empty
            DataFrame when fewer than 2 pairs have data.
        """
        days = lookback_days or self.lookback_days
        if len(self._price_data) < 2:
            logger.warning("CorrelationManager: fewer than 2 pairs available")
            return pd.DataFrame()

        cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=days)
        returns: Dict[str, pd.Series] = {}
        for pair, prices in self._price_data.items():
            sliced = prices[prices.index >= cutoff] if not prices.empty else prices
            if len(sliced) < 2:
                continue
            returns[pair] = sliced.pct_change().dropna()

        if len(returns) < 2:
            return pd.DataFrame()

        df = pd.DataFrame(returns)
        corr = df.corr(method="pearson")
        return corr

    def get_max_correlated_exposure(
        self,
        positions: Dict[str, float],
    ) -> float:
        """
        Return the effective concentration of the portfolio due to correlation.

        Finds the largest cluster of correlated positions (|corr| > threshold)
        and returns the sum of their notional weights as a proxy for
        concentration risk.

        Args:
            positions: Dict mapping pair to notional exposure (e.g. in USD).

        Returns:
            Float in [0, 1] representing the fraction of total portfolio
            exposure that is concentrated in a correlated cluster.
        """
        if not positions:
            return 0.0

        total = sum(abs(v) for v in positions.values())
        if total == 0:
            return 0.0

        corr = self.get_correlation_matrix()
        if corr.empty:
            return 0.0

        # Build adjacency: which pairs are highly correlated
        pairs = list(positions.keys())
        # Find max cluster sum
        max_cluster = 0.0
        for base in pairs:
            if base not in corr.index:
                continue
            cluster = abs(positions.get(base, 0.0))
            for other in pairs:
                if other == base or other not in corr.columns:
                    continue
                if abs(corr.loc[base, other]) >= self.correlation_threshold:
                    cluster += abs(positions.get(other, 0.0))
            max_cluster = max(max_cluster, cluster)

        return max_cluster / total

    def should_reduce_position(
        self,
        new_pair: str,
        existing_positions: Dict[str, float],
    ) -> Tuple[bool, float]:
        """
        Advise whether to reduce the size of a new position due to correlation.

        If an existing position is highly correlated with ``new_pair`` the
        recommended sizing multiplier is 0.5 (50% reduction).  If two or more
        existing positions are highly correlated the multiplier is 0.25.

        Args:
            new_pair: The pair being considered for a new position.
            existing_positions: Current open positions (pair → notional).

        Returns:
            Tuple of (should_reduce: bool, sizing_multiplier: float).
            ``sizing_multiplier`` is 1.0 when no reduction is recommended.
        """
        corr = self.get_correlation_matrix()
        if corr.empty or new_pair not in corr.index:
            return False, 1.0

        high_corr_count = 0
        for pair in existing_positions:
            if pair == new_pair or pair not in corr.columns:
                continue
            if abs(corr.loc[new_pair, pair]) >= self.correlation_threshold:
                high_corr_count += 1
                logger.info(
                    "CorrelationManager: %s correlated with existing %s "
                    "(|r|=%.2f >= %.2f)",
                    new_pair,
                    pair,
                    abs(corr.loc[new_pair, pair]),
                    self.correlation_threshold,
                )

        if high_corr_count == 0:
            return False, 1.0
        if high_corr_count == 1:
            return True, 0.5
        return True, 0.25
