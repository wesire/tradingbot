"""
Risk-parity position allocator.

Implements inverse-volatility weighting so that each trading pair
contributes equally to overall portfolio risk.  Higher-volatility pairs
receive proportionally smaller allocations.
"""
import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class RiskParityAllocator:
    """
    Inverse-volatility position sizer (risk-parity allocation).

    Each pair's weight is proportional to the inverse of its realised
    volatility so that every pair contributes the same amount of risk to
    the portfolio.

    Attributes:
        DEFAULT_REBALANCE_THRESHOLD: Minimum drift (fraction) before a
            rebalance trade is recommended.
        DEFAULT_VOL_WINDOW: Rolling window (days) for volatility estimation.
    """

    DEFAULT_REBALANCE_THRESHOLD: float = 0.05  # 5 %
    DEFAULT_VOL_WINDOW: int = 30

    def __init__(
        self,
        rebalance_threshold: float = DEFAULT_REBALANCE_THRESHOLD,
        vol_window: int = DEFAULT_VOL_WINDOW,
    ) -> None:
        """
        Initialise the allocator.

        Args:
            rebalance_threshold: Minimum fractional drift from target before
                recommending a rebalance (default 0.05 = 5 %).
            vol_window: Rolling window in days for volatility estimation.
        """
        self.rebalance_threshold = rebalance_threshold
        self.vol_window = vol_window
        logger.info(
            "Initialized RiskParityAllocator "
            "(rebalance_threshold=%.2f, vol_window=%dd)",
            rebalance_threshold,
            vol_window,
        )

    # ------------------------------------------------------------------
    # Core methods
    # ------------------------------------------------------------------

    def calculate_weights(
        self,
        pairs_volatility: Dict[str, float],
    ) -> Dict[str, float]:
        """
        Compute inverse-volatility weights for each pair.

        Args:
            pairs_volatility: Mapping of pair → annualised volatility (or any
                positive volatility measure).  A volatility of 0 is replaced
                with a very small positive number to avoid division by zero.

        Returns:
            Dict mapping pair → weight (all weights sum to 1.0).
        """
        if not pairs_volatility:
            return {}

        inv_vols: Dict[str, float] = {}
        for pair, vol in pairs_volatility.items():
            safe_vol = max(vol, 1e-9)
            inv_vols[pair] = 1.0 / safe_vol

        total = sum(inv_vols.values())
        if total == 0:
            # Equal weight fallback
            n = len(pairs_volatility)
            return {p: 1.0 / n for p in pairs_volatility}

        weights = {pair: iv / total for pair, iv in inv_vols.items()}
        logger.debug("RiskParityAllocator: weights=%s", weights)
        return weights

    def estimate_volatility(
        self,
        price_series: pd.Series,
        annualise: bool = True,
    ) -> float:
        """
        Estimate realised volatility from a price series.

        Args:
            price_series: Daily close prices (index = datetime).
            annualise: If True, annualise the daily volatility by × √252.

        Returns:
            Volatility estimate as a positive float.
        """
        if len(price_series) < 2:
            return 1.0  # fallback

        window = min(self.vol_window, len(price_series) - 1)
        returns = price_series.pct_change().dropna().tail(window)
        daily_vol = float(returns.std())
        if annualise:
            return daily_vol * np.sqrt(252)
        return daily_vol

    def adjust_allocation(
        self,
        current_positions: Dict[str, float],
        market_data: Dict[str, pd.Series],
        total_capital: float = 1.0,
    ) -> List[Dict]:
        """
        Return recommended rebalancing trades.

        Compares current allocations against risk-parity targets and emits a
        trade recommendation for each pair whose drift exceeds
        ``rebalance_threshold``.

        Args:
            current_positions: Current notional exposure per pair.
            market_data: Price series per pair (for volatility estimation).
            total_capital: Total portfolio capital (used to compute target
                notional; defaults to 1.0 for fractional sizing).

        Returns:
            List of dicts with keys ``pair``, ``action`` (``"buy"`` /
            ``"sell"``), ``current_weight``, ``target_weight``,
            ``drift``, and ``recommended_delta`` (signed change in notional).
        """
        # Estimate volatilities
        vols: Dict[str, float] = {}
        for pair, prices in market_data.items():
            vols[pair] = self.estimate_volatility(prices)

        target_weights = self.calculate_weights(vols)
        if not target_weights:
            return []

        total_current = sum(abs(v) for v in current_positions.values()) or total_capital
        current_weights = {
            pair: abs(current_positions.get(pair, 0.0)) / total_current
            for pair in target_weights
        }

        recommendations: List[Dict] = []
        for pair, target_w in target_weights.items():
            current_w = current_weights.get(pair, 0.0)
            drift = abs(current_w - target_w)
            if drift < self.rebalance_threshold:
                continue
            delta_notional = (target_w - current_w) * total_current
            action = "buy" if delta_notional > 0 else "sell"
            recommendations.append(
                {
                    "pair": pair,
                    "action": action,
                    "current_weight": round(current_w, 4),
                    "target_weight": round(target_w, 4),
                    "drift": round(drift, 4),
                    "recommended_delta": round(delta_notional, 6),
                }
            )
            logger.info(
                "RiskParityAllocator: rebalance %s — %s %.4f "
                "(drift=%.2f%% > threshold=%.2f%%)",
                pair,
                action,
                abs(delta_notional),
                drift * 100,
                self.rebalance_threshold * 100,
            )

        return recommendations
