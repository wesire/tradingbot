"""
Unit tests for SmartOrderRouter and ExecutionAnalytics.
"""
import time
from unittest.mock import MagicMock, call

import pytest

from bot.execution.smart_orders import SmartOrderRouter, ExecutionAnalytics


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_exchange():
    """Return a mock CCXT-like exchange."""
    ex = MagicMock()
    ex.create_limit_order.return_value = {
        "id": "order_123",
        "type": "limit",
        "status": "closed",
        "price": 40000.0,
        "average": 40000.0,
        "fee": {"cost": 0.01},
    }
    ex.create_market_order.return_value = {
        "id": "order_456",
        "type": "market",
        "status": "closed",
        "price": 40010.0,
        "average": 40010.0,
        "fee": {"cost": 0.02},
    }
    ex.fetch_order.return_value = {
        "id": "order_123",
        "status": "closed",
        "average": 40000.0,
        "fee": {"cost": 0.01},
    }
    return ex


# ---------------------------------------------------------------------------
# SmartOrderRouter
# ---------------------------------------------------------------------------

class TestSmartOrderRouter:
    def test_place_limit_order_success(self):
        exchange = _mock_exchange()
        router = SmartOrderRouter(exchange, limit_timeout=0)
        order = router.place_limit_order("BTC/USDT", "buy", 0.001, 40000.0)
        exchange.create_limit_order.assert_called_once_with(
            "BTC/USDT", "buy", 0.001, 40000.0, {}
        )
        assert order["id"] == "order_123"

    def test_place_limit_order_fallback_on_exchange_error(self):
        exchange = _mock_exchange()
        exchange.create_limit_order.side_effect = Exception("exchange error")
        router = SmartOrderRouter(exchange, limit_timeout=0)
        order = router.place_limit_order("BTC/USDT", "buy", 0.001, 40000.0)
        # Should fall back to market order
        exchange.create_market_order.assert_called_once()
        assert order["id"] == "order_456"

    def test_place_limit_order_records_analytics(self):
        exchange = _mock_exchange()
        router = SmartOrderRouter(exchange, limit_timeout=0)
        router.place_limit_order("BTC/USDT", "buy", 0.001, 40000.0)
        assert len(router.analytics._executions) == 1

    def test_place_scaled_entry(self):
        exchange = _mock_exchange()
        router = SmartOrderRouter(exchange, limit_timeout=0)
        orders = router.place_scaled_entry(
            "BTC/USDT", "buy", 0.01, (39900.0, 40100.0), num_orders=4
        )
        assert len(orders) == 4
        assert exchange.create_limit_order.call_count == 4

    def test_place_scaled_entry_single_slice(self):
        exchange = _mock_exchange()
        router = SmartOrderRouter(exchange, limit_timeout=0)
        orders = router.place_scaled_entry(
            "ETH/USDT", "sell", 1.0, (3000.0, 3100.0), num_orders=1
        )
        assert len(orders) == 1

    def test_place_twap_order(self):
        exchange = _mock_exchange()
        router = SmartOrderRouter(exchange, limit_timeout=0)
        orders = router.place_twap_order(
            "BTC/USDT", "buy", 0.01, duration_seconds=0, num_slices=3
        )
        assert len(orders) == 3
        assert exchange.create_market_order.call_count == 3

    def test_analytics_property(self):
        exchange = _mock_exchange()
        router = SmartOrderRouter(exchange)
        assert isinstance(router.analytics, ExecutionAnalytics)


# ---------------------------------------------------------------------------
# ExecutionAnalytics
# ---------------------------------------------------------------------------

class TestExecutionAnalytics:
    def test_record_and_slippage(self):
        analytics = ExecutionAnalytics()
        analytics.record_execution(
            pair="BTC/USDT",
            expected_price=40000.0,
            fill_price=40040.0,
            fill_time_seconds=0.5,
            fees=0.01,
            order_type="limit",
        )
        slippage = analytics.get_average_slippage("BTC/USDT")
        assert slippage == pytest.approx(0.001)  # 0.1%

    def test_slippage_empty(self):
        analytics = ExecutionAnalytics()
        assert analytics.get_average_slippage() == 0.0

    def test_slippage_per_pair(self):
        analytics = ExecutionAnalytics()
        analytics.record_execution("BTC/USDT", 40000.0, 40100.0, 1.0)
        analytics.record_execution("ETH/USDT", 3000.0, 3030.0, 0.5)
        btc_slip = analytics.get_average_slippage("BTC/USDT")
        eth_slip = analytics.get_average_slippage("ETH/USDT")
        assert btc_slip == pytest.approx(0.0025)
        assert eth_slip == pytest.approx(0.01)

    def test_execution_report_summary(self):
        analytics = ExecutionAnalytics()
        for i in range(5):
            analytics.record_execution("BTC/USDT", 40000.0, 40000.0 + i, 0.1 * i, fees=0.01)
        report = analytics.get_execution_report(period="all")
        assert report["total_executions"] == 5
        assert "avg_slippage" in report
        assert "total_fees" in report

    def test_execution_report_empty(self):
        analytics = ExecutionAnalytics()
        report = analytics.get_execution_report(period="all")
        assert report["total_executions"] == 0
        assert report["avg_slippage"] == 0.0

    def test_maker_ratio(self):
        analytics = ExecutionAnalytics()
        analytics.record_execution("BTC/USDT", 40000.0, 40000.0, 1.0, order_type="limit")
        analytics.record_execution("BTC/USDT", 40000.0, 40000.0, 0.1, order_type="market")
        report = analytics.get_execution_report(period="all")
        assert report["maker_ratio"] == pytest.approx(0.5)
