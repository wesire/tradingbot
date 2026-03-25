"""
Unit tests for SentimentBacktester, WalkForwardAnalyzer, and MonteCarloSimulator.
"""
import json
import math
import os
import tempfile
import pytest

from bot.sentiment.backtester import (
    SentimentBacktester,
    BacktestResult,
    ComparisonReport,
    _compute_metrics,
    _run_simple_strategy,
)
from bot.backtesting.walk_forward import WalkForwardAnalyzer, WalkForwardReport
from bot.backtesting.monte_carlo import MonteCarloSimulator, SimulationResult


# ---------------------------------------------------------------------------
# Synthetic data helpers
# ---------------------------------------------------------------------------

def _synthetic_prices(n: int = 300, seed: int = 42) -> list:
    """Simple random walk price series."""
    import random
    rng = random.Random(seed)
    price = 100.0
    prices = [price]
    for _ in range(n - 1):
        price *= 1 + rng.gauss(0.0002, 0.02)
        prices.append(price)
    return prices


def _synthetic_sentiment(n: int = 300, seed: int = 7) -> list:
    """Random sentiment series in [-1, 1]."""
    import random
    rng = random.Random(seed)
    return [max(-1.0, min(1.0, rng.gauss(0.1, 0.4))) for _ in range(n)]


def _sample_trade_returns(n: int = 100, seed: int = 1) -> list:
    import random
    rng = random.Random(seed)
    # Mostly small gains/losses with occasional larger moves
    return [rng.gauss(0.002, 0.01) for _ in range(n)]


# ===========================================================================
# SentimentBacktester tests
# ===========================================================================

class TestSentimentBacktester:

    def test_run_backtest_returns_two_results(self):
        prices = _synthetic_prices()
        sentiment = _synthetic_sentiment(len(prices))
        bt = SentimentBacktester()
        without, with_sent = bt.run_backtest(prices, sentiment)
        assert isinstance(without, BacktestResult)
        assert isinstance(with_sent, BacktestResult)
        assert without.label == "without_sentiment"
        assert with_sent.label == "with_sentiment"

    def test_trade_counts_are_non_negative(self):
        prices = _synthetic_prices()
        sentiment = _synthetic_sentiment(len(prices))
        bt = SentimentBacktester()
        without, with_sent = bt.run_backtest(prices, sentiment)
        assert without.total_trades >= 0
        assert with_sent.total_trades >= 0

    def test_sentiment_filter_reduces_trades(self):
        """Sentiment overlay (threshold > 0) should not increase trade count."""
        prices = _synthetic_prices(500)
        sentiment = _synthetic_sentiment(500)
        bt = SentimentBacktester(sentiment_threshold=0.3)
        without, with_sent = bt.run_backtest(prices, sentiment)
        # Sentiment filter can only remove trades, never add
        assert with_sent.total_trades <= without.total_trades

    def test_compare_results_returns_report(self):
        prices = _synthetic_prices()
        sentiment = _synthetic_sentiment(len(prices))
        bt = SentimentBacktester()
        bt.run_backtest(prices, sentiment)
        report = bt.compare_results()
        assert isinstance(report, ComparisonReport)
        assert isinstance(report.sharpe_improvement_pct, float)
        assert isinstance(report.win_rate_delta, float)

    def test_compare_results_before_run_raises(self):
        bt = SentimentBacktester()
        with pytest.raises(RuntimeError):
            bt.compare_results()

    def test_calculate_sentiment_edge_keys(self):
        prices = _synthetic_prices()
        sentiment = _synthetic_sentiment(len(prices))
        bt = SentimentBacktester()
        bt.run_backtest(prices, sentiment)
        edge = bt.calculate_sentiment_edge()
        assert "sharpe_improvement_pct" in edge
        assert "win_rate_delta" in edge
        assert "drawdown_delta" in edge
        assert "profit_factor_delta" in edge

    def test_generate_report_creates_json(self):
        prices = _synthetic_prices()
        sentiment = _synthetic_sentiment(len(prices))
        bt = SentimentBacktester()
        bt.run_backtest(prices, sentiment)
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "report.json")
            bt.generate_report(output_path)
            assert os.path.exists(output_path)
            with open(output_path) as f:
                data = json.load(f)
            assert "comparison" in data
            assert "sentiment_edge" in data
            assert "generated_at" in data

    def test_generate_report_before_run_raises(self):
        bt = SentimentBacktester()
        with pytest.raises(RuntimeError):
            with tempfile.TemporaryDirectory() as tmpdir:
                bt.generate_report(os.path.join(tmpdir, "r.json"))

    def test_metrics_score_in_valid_range(self):
        prices = _synthetic_prices()
        sentiment = _synthetic_sentiment(len(prices))
        bt = SentimentBacktester()
        without, with_sent = bt.run_backtest(prices, sentiment)
        for result in (without, with_sent):
            assert 0.0 <= result.win_rate <= 1.0
            assert result.max_drawdown >= 0.0
            assert result.profit_factor >= 0.0

    def test_compute_metrics_empty_returns(self):
        """Empty return list produces zero-trade result."""
        result = _compute_metrics([], "test")
        assert result.total_trades == 0
        assert result.sharpe_ratio == 0.0

    def test_run_simple_strategy_no_sentiment(self):
        prices = _synthetic_prices(100)
        returns = _run_simple_strategy(prices, use_sentiment=False)
        assert isinstance(returns, list)

    def test_run_simple_strategy_with_sentiment(self):
        prices = _synthetic_prices(100)
        sentiment = _synthetic_sentiment(100)
        returns_no = _run_simple_strategy(prices, use_sentiment=False)
        returns_yes = _run_simple_strategy(
            prices, use_sentiment=True, sentiment_scores=sentiment
        )
        assert len(returns_yes) <= len(returns_no)

    def test_strategy_params_override(self):
        prices = _synthetic_prices(200)
        sentiment = _synthetic_sentiment(200)
        bt = SentimentBacktester()
        bt.run_backtest(
            prices, sentiment, strategy_params={"sentiment_threshold": 0.5}
        )
        assert bt.sentiment_threshold == 0.5

    def test_too_few_prices(self):
        """Strategy with fewer than 6 prices returns no trades."""
        prices = [100.0, 101.0, 102.0]
        sentiment = [0.0, 0.0, 0.0]
        bt = SentimentBacktester()
        without, with_sent = bt.run_backtest(prices, sentiment)
        assert without.total_trades == 0
        assert with_sent.total_trades == 0


