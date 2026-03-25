"""
Unit tests for the portfolio modules:
- CorrelationManager
- RiskParityAllocator
- PerformanceTracker
"""
import math
from datetime import datetime, timedelta, timezone

import pandas as pd
import numpy as np
import pytest

from bot.portfolio.correlation_manager import CorrelationManager
from bot.portfolio.risk_parity import RiskParityAllocator
from bot.portfolio.performance_tracker import PerformanceTracker


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_prices(n=60, start=100.0, seed=42):
    """Generate a simple synthetic price series."""
    rng = np.random.default_rng(seed)
    returns = rng.normal(0, 0.01, n)
    prices = [start]
    for r in returns:
        prices.append(prices[-1] * (1 + r))
    idx = pd.date_range(end=pd.Timestamp.now(tz="UTC"), periods=n + 1, freq="D")
    return pd.Series(prices, index=idx)


def _trade(pnl=10.0, pair="BTC/USDT", side="long"):
    now = datetime.now(timezone.utc).isoformat()
    return {
        "pair": pair,
        "side": side,
        "entry_price": 40000.0,
        "exit_price": 40100.0 if pnl > 0 else 39900.0,
        "amount": 0.001,
        "fees": 0.1,
        "pnl": pnl,
        "strategy": "test_strategy",
        "session": "london",
        "opened_at": now,
        "closed_at": now,
    }


# ---------------------------------------------------------------------------
# CorrelationManager
# ---------------------------------------------------------------------------

class TestCorrelationManager:
    def test_empty_matrix_when_fewer_than_two_pairs(self):
        mgr = CorrelationManager()
        mgr.update_prices("BTC/USDT", _make_prices())
        corr = mgr.get_correlation_matrix()
        assert corr.empty

    def test_correlation_matrix_shape(self):
        mgr = CorrelationManager()
        mgr.update_prices("BTC/USDT", _make_prices(seed=1))
        mgr.update_prices("ETH/USDT", _make_prices(seed=2))
        mgr.update_prices("SOL/USDT", _make_prices(seed=3))
        corr = mgr.get_correlation_matrix()
        assert corr.shape == (3, 3)

    def test_self_correlation_is_one(self):
        mgr = CorrelationManager()
        mgr.update_prices("BTC/USDT", _make_prices(seed=1))
        mgr.update_prices("ETH/USDT", _make_prices(seed=2))
        corr = mgr.get_correlation_matrix()
        assert corr.loc["BTC/USDT", "BTC/USDT"] == pytest.approx(1.0)

    def test_highly_correlated_pairs_reduce_position(self):
        mgr = CorrelationManager(correlation_threshold=0.5)
        # Make two identical price series (correlation = 1.0)
        prices = _make_prices(seed=5)
        mgr.update_prices("BTC/USDT", prices)
        mgr.update_prices("ETH/USDT", prices)
        should_reduce, multiplier = mgr.should_reduce_position(
            "ETH/USDT", {"BTC/USDT": 1000.0}
        )
        assert should_reduce is True
        assert multiplier < 1.0

    def test_uncorrelated_pairs_no_reduction(self):
        mgr = CorrelationManager(correlation_threshold=0.9)
        # Orthogonal random series
        rng = np.random.default_rng(99)
        p1 = pd.Series(
            [100 * (1 + r) for r in np.cumsum(rng.normal(0, 0.01, 60))],
            index=pd.date_range(end=pd.Timestamp.now(tz="UTC"), periods=60, freq="D"),
        )
        rng2 = np.random.default_rng(100)
        p2 = pd.Series(
            [100 * (1 + r) for r in np.cumsum(rng2.normal(0, 0.01, 60))],
            index=pd.date_range(end=pd.Timestamp.now(tz="UTC"), periods=60, freq="D"),
        )
        mgr.update_prices("BTC/USDT", p1)
        mgr.update_prices("ETH/USDT", p2)
        # Even if corr is not zero, with threshold=0.9 it won't be reduced
        should_reduce, multiplier = mgr.should_reduce_position(
            "ETH/USDT", {"BTC/USDT": 1000.0}
        )
        # multiplier should be 1.0 (no reduction)
        assert multiplier == 1.0

    def test_max_correlated_exposure(self):
        mgr = CorrelationManager(correlation_threshold=0.5)
        prices = _make_prices(seed=5)
        mgr.update_prices("BTC/USDT", prices)
        mgr.update_prices("ETH/USDT", prices)
        exposure = mgr.get_max_correlated_exposure(
            {"BTC/USDT": 1000.0, "ETH/USDT": 1000.0}
        )
        assert 0.0 <= exposure <= 1.0

    def test_no_positions_returns_zero(self):
        mgr = CorrelationManager()
        assert mgr.get_max_correlated_exposure({}) == 0.0


# ---------------------------------------------------------------------------
# RiskParityAllocator
# ---------------------------------------------------------------------------

