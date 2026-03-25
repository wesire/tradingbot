"""
Walk-forward analysis for strategy validation.

Splits price data into rolling in-sample and out-of-sample windows, trains
strategy parameters on each in-sample window, evaluates on the corresponding
out-of-sample window, and aggregates the results to detect overfitting.
"""
import logging
import math
import statistics
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class WindowResult:
    """Performance for a single walk-forward window."""

    window_index: int
    in_sample_start: int
    in_sample_end: int
    out_sample_start: int
    out_sample_end: int
    in_sample_sharpe: float
    out_sample_sharpe: float
    in_sample_win_rate: float
    out_sample_win_rate: float
    in_sample_trades: int
    out_sample_trades: int
    best_params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WalkForwardReport:
    """Aggregated results from all walk-forward windows."""

    windows: List[WindowResult]
    avg_out_sample_sharpe: float
    avg_out_sample_win_rate: float
    overfitting_ratio: float          # IS Sharpe / OOS Sharpe (< 2.0 is healthy)
    total_out_sample_trades: int
    is_overfitting: bool              # True when ratio >= 2.0


# ---------------------------------------------------------------------------
# Default strategy / objective helpers
# ---------------------------------------------------------------------------

def _default_returns(
    prices: Sequence[float],
    lookback: int = 5,
    long_only: bool = True,
) -> List[float]:
    """Simple momentum strategy returns for a given parameter set."""
    prices_list = list(prices)
    n = len(prices_list)
    if n < lookback + 1:
        return []
    returns: List[float] = []
    for i in range(lookback, n - 1):
        momentum = (prices_list[i] - prices_list[i - lookback]) / prices_list[i - lookback]
        direction = 1 if momentum > 0 else (-1 if not long_only else 0)
        if direction == 0:
            continue
        r = (prices_list[i + 1] - prices_list[i]) / prices_list[i] * direction
        returns.append(r)
    return returns


def _sharpe(returns: List[float]) -> float:
    """Annualised Sharpe ratio (rf=0, 252-day annualisation)."""
    if len(returns) < 2:
        return 0.0
    mean_r = statistics.mean(returns)
    stdev_r = statistics.stdev(returns)
    return (mean_r / stdev_r) * math.sqrt(252) if stdev_r > 0 else 0.0


def _win_rate(returns: List[float]) -> float:
    if not returns:
        return 0.0
    return sum(1 for r in returns if r > 0) / len(returns)


# ---------------------------------------------------------------------------
# WalkForwardAnalyzer
# ---------------------------------------------------------------------------