# ===========================================================================
# WalkForwardAnalyzer tests
# ===========================================================================

class TestWalkForwardAnalyzer:

    def test_basic_run(self):
        prices = _synthetic_prices(500)
        analyzer = WalkForwardAnalyzer(in_sample_bars=100, out_sample_bars=30)
        report = analyzer.run(prices)
        assert isinstance(report, WalkForwardReport)
        assert len(report.windows) > 0

    def test_window_count(self):
        """Number of windows is roughly (n - IS) / OOS."""
        prices = _synthetic_prices(400)
        analyzer = WalkForwardAnalyzer(in_sample_bars=100, out_sample_bars=50)
        report = analyzer.run(prices)
        # (400 - 100) / 50 = 6
        assert len(report.windows) == 6

    def test_overfitting_detection(self):
        """Report has is_overfitting flag."""
        prices = _synthetic_prices(400)
        analyzer = WalkForwardAnalyzer(in_sample_bars=100, out_sample_bars=50)
        report = analyzer.run(prices)
        assert isinstance(report.is_overfitting, bool)

    def test_insufficient_data_raises(self):
        """Too few bars raises ValueError."""
        prices = _synthetic_prices(50)
        analyzer = WalkForwardAnalyzer(in_sample_bars=100, out_sample_bars=30)
        with pytest.raises(ValueError):
            analyzer.run(prices)

    def test_invalid_params_raise(self):
        with pytest.raises(ValueError):
            WalkForwardAnalyzer(in_sample_bars=0, out_sample_bars=10)

    def test_out_of_sample_metrics_present(self):
        prices = _synthetic_prices(400)
        analyzer = WalkForwardAnalyzer(in_sample_bars=100, out_sample_bars=50)
        report = analyzer.run(prices)
        assert isinstance(report.avg_out_sample_sharpe, float)
        assert isinstance(report.avg_out_sample_win_rate, float)
        assert 0.0 <= report.avg_out_sample_win_rate <= 1.0

    def test_window_index_sequential(self):
        prices = _synthetic_prices(400)
        analyzer = WalkForwardAnalyzer(in_sample_bars=100, out_sample_bars=50)
        report = analyzer.run(prices)
        indices = [w.window_index for w in report.windows]
        assert indices == list(range(len(report.windows)))

    def test_best_params_populated(self):
        prices = _synthetic_prices(400)
        analyzer = WalkForwardAnalyzer(in_sample_bars=100, out_sample_bars=50)
        report = analyzer.run(prices)
        for w in report.windows:
            assert isinstance(w.best_params, dict)
            assert len(w.best_params) > 0

    def test_custom_strategy_fn(self):
        """Custom strategy function is used in analysis."""
        def always_buy(prices, **params):
            return [0.001] * (len(prices) - 1)

        prices = _synthetic_prices(300)
        analyzer = WalkForwardAnalyzer(
            in_sample_bars=100,
            out_sample_bars=30,
            strategy_fn=always_buy,
        )
        report = analyzer.run(prices)
        assert len(report.windows) > 0


