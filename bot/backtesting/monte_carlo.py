"""
Monte Carlo simulation for trading strategy risk assessment.

Randomly resamples a sequence of historical trade returns to estimate the
distribution of key performance metrics (final equity, max drawdown, Sharpe
ratio) and derive risk-of-ruin probabilities and percentile outcomes.

Matplotlib is an optional dependency: plots are saved only when available.
"""
import logging
import math
import random
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

try:
    import matplotlib
    matplotlib.use("Agg")  # non-interactive backend
    import matplotlib.pyplot as plt
    _MATPLOTLIB_AVAILABLE = True
except ImportError:  # pragma: no cover
    _MATPLOTLIB_AVAILABLE = False
    logger.debug("matplotlib not available — plots will be skipped")


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class SimulationResult:
    """Summary statistics from a Monte Carlo simulation run."""

    n_simulations: int
    final_equity_mean: float
    final_equity_std: float
    sharpe_mean: float
    sharpe_std: float
    max_drawdown_mean: float
    max_drawdown_std: float
    equity_percentiles: Dict[int, float] = field(default_factory=dict)
    sharpe_percentiles: Dict[int, float] = field(default_factory=dict)
    drawdown_percentiles: Dict[int, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _equity_curve(returns: List[float]) -> List[float]:
    """Return cumulative equity curve starting at 1.0."""
    equity = 1.0
    curve = [equity]
    for r in returns:
        equity *= 1.0 + r
        curve.append(equity)
    return curve


def _max_drawdown(equity: List[float]) -> float:
    """Peak-to-trough drawdown as a positive fraction."""
    peak = equity[0]
    max_dd = 0.0
    for val in equity:
        peak = max(peak, val)
        dd = (peak - val) / peak
        max_dd = max(max_dd, dd)
    return max_dd


def _sharpe(returns: List[float]) -> float:
    """Annualised Sharpe ratio (rf=0)."""
    if len(returns) < 2:
        return 0.0
    mean_r = statistics.mean(returns)
    stdev_r = statistics.stdev(returns)
    return (mean_r / stdev_r) * math.sqrt(252) if stdev_r > 0 else 0.0


def _percentile(data: List[float], pct: int) -> float:
    """Simple percentile via sorted index."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * pct / 100
    lo = int(k)
    hi = lo + 1
    if hi >= len(sorted_data):
        return sorted_data[-1]
    frac = k - lo
    return sorted_data[lo] * (1 - frac) + sorted_data[hi] * frac


# ---------------------------------------------------------------------------
# MonteCarloSimulator
# ---------------------------------------------------------------------------

class MonteCarloSimulator:
    """
    Monte Carlo simulation for trade-sequence risk assessment.

    Randomly resamples the provided trade returns *n_simulations* times to
    produce confidence intervals for final equity, max drawdown, and Sharpe
    ratio.

    Example::

        sim = MonteCarloSimulator(seed=42)
        result = sim.run_simulation(trade_returns, n_simulations=1000)
        print("Median final equity:", result.equity_percentiles[50])
        ror = sim.get_risk_of_ruin(threshold=0.20)
        print(f"Risk of ruin (20 % drawdown): {ror:.1%}")
        outcomes = sim.get_percentile_outcomes([5, 25, 50, 75, 95])
        sim.plot_results("/tmp/mc_results.png")
    """

    def __init__(self, seed: Optional[int] = None) -> None:
        """
        Initialise the simulator.

        Args:
            seed: Optional random seed for reproducibility.
        """
        self._rng = random.Random(seed)
        self._sim_equities: List[List[float]] = []
        self._sim_sharpes: List[float] = []
        self._sim_drawdowns: List[float] = []
        self._result: Optional[SimulationResult] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_simulation(
        self,
        trade_returns: Sequence[float],
        n_simulations: int = 1000,
        percentiles: List[int] = None,  # type: ignore[assignment]
    ) -> SimulationResult:
        """
        Randomly resample *trade_returns* to estimate outcome distributions.

        Args:
            trade_returns: Historical per-trade fractional returns.
            n_simulations: Number of random resamples (default 1000).
            percentiles: Percentile levels to compute (default
                ``[5, 25, 50, 75, 95]``).

        Returns:
            :class:`SimulationResult` with summary statistics.
        """
        if percentiles is None:
            percentiles = [5, 25, 50, 75, 95]

        returns_list = list(trade_returns)
        n_trades = len(returns_list)

        if n_trades == 0:
            logger.warning("MonteCarloSimulator: empty trade_returns")
            self._result = SimulationResult(
                n_simulations=0,
                final_equity_mean=1.0,
                final_equity_std=0.0,
                sharpe_mean=0.0,
                sharpe_std=0.0,
                max_drawdown_mean=0.0,
                max_drawdown_std=0.0,
            )
            return self._result

        final_equities: List[float] = []
        sharpes: List[float] = []
        max_drawdowns: List[float] = []
        sim_equities: List[List[float]] = []

        for _ in range(n_simulations):
            sampled = self._rng.choices(returns_list, k=n_trades)
            equity = _equity_curve(sampled)
            final_equities.append(equity[-1])
            sharpes.append(_sharpe(sampled))
            max_drawdowns.append(_max_drawdown(equity))
            sim_equities.append(equity)

        self._sim_equities = sim_equities
        self._sim_sharpes = sharpes
        self._sim_drawdowns = max_drawdowns

        eq_pcts = {p: _percentile(final_equities, p) for p in percentiles}
        sh_pcts = {p: _percentile(sharpes, p) for p in percentiles}
        dd_pcts = {p: _percentile(max_drawdowns, p) for p in percentiles}

        self._result = SimulationResult(
            n_simulations=n_simulations,
            final_equity_mean=statistics.mean(final_equities),
            final_equity_std=statistics.stdev(final_equities) if len(final_equities) > 1 else 0.0,
            sharpe_mean=statistics.mean(sharpes),
            sharpe_std=statistics.stdev(sharpes) if len(sharpes) > 1 else 0.0,
            max_drawdown_mean=statistics.mean(max_drawdowns),
            max_drawdown_std=statistics.stdev(max_drawdowns) if len(max_drawdowns) > 1 else 0.0,
            equity_percentiles=eq_pcts,
            sharpe_percentiles=sh_pcts,
            drawdown_percentiles=dd_pcts,
        )

        logger.info(
            "MonteCarloSimulator: %d simulations — "
            "median equity=%.3f, p95 drawdown=%.2f%%, mean Sharpe=%.3f",
            n_simulations,
            eq_pcts.get(50, 0.0),
            dd_pcts.get(95, 0.0) * 100,
            statistics.mean(sharpes),
        )
        return self._result

    def get_risk_of_ruin(self, threshold: float = 0.20) -> float:
        """
        Estimate the probability of hitting a given max-drawdown threshold.

        Args:
            threshold: Maximum-drawdown fraction considered "ruin" (e.g.
                ``0.20`` = 20 %).

        Returns:
            Probability in [0, 1].

        Raises:
            RuntimeError: if :meth:`run_simulation` has not been called yet.
        """
        if not self._sim_drawdowns:
            raise RuntimeError(
                "No simulation results available. Call run_simulation() first."
            )
        ruined = sum(1 for dd in self._sim_drawdowns if dd >= threshold)
        return ruined / len(self._sim_drawdowns)

    def get_percentile_outcomes(
        self, percentiles: List[int] = None  # type: ignore[assignment]
    ) -> Dict[int, float]:
        """
        Return final equity at the requested percentile levels.

        Args:
            percentiles: Percentile levels (default ``[5, 25, 50, 75, 95]``).

        Returns:
            Dict mapping percentile → final equity.

        Raises:
            RuntimeError: if :meth:`run_simulation` has not been called yet.
        """
        if self._result is None:
            raise RuntimeError(
                "No simulation results available. Call run_simulation() first."
            )
        if percentiles is None:
            percentiles = [5, 25, 50, 75, 95]
        final_equities = [eq[-1] for eq in self._sim_equities]
        return {p: _percentile(final_equities, p) for p in percentiles}

    def plot_results(self, output_path: str) -> Optional[str]:
        """
        Save a visualisation of the simulation results as a PNG image.

        Requires matplotlib.  Returns ``None`` when matplotlib is unavailable.

        Args:
            output_path: Destination PNG file path.

        Returns:
            Absolute path of the saved image, or ``None`` if matplotlib is
            not installed.

        Raises:
            RuntimeError: if :meth:`run_simulation` has not been called yet.
        """
        if self._result is None:
            raise RuntimeError(
                "No simulation results available. Call run_simulation() first."
            )

        if not _MATPLOTLIB_AVAILABLE:
            logger.warning(
                "MonteCarloSimulator: matplotlib not available — "
                "skipping plot"
            )
            return None

        fig, axes = plt.subplots(1, 3, figsize=(15, 5))
        fig.suptitle(
            f"Monte Carlo Simulation ({self._result.n_simulations:,} runs)"
        )

        # Equity curves (sample up to 200 paths)
        ax = axes[0]
        sample_paths = self._sim_equities[: min(200, len(self._sim_equities))]
        for path in sample_paths:
            ax.plot(path, alpha=0.05, color="steelblue", linewidth=0.5)
        # Median line
        if self._sim_equities:
            min_len = min(len(p) for p in self._sim_equities)
            median_path = [
                _percentile([p[i] for p in self._sim_equities], 50)
                for i in range(min_len)
            ]
            ax.plot(median_path, color="red", linewidth=1.5, label="Median")
        ax.set_title("Equity Curves")
        ax.set_xlabel("Trade #")
        ax.set_ylabel("Equity")
        ax.legend(fontsize=8)

        # Final equity distribution
        ax = axes[1]
        final_equities = [eq[-1] for eq in self._sim_equities]
        ax.hist(final_equities, bins=50, color="steelblue", edgecolor="white")
        ax.axvline(
            _percentile(final_equities, 5),
            color="red",
            linestyle="--",
            label="P5",
        )
        ax.axvline(
            _percentile(final_equities, 50),
            color="green",
            linestyle="--",
            label="P50",
        )
        ax.set_title("Final Equity Distribution")
        ax.set_xlabel("Final Equity")
        ax.set_ylabel("Frequency")
        ax.legend(fontsize=8)

        # Max drawdown distribution
        ax = axes[2]
        ax.hist(
            [dd * 100 for dd in self._sim_drawdowns],
            bins=50,
            color="firebrick",
            edgecolor="white",
        )
        ax.set_title("Max Drawdown Distribution")
        ax.set_xlabel("Max Drawdown (%)")
        ax.set_ylabel("Frequency")

        plt.tight_layout()
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(str(path), dpi=100)
        plt.close(fig)
        logger.info("MonteCarloSimulator: plot saved to %s", path)
        return str(path.resolve())