class WalkForwardAnalyzer:
    """
    Walk-forward analysis for strategy parameter validation.

    Slides an in-sample/out-of-sample window pair across the price series,
    optimises strategy parameters on each in-sample portion, and evaluates
    on the unseen out-of-sample portion.

    Example::

        analyzer = WalkForwardAnalyzer(
            in_sample_bars=180,
            out_sample_bars=30,
        )
        report = analyzer.run(prices)
        print(report.avg_out_sample_sharpe)
        print("Overfitting detected:", report.is_overfitting)
    """

    OVERFITTING_RATIO_THRESHOLD = 2.0

    def __init__(
        self,
        in_sample_bars: int = 180,
        out_sample_bars: int = 30,
        strategy_fn: Optional[Callable[..., List[float]]] = None,
        param_grid: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """
        Initialise the analyser.

        Args:
            in_sample_bars: Number of bars in each in-sample window.
            out_sample_bars: Number of bars in each out-of-sample window.
            strategy_fn: Callable ``(prices, **params) -> [float, ...]`` that
                returns per-trade returns.  Defaults to a simple momentum
                strategy.
            param_grid: List of parameter dicts to try during optimisation.
                Defaults to varying the ``lookback`` period over {3, 5, 10}.
        """
        if in_sample_bars < 2 or out_sample_bars < 1:
            raise ValueError(
                "in_sample_bars must be >= 2 and out_sample_bars >= 1"
            )
        self.in_sample_bars = in_sample_bars
        self.out_sample_bars = out_sample_bars
        self._strategy_fn = strategy_fn or _default_returns
        self._param_grid = param_grid or [
            {"lookback": 3},
            {"lookback": 5},
            {"lookback": 10},
        ]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        prices: Sequence[float],
        prices_extra: Optional[Dict[str, Sequence[float]]] = None,
    ) -> WalkForwardReport:
        """
        Run walk-forward analysis.

        Args:
            prices: Full time-ordered close-price series.
            prices_extra: Additional data series passed to *strategy_fn*
                as keyword arguments (e.g. ``{"sentiment": [...]})``).

        Returns:
            :class:`WalkForwardReport` with per-window and aggregate metrics.
        """
        prices_list = list(prices)
        n = len(prices_list)
        window_size = self.in_sample_bars + self.out_sample_bars

        if n < window_size:
            raise ValueError(
                f"Need at least {window_size} bars but got {n}. "
                "Reduce in_sample_bars or out_sample_bars."
            )

        windows: List[WindowResult] = []
        idx = 0
        window_index = 0

        while idx + window_size <= n:
            is_start = idx
            is_end = idx + self.in_sample_bars
            oos_start = is_end
            oos_end = is_end + self.out_sample_bars

            is_prices = prices_list[is_start:is_end]
            oos_prices = prices_list[oos_start:oos_end]

            # Optimise on in-sample
            best_params, best_is_sharpe = self._optimise(is_prices)
            is_returns = self._strategy_fn(is_prices, **best_params)

            # Evaluate on out-of-sample
            oos_returns = self._strategy_fn(oos_prices, **best_params)

            result = WindowResult(
                window_index=window_index,
                in_sample_start=is_start,
                in_sample_end=is_end,
                out_sample_start=oos_start,
                out_sample_end=oos_end,
                in_sample_sharpe=best_is_sharpe,
                out_sample_sharpe=_sharpe(oos_returns),
                in_sample_win_rate=_win_rate(is_returns),
                out_sample_win_rate=_win_rate(oos_returns),
                in_sample_trades=len(is_returns),
                out_sample_trades=len(oos_returns),
                best_params=best_params,
            )
            windows.append(result)
            logger.debug(
                "WFA window %d: IS Sharpe=%.3f OOS Sharpe=%.3f params=%s",
                window_index,
                result.in_sample_sharpe,
                result.out_sample_sharpe,
                best_params,
            )

            idx += self.out_sample_bars  # slide by OOS size
            window_index += 1

        if not windows:
            return WalkForwardReport(
                windows=[],
                avg_out_sample_sharpe=0.0,
                avg_out_sample_win_rate=0.0,
                overfitting_ratio=0.0,
                total_out_sample_trades=0,
                is_overfitting=False,
            )

        oos_sharpes = [w.out_sample_sharpe for w in windows]
        oos_win_rates = [w.out_sample_win_rate for w in windows]
        is_sharpes = [w.in_sample_sharpe for w in windows]

        avg_oos_sharpe = statistics.mean(oos_sharpes)
        avg_is_sharpe = statistics.mean(is_sharpes)
        avg_oos_wr = statistics.mean(oos_win_rates)
        total_oos_trades = sum(w.out_sample_trades for w in windows)

        overfitting_ratio = (
            avg_is_sharpe / avg_oos_sharpe
            if avg_oos_sharpe > 0
            else float("inf")
        )
        is_overfitting = overfitting_ratio >= self.OVERFITTING_RATIO_THRESHOLD

        report = WalkForwardReport(
            windows=windows,
            avg_out_sample_sharpe=avg_oos_sharpe,
            avg_out_sample_win_rate=avg_oos_wr,
            overfitting_ratio=overfitting_ratio,
            total_out_sample_trades=total_oos_trades,
            is_overfitting=is_overfitting,
        )

        logger.info(
            "WalkForwardAnalyzer: %d windows, avg OOS Sharpe=%.3f, "
            "overfitting ratio=%.2f (%s)",
            len(windows),
            avg_oos_sharpe,
            overfitting_ratio,
            "OVERFIT" if is_overfitting else "OK",
        )
        return report

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _optimise(
        self, prices: Sequence[float]
    ) -> Tuple[Dict[str, Any], float]:
        """
        Grid-search over *param_grid* and return the best params by Sharpe.

        Args:
            prices: In-sample price series.

        Returns:
            Tuple of ``(best_params, best_sharpe)``.
        """
        best_params: Dict[str, Any] = self._param_grid[0]
        best_sharpe = -float("inf")

        for params in self._param_grid:
            try:
                rets = self._strategy_fn(prices, **params)
                s = _sharpe(rets)
                if s > best_sharpe:
                    best_sharpe = s
                    best_params = params
            except Exception as exc:
                logger.debug("WFA: error with params %s: %s", params, exc)

        return best_params, best_sharpe