# ===========================================================================
# MonteCarloSimulator tests
# ===========================================================================

class TestMonteCarloSimulator:

    def test_basic_simulation(self):
        returns = _sample_trade_returns(100)
        sim = MonteCarloSimulator(seed=42)
        result = sim.run_simulation(returns, n_simulations=100)
        assert isinstance(result, SimulationResult)
        assert result.n_simulations == 100

    def test_equity_percentiles_populated(self):
        returns = _sample_trade_returns(100)
        sim = MonteCarloSimulator(seed=42)
        result = sim.run_simulation(returns, n_simulations=200)
        for pct in [5, 25, 50, 75, 95]:
            assert pct in result.equity_percentiles

    def test_percentile_ordering(self):
        """Lower percentile should have lower or equal equity."""
        returns = _sample_trade_returns(200)
        sim = MonteCarloSimulator(seed=42)
        result = sim.run_simulation(returns, n_simulations=500)
        p5 = result.equity_percentiles[5]
        p50 = result.equity_percentiles[50]
        p95 = result.equity_percentiles[95]
        assert p5 <= p50 <= p95

    def test_risk_of_ruin_range(self):
        returns = _sample_trade_returns(100)
        sim = MonteCarloSimulator(seed=42)
        sim.run_simulation(returns, n_simulations=200)
        ror = sim.get_risk_of_ruin(threshold=0.30)
        assert 0.0 <= ror <= 1.0

    def test_risk_of_ruin_before_run_raises(self):
        sim = MonteCarloSimulator()
        with pytest.raises(RuntimeError):
            sim.get_risk_of_ruin(0.20)

    def test_get_percentile_outcomes(self):
        returns = _sample_trade_returns(100)
        sim = MonteCarloSimulator(seed=42)
        sim.run_simulation(returns, n_simulations=200)
        outcomes = sim.get_percentile_outcomes([10, 50, 90])
        assert set(outcomes.keys()) == {10, 50, 90}

    def test_get_percentile_outcomes_before_run_raises(self):
        sim = MonteCarloSimulator()
        with pytest.raises(RuntimeError):
            sim.get_percentile_outcomes([50])

    def test_empty_trade_returns(self):
        sim = MonteCarloSimulator()
        result = sim.run_simulation([], n_simulations=100)
        assert result.n_simulations == 0
        assert result.final_equity_mean == 1.0

    def test_reproducible_with_seed(self):
        """Same seed produces same results."""
        returns = _sample_trade_returns(100)
        sim1 = MonteCarloSimulator(seed=99)
        result1 = sim1.run_simulation(returns, n_simulations=100)
        sim2 = MonteCarloSimulator(seed=99)
        result2 = sim2.run_simulation(returns, n_simulations=100)
        assert result1.final_equity_mean == result2.final_equity_mean

    def test_plot_skips_gracefully_no_matplotlib(self):
        """plot_results returns None when matplotlib is unavailable."""
        returns = _sample_trade_returns(50)
        sim = MonteCarloSimulator(seed=42)
        sim.run_simulation(returns, n_simulations=50)
        import bot.backtesting.monte_carlo as mc_mod
        original = mc_mod._MATPLOTLIB_AVAILABLE
        mc_mod._MATPLOTLIB_AVAILABLE = False
        with tempfile.TemporaryDirectory() as tmpdir:
            result = sim.plot_results(os.path.join(tmpdir, "plot.png"))
        mc_mod._MATPLOTLIB_AVAILABLE = original
        assert result is None

    def test_plot_before_run_raises(self):
        sim = MonteCarloSimulator()
        with pytest.raises(RuntimeError):
            with tempfile.TemporaryDirectory() as tmpdir:
                sim.plot_results(os.path.join(tmpdir, "plot.png"))

    def test_stat_fields_present(self):
        returns = _sample_trade_returns(100)
        sim = MonteCarloSimulator(seed=42)
        result = sim.run_simulation(returns, n_simulations=100)
        assert isinstance(result.sharpe_mean, float)
        assert isinstance(result.max_drawdown_mean, float)
        assert result.max_drawdown_mean >= 0.0
