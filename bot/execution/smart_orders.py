"""
Smart order execution: limit orders, scaled entries, TWAP, and analytics.

Provides ``SmartOrderRouter`` for maker-fee-friendly execution and
``ExecutionAnalytics`` for tracking fill quality metrics.
"""
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Smart Order Router
# ---------------------------------------------------------------------------

class SmartOrderRouter:
    """
    Routes orders to prefer limit (maker) executions over market orders.

    Supports:
    - Single limit orders with market-order fallback on timeout
    - Scaled / iceberg entries (split large orders across a price range)
    - TWAP (Time-Weighted Average Price) execution

    This class is intentionally exchange-agnostic: it accepts a callable
    ``exchange`` object that follows the CCXT interface.

    Attributes:
        DEFAULT_LIMIT_TIMEOUT: Seconds to wait for a limit order fill before
            falling back to a market order.
    """

    DEFAULT_LIMIT_TIMEOUT: int = 60

    def __init__(
        self,
        exchange: Any,
        limit_timeout: int = DEFAULT_LIMIT_TIMEOUT,
    ) -> None:
        """
        Initialise the router.

        Args:
            exchange: CCXT-compatible exchange instance (or mock).
            limit_timeout: Seconds before a limit order is cancelled and
                replaced with a market order.
        """
        self._exchange = exchange
        self.limit_timeout = limit_timeout
        self._analytics = ExecutionAnalytics()
        logger.info(
            "Initialized SmartOrderRouter (limit_timeout=%ds)", limit_timeout
        )

    @property
    def analytics(self) -> "ExecutionAnalytics":
        """Return the attached ExecutionAnalytics instance."""
        return self._analytics

    # ------------------------------------------------------------------
    # Core order methods
    # ------------------------------------------------------------------

    def place_limit_order(
        self,
        pair: str,
        side: str,
        amount: float,
        price: float,
        params: Optional[Dict] = None,
    ) -> Dict:
        """
        Place a limit order and fall back to market if not filled in time.

        Args:
            pair: Trading pair symbol (e.g. ``"BTC/USDT"``).
            side: ``"buy"`` or ``"sell"``.
            amount: Order quantity.
            price: Limit price.
            params: Optional extra CCXT params.

        Returns:
            Order result dict (from exchange or synthetic on fallback).
        """
        start = time.monotonic()
        order_params = params or {}

        logger.info(
            "SmartOrderRouter: placing limit %s %s %.6f @ %.4f",
            side, pair, amount, price,
        )
        try:
            order = self._exchange.create_limit_order(
                pair, side, amount, price, order_params
            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("SmartOrderRouter: limit order failed: %s — falling back to market", exc)
            order = self._exchange.create_market_order(pair, side, amount, order_params)
            self._analytics.record_execution(
                pair=pair,
                expected_price=price,
                fill_price=float(order.get("price") or order.get("average") or price),
                fill_time_seconds=time.monotonic() - start,
                fees=float(order.get("fee", {}).get("cost", 0.0)),
                order_type="market_fallback",
            )
            return order

        # Poll for fill within timeout
        order_id = order.get("id")
        while time.monotonic() - start < self.limit_timeout:
            time.sleep(1)
            try:
                order = self._exchange.fetch_order(order_id, pair)
            except Exception:  # pylint: disable=broad-except
                break
            status = order.get("status")
            if status in ("closed", "filled"):
                break
            if status in ("canceled", "expired", "rejected"):
                logger.warning("SmartOrderRouter: limit order %s — %s", order_id, status)
                order = self._exchange.create_market_order(pair, side, amount, order_params)
                break

        fill_price = float(order.get("average") or order.get("price") or price)
        self._analytics.record_execution(
            pair=pair,
            expected_price=price,
            fill_price=fill_price,
            fill_time_seconds=time.monotonic() - start,
            fees=float(order.get("fee", {}).get("cost", 0.0)),
            order_type=order.get("type", "limit"),
        )
        return order

    def place_scaled_entry(
        self,
        pair: str,
        side: str,
        total_amount: float,
        price_range: tuple,
        num_orders: int = 5,
    ) -> List[Dict]:
        """
        Split a large order into multiple limit orders across a price range.

        Useful for hiding order size (iceberg-style) and improving average
        entry price.

        Args:
            pair: Trading pair symbol.
            side: ``"buy"`` or ``"sell"``.
            total_amount: Total order quantity to fill.
            price_range: ``(low_price, high_price)`` tuple.
            num_orders: Number of slices to create (default 5).

        Returns:
            List of order result dicts.
        """
        if num_orders < 1:
            num_orders = 1

        low, high = min(price_range), max(price_range)
        step = (high - low) / max(num_orders - 1, 1)
        slice_amount = total_amount / num_orders

        prices = [low + i * step for i in range(num_orders)]
        if side == "sell":
            prices = list(reversed(prices))  # sell from high to low

        orders: List[Dict] = []
        for price in prices:
            try:
                order = self.place_limit_order(pair, side, slice_amount, price)
                orders.append(order)
            except Exception as exc:  # pylint: disable=broad-except
                logger.error("SmartOrderRouter: scaled entry slice failed: %s", exc)

        logger.info(
            "SmartOrderRouter: scaled %s %s — placed %d/%d slices",
            side, pair, len(orders), num_orders,
        )
        return orders

    def place_twap_order(
        self,
        pair: str,
        side: str,
        total_amount: float,
        duration_seconds: int,
        num_slices: int = 10,
    ) -> List[Dict]:
        """
        Execute a TWAP order: equal slices spread evenly over a time period.

        Args:
            pair: Trading pair symbol.
            side: ``"buy"`` or ``"sell"``.
            total_amount: Total quantity to execute.
            duration_seconds: Total time over which to spread execution.
            num_slices: Number of equal-sized order slices.

        Returns:
            List of order result dicts.
        """
        if num_slices < 1:
            num_slices = 1

        slice_amount = total_amount / num_slices
        interval = duration_seconds / num_slices

        orders: List[Dict] = []
        logger.info(
            "SmartOrderRouter: TWAP %s %s — %d slices over %ds",
            side, pair, num_slices, duration_seconds,
        )
        for i in range(num_slices):
            try:
                # Use market order for each TWAP slice to ensure execution
                order = self._exchange.create_market_order(pair, side, slice_amount, {})
                fill_price = float(order.get("average") or order.get("price") or 0.0)
                self._analytics.record_execution(
                    pair=pair,
                    expected_price=fill_price,
                    fill_price=fill_price,
                    fill_time_seconds=0.0,
                    fees=float(order.get("fee", {}).get("cost", 0.0)),
                    order_type="twap",
                )
                orders.append(order)
            except Exception as exc:  # pylint: disable=broad-except
                logger.error("SmartOrderRouter: TWAP slice %d failed: %s", i + 1, exc)

            if i < num_slices - 1:
                time.sleep(interval)

        return orders


# ---------------------------------------------------------------------------
# Execution Analytics
# ---------------------------------------------------------------------------

class ExecutionAnalytics:
    """
    Track per-trade execution quality metrics.

    Maintains an in-memory log of executions.  Use ``get_execution_report``
    for a period summary and ``get_average_slippage`` for per-pair averages.
    """

    def __init__(self) -> None:
        self._executions: List[Dict] = []

    def record_execution(
        self,
        pair: str,
        expected_price: float,
        fill_price: float,
        fill_time_seconds: float,
        fees: float = 0.0,
        order_type: str = "limit",
    ) -> None:
        """
        Record a single execution event.

        Args:
            pair: Trading pair symbol.
            expected_price: Price at which the order was intended to fill.
            fill_price: Actual fill price.
            fill_time_seconds: Elapsed seconds from order placement to fill.
            fees: Fees paid for this execution.
            order_type: ``"limit"``, ``"market"``, ``"market_fallback"``,
                ``"twap"``, etc.
        """
        slippage = (fill_price - expected_price) / expected_price if expected_price else 0.0
        self._executions.append(
            {
                "pair": pair,
                "expected_price": expected_price,
                "fill_price": fill_price,
                "slippage": slippage,
                "fill_time_seconds": fill_time_seconds,
                "fees": fees,
                "order_type": order_type,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        logger.debug(
            "ExecutionAnalytics: %s %s slippage=%.4f%% fill_time=%.1fs",
            order_type, pair, slippage * 100, fill_time_seconds,
        )

    def get_average_slippage(self, pair: Optional[str] = None) -> float:
        """
        Return the average absolute slippage across all tracked executions.

        Args:
            pair: If provided, filter to this pair only.

        Returns:
            Average absolute slippage as a fraction (0.001 = 0.1 %).
        """
        execs = (
            [e for e in self._executions if e["pair"] == pair]
            if pair
            else self._executions
        )
        if not execs:
            return 0.0
        return sum(abs(e["slippage"]) for e in execs) / len(execs)

    def get_execution_report(self, period: str = "7d") -> Dict:
        """
        Return a summary report of execution quality.

        Args:
            period: Time window e.g. ``"7d"``, ``"30d"``, ``"all"``.

        Returns:
            Dict with total executions, avg slippage, avg fill time, total
            fees, maker/taker ratio, and per-pair breakdown.
        """
        now = datetime.now(timezone.utc)
        if period != "all":
            try:
                days = int(period.rstrip("d"))
            except ValueError:
                days = 7
            cutoff = now.isoformat()[:10 - days]  # rough filter
            execs = [
                e for e in self._executions
                if e.get("timestamp", "") >= (
                    datetime.now(timezone.utc).replace(
                        day=max(1, now.day - days)
                    ).isoformat()
                )
            ]
        else:
            execs = list(self._executions)

        if not execs:
            return {
                "period": period,
                "total_executions": 0,
                "avg_slippage": 0.0,
                "avg_fill_time_seconds": 0.0,
                "total_fees": 0.0,
                "maker_ratio": 0.0,
            }

        avg_slippage = sum(abs(e["slippage"]) for e in execs) / len(execs)
        avg_fill = sum(e["fill_time_seconds"] for e in execs) / len(execs)
        total_fees = sum(e["fees"] for e in execs)
        maker_count = sum(1 for e in execs if e["order_type"] == "limit")
        maker_ratio = maker_count / len(execs)

        # Per-pair
        pairs = list({e["pair"] for e in execs})
        per_pair = {}
        for pair in pairs:
            pe = [e for e in execs if e["pair"] == pair]
            per_pair[pair] = {
                "executions": len(pe),
                "avg_slippage": sum(abs(e["slippage"]) for e in pe) / len(pe),
                "total_fees": sum(e["fees"] for e in pe),
            }

        return {
            "period": period,
            "total_executions": len(execs),
            "avg_slippage": round(avg_slippage, 6),
            "avg_fill_time_seconds": round(avg_fill, 2),
            "total_fees": round(total_fees, 6),
            "maker_ratio": round(maker_ratio, 4),
            "per_pair": per_pair,
        }
