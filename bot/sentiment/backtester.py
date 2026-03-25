"""
Sentiment backtesting framework.

Validates that sentiment data improves trading performance by running a simple
strategy both with and without a sentiment overlay, then comparing key metrics
(Sharpe ratio, win rate, max drawdown, profit factor).
"""
import json
import logging
import math
import statistics
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class BacktestResult:
    """Performance metrics for a single backtest run."""

    label: str
    total_trades: int
    win_rate: float          # fraction in [0, 1]
    profit_factor: float     # gross profit / gross loss
    sharpe_ratio: float
    max_drawdown: float      # peak-to-trough as a positive fraction
    total_return: float      # fractional total return
    equity_curve: List[float] = field(default_factory=list, repr=False)

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a plain dictionary (without equity curve)."""
        d = asdict(self)
        d.pop("equity_curve", None)
        return d


@dataclass
class ComparisonReport:
    """Side-by-side comparison of two backtest runs."""

    without_sentiment: BacktestResult
    with_sentiment: BacktestResult
    sharpe_improvement_pct: float   # % improvement
    win_rate_delta: float           # absolute improvement
    drawdown_delta: float           # negative means improvement
    sentiment_adds_value: bool      # True when Sharpe improves

    def to_dict(self) -> Dict[str, Any]:
        return {
            "without_sentiment": self.without_sentiment.to_dict(),
            "with_sentiment": self.with_sentiment.to_dict(),
            "sharpe_improvement_pct": round(self.sharpe_improvement_pct, 4),
            "win_rate_delta": round(self.win_rate_delta, 4),
            "drawdown_delta": round(self.drawdown_delta, 4),
            "sentiment_adds_value": self.sentiment_adds_value,
        }


# ---------------------------------------------------------------------------
# Strategy helpers
# ---------------------------------------------------------------------------

def _compute_metrics(
    returns: List[float], label: str
) -> BacktestResult:
    """
    Compute performance metrics from a list of per-trade returns.

    Args:
        returns: Fractional return for each trade (e.g. +0.02 = +2 %).
        label: Human-readable label for the result.

    Returns:
        :class:`BacktestResult` populated with computed metrics.
    """
    if not returns:
        return BacktestResult(
            label=label,
            total_trades=0,
            win_rate=0.0,
            profit_factor=0.0,
            sharpe_ratio=0.0,
            max_drawdown=0.0,
            total_return=0.0,
        )

    total_trades = len(returns)
    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r <= 0]

    win_rate = len(wins) / total_trades

    gross_profit = sum(wins) if wins else 0.0
    gross_loss = abs(sum(losses)) if losses else 0.0
    profit_factor = (
        gross_profit / gross_loss if gross_loss > 0 else float("inf")
    )

    total_return = sum(returns)

    # Sharpe ratio (annualised, assuming daily bars, rf=0)
    mean_r = statistics.mean(returns)
    stdev_r = statistics.stdev(returns) if len(returns) > 1 else 1e-9
    sharpe_ratio = (mean_r / stdev_r) * math.sqrt(252) if stdev_r > 0 else 0.0

    # Max drawdown
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    equity_curve: List[float] = [1.0]
    for r in returns:
        equity *= 1.0 + r
        peak = max(peak, equity)
        dd = (peak - equity) / peak
        max_dd = max(max_dd, dd)
        equity_curve.append(equity)

    return BacktestResult(
        label=label,
        total_trades=total_trades,
        win_rate=win_rate,
        profit_factor=profit_factor,
        sharpe_ratio=sharpe_ratio,
        max_drawdown=max_dd,
        total_return=total_return,
        equity_curve=equity_curve,
    )


def _run_simple_strategy(
    prices: Sequence[float],
    *,
    use_sentiment: bool = False,
    sentiment_scores: Optional[Sequence[float]] = None,
    sentiment_threshold: float = 0.3,
    long_only: bool = True,
) -> List[float]:
    """
    Minimal momentum/mean-reversion strategy for backtesting.

    Generates a long signal when the 5-period return is positive (or negative
    for mean-reversion).  With sentiment overlay enabled, a trade is only
    taken when the corresponding sentiment score exceeds *sentiment_threshold*
    (absolute value).

    Args:
        prices: Sequence of close prices.
        use_sentiment: Whether to apply sentiment filtering.
        sentiment_scores: Per-bar sentiment scores in [-1, 1].  Must be the
            same length as *prices* when *use_sentiment* is True.
        sentiment_threshold: Minimum |sentiment| required to enter a trade.
        long_only: When True, only enter long trades.

    Returns:
        List of per-trade fractional returns.
    """
    prices_list = list(prices)
    n = len(prices_list)
    if n < 6:
        return []

    scores = list(sentiment_scores) if sentiment_scores else [0.0] * n

    lookback = 5
    returns: List[float] = []

    for i in range(lookback, n - 1):
        momentum = (prices_list[i] - prices_list[i - lookback]) / prices_list[i - lookback]
        sentiment_val = scores[i] if i < len(scores) else 0.0

        # Signal: positive momentum → long; negative → short (if not long_only)
        if momentum > 0:
            direction = 1
        else:
            direction = -1 if not long_only else 0

        if direction == 0:
            continue

        if use_sentiment:
            if abs(sentiment_val) < sentiment_threshold:
                continue
            # Align trade direction with sentiment
            if direction == 1 and sentiment_val < 0:
                continue
            if direction == -1 and sentiment_val > 0:
                continue

        # Return = next-bar close change
        trade_return = (
            (prices_list[i + 1] - prices_list[i]) / prices_list[i]
        ) * direction
        returns.append(trade_return)

    return returns


# ---------------------------------------------------------------------------
# Main backtester class
# ---------------------------------------------------------------------------

class SentimentBacktester:
    """
    Validates whether sentiment data improves trading performance.

    Runs the same strategy with and without a sentiment overlay and compares
    key performance metrics.

    Example::

        backtester = SentimentBacktester(sentiment_threshold=0.3)
        backtester.run_backtest(prices, sentiment_scores)
        report = backtester.compare_results()
        print(report.sharpe_improvement_pct)
        backtester.generate_report("/tmp/sentiment_backtest.json")
    """

    def __init__(
        self,
        sentiment_threshold: float = 0.3,
        long_only: bool = True,
    ) -> None:
        """
        Initialise the backtester.

        Args:
            sentiment_threshold: Minimum |sentiment| required to enter a
                trade when the sentiment overlay is enabled (default 0.3).
            long_only: When True, only long trades are taken (default True).
        """
        self.sentiment_threshold = sentiment_threshold
        self.long_only = long_only
        self._result_without: Optional[BacktestResult] = None
        self._result_with: Optional[BacktestResult] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_backtest(
        self,
        historical_prices: Sequence[float],
        historical_sentiment: Sequence[float],
        strategy_params: Optional[Dict[str, Any]] = None,
    ) -> Tuple[BacktestResult, BacktestResult]:
        """
        Run the strategy both with and without the sentiment overlay.

        Args:
            historical_prices: Time-ordered sequence of close prices.
            historical_sentiment: Per-bar sentiment scores in [-1, 1].
                Must be the same length as *historical_prices*.
            strategy_params: Optional overrides for strategy parameters.
                Supported keys: ``sentiment_threshold``, ``long_only``.

        Returns:
            Tuple of ``(result_without_sentiment, result_with_sentiment)``.
        """
        if strategy_params:
            self.sentiment_threshold = strategy_params.get(
                "sentiment_threshold", self.sentiment_threshold
            )
            self.long_only = strategy_params.get("long_only", self.long_only)

        logger.info(
            "SentimentBacktester: running backtest on %d bars "
            "(threshold=%.2f, long_only=%s)",
            len(historical_prices),
            self.sentiment_threshold,
            self.long_only,
        )

        # Baseline: no sentiment filter
        baseline_returns = _run_simple_strategy(
            historical_prices,
            use_sentiment=False,
            long_only=self.long_only,
        )
        self._result_without = _compute_metrics(
            baseline_returns, label="without_sentiment"
        )

        # With sentiment overlay
        sentiment_returns = _run_simple_strategy(
            historical_prices,
            use_sentiment=True,
            sentiment_scores=historical_sentiment,
            sentiment_threshold=self.sentiment_threshold,
            long_only=self.long_only,
        )
        self._result_with = _compute_metrics(
            sentiment_returns, label="with_sentiment"
        )

        logger.info(
            "SentimentBacktester: without sentiment — "
            "Sharpe=%.3f, WR=%.2f%%, trades=%d",
            self._result_without.sharpe_ratio,
            self._result_without.win_rate * 100,
            self._result_without.total_trades,
        )
        logger.info(
            "SentimentBacktester: with sentiment — "
            "Sharpe=%.3f, WR=%.2f%%, trades=%d",
            self._result_with.sharpe_ratio,
            self._result_with.win_rate * 100,
            self._result_with.total_trades,
        )

        return self._result_without, self._result_with

    def compare_results(self) -> ComparisonReport:
        """
        Return a side-by-side comparison of the two backtest runs.

        Returns:
            :class:`ComparisonReport` with delta metrics.

        Raises:
            RuntimeError: if :meth:`run_backtest` has not been called yet.
        """
        if self._result_without is None or self._result_with is None:
            raise RuntimeError(
                "No backtest results available. Call run_backtest() first."
            )

        sharpe_base = self._result_without.sharpe_ratio
        sharpe_sent = self._result_with.sharpe_ratio

        if sharpe_base != 0:
            sharpe_improvement_pct = (
                (sharpe_sent - sharpe_base) / abs(sharpe_base) * 100
            )
        else:
            sharpe_improvement_pct = 0.0

        win_rate_delta = (
            self._result_with.win_rate - self._result_without.win_rate
        )
        drawdown_delta = (
            self._result_with.max_drawdown
            - self._result_without.max_drawdown
        )

        return ComparisonReport(
            without_sentiment=self._result_without,
            with_sentiment=self._result_with,
            sharpe_improvement_pct=sharpe_improvement_pct,
            win_rate_delta=win_rate_delta,
            drawdown_delta=drawdown_delta,
            sentiment_adds_value=sharpe_improvement_pct > 0,
        )

    def calculate_sentiment_edge(self) -> Dict[str, float]:
        """
        Quantify the improvement from adding sentiment.

        Returns:
            Dictionary with:
            - ``sharpe_improvement_pct``: % Sharpe improvement
            - ``win_rate_delta``: absolute win-rate improvement
            - ``drawdown_delta``: change in max drawdown (negative = better)
            - ``profit_factor_delta``: change in profit factor

        Raises:
            RuntimeError: if :meth:`run_backtest` has not been called yet.
        """
        report = self.compare_results()
        return {
            "sharpe_improvement_pct": report.sharpe_improvement_pct,
            "win_rate_delta": report.win_rate_delta,
            "drawdown_delta": report.drawdown_delta,
            "profit_factor_delta": (
                self._result_with.profit_factor  # type: ignore[union-attr]
                - self._result_without.profit_factor  # type: ignore[union-attr]
            ),
        }

    def generate_report(self, output_path: str) -> str:
        """
        Save a detailed comparison report as a JSON file.

        Args:
            output_path: Destination file path (will be created or overwritten).

        Returns:
            Absolute path of the saved report file.

        Raises:
            RuntimeError: if :meth:`run_backtest` has not been called yet.
        """
        report = self.compare_results()
        edge = self.calculate_sentiment_edge()

        output: Dict[str, Any] = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "strategy_params": {
                "sentiment_threshold": self.sentiment_threshold,
                "long_only": self.long_only,
            },
            "comparison": report.to_dict(),
            "sentiment_edge": edge,
        }

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(output, indent=2))
        logger.info("SentimentBacktester: report saved to %s", path)
        return str(path.resolve())