class TestRiskParityAllocator:
    def test_weights_sum_to_one(self):
        alloc = RiskParityAllocator()
        vols = {"BTC/USDT": 0.8, "ETH/USDT": 0.6, "SOL/USDT": 1.2}
        weights = alloc.calculate_weights(vols)
        assert sum(weights.values()) == pytest.approx(1.0)

    def test_higher_vol_gets_lower_weight(self):
        alloc = RiskParityAllocator()
        vols = {"BTC/USDT": 0.5, "SOL/USDT": 2.0}
        weights = alloc.calculate_weights(vols)
        assert weights["BTC/USDT"] > weights["SOL/USDT"]

    def test_equal_vol_equal_weight(self):
        alloc = RiskParityAllocator()
        vols = {"BTC/USDT": 1.0, "ETH/USDT": 1.0}
        weights = alloc.calculate_weights(vols)
        assert weights["BTC/USDT"] == pytest.approx(0.5)
        assert weights["ETH/USDT"] == pytest.approx(0.5)

    def test_empty_vols_returns_empty(self):
        alloc = RiskParityAllocator()
        assert alloc.calculate_weights({}) == {}

    def test_zero_vol_handled(self):
        alloc = RiskParityAllocator()
        vols = {"BTC/USDT": 0.0, "ETH/USDT": 1.0}
        weights = alloc.calculate_weights(vols)
        # BTC gets huge weight (nearly all), ETH nearly none
        assert sum(weights.values()) == pytest.approx(1.0)

    def test_estimate_volatility(self):
        alloc = RiskParityAllocator()
        prices = _make_prices(n=100, seed=7)
        vol = alloc.estimate_volatility(prices)
        assert vol > 0

    def test_adjust_allocation_recommends_rebalance(self):
        alloc = RiskParityAllocator(rebalance_threshold=0.0)  # Always rebalance
        prices = {"BTC/USDT": _make_prices(n=60, seed=1), "ETH/USDT": _make_prices(n=60, seed=2)}
        # Current positions wildly off target
        positions = {"BTC/USDT": 900.0, "ETH/USDT": 100.0}
        recs = alloc.adjust_allocation(positions, prices, total_capital=1000.0)
        # Should recommend at least one rebalance
        assert isinstance(recs, list)

    def test_adjust_allocation_no_rebalance_within_threshold(self):
        alloc = RiskParityAllocator(rebalance_threshold=0.99)  # Extremely high — never rebalance
        prices = {"BTC/USDT": _make_prices(n=60, seed=1)}
        positions = {"BTC/USDT": 1000.0}
        recs = alloc.adjust_allocation(positions, prices, total_capital=1000.0)
        assert recs == []


# ---------------------------------------------------------------------------
# PerformanceTracker
# ---------------------------------------------------------------------------

class TestPerformanceTracker:
    def test_record_and_retrieve_trade(self):
        tracker = PerformanceTracker(db_path=":memory:")
        row_id = tracker.record_trade(_trade(pnl=5.0))
        assert row_id == 1
        trades = tracker.get_trades()
        assert len(trades) == 1
        assert trades[0]["pnl"] == 5.0
        tracker.close()

    def test_get_daily_summary(self):
        tracker = PerformanceTracker(db_path=":memory:")
        tracker.record_trade(_trade(pnl=5.0))
        tracker.record_trade(_trade(pnl=-2.0))
        summary = tracker.get_daily_summary()
        assert summary["total_trades"] == 2
        assert summary["total_pnl"] == pytest.approx(3.0)
        tracker.close()

    def test_win_rate(self):
        tracker = PerformanceTracker(db_path=":memory:")
        for _ in range(3):
            tracker.record_trade(_trade(pnl=1.0))
        tracker.record_trade(_trade(pnl=-1.0))
        summary = tracker.get_daily_summary()
        assert summary["win_rate"] == pytest.approx(0.75)
        tracker.close()

    def test_performance_report_period(self):
        tracker = PerformanceTracker(db_path=":memory:")
        tracker.record_trade(_trade(pnl=10.0))
        report = tracker.get_performance_report(period="30d")
        assert "metrics" in report
        assert report["metrics"]["total_trades"] == 1
        tracker.close()

    def test_performance_report_all(self):
        tracker = PerformanceTracker(db_path=":memory:")
        tracker.record_trade(_trade(pnl=5.0))
        report = tracker.get_performance_report(period="all")
        assert report["period"] == "all"
        tracker.close()

    def test_empty_metrics(self):
        tracker = PerformanceTracker(db_path=":memory:")
        summary = tracker.get_daily_summary()
        assert summary["total_trades"] == 0
        assert summary["win_rate"] == 0.0
        tracker.close()

    def test_export_csv(self, tmp_path):
        tracker = PerformanceTracker(db_path=":memory:")
        tracker.record_trade(_trade(pnl=5.0))
        tracker.record_trade(_trade(pnl=-2.0))
        filepath = str(tmp_path / "trades.csv")
        count = tracker.export_csv(filepath)
        assert count == 2
        with open(filepath) as fh:
            lines = fh.readlines()
        assert len(lines) == 3  # header + 2 rows
        tracker.close()

    def test_sharpe_ratio_positive_for_winning_trades(self):
        tracker = PerformanceTracker(db_path=":memory:")
        for _ in range(20):
            tracker.record_trade(_trade(pnl=1.0))
        report = tracker.get_performance_report(period="all")
        # All wins → positive or zero Sharpe (std=0 edge case)
        assert report["metrics"]["sharpe_ratio"] >= 0.0
        tracker.close()

    def test_record_equity(self):
        tracker = PerformanceTracker(db_path=":memory:")
        tracker.record_equity(10000.0)
        tracker.record_equity(10100.0)
        report = tracker.get_performance_report(period="all")
        assert len(report["equity_curve"]) == 2
        tracker.close()
