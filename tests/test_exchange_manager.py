"""
Unit tests for ExchangeManager.
"""
from unittest.mock import MagicMock, patch

import pytest

from bot.execution.exchange_manager import ExchangeManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_ccxt_exchange():
    """Return a mock CCXT exchange instance."""
    ex = MagicMock()
    ex.fetch_balance.return_value = {
        "free": {"USDT": 1000.0, "BTC": 0.1},
        "total": {"USDT": 1000.0, "BTC": 0.1},
    }
    return ex


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestExchangeManager:
    def _register_mock(self, mgr: ExchangeManager, name: str = "binance"):
        """Register a mock exchange bypassing CCXT."""
        mock_ex = _mock_ccxt_exchange()
        mgr._exchanges[name] = mock_ex
        mgr._configs[name] = {}
        return mock_ex

    def test_get_exchange_after_manual_register(self):
        mgr = ExchangeManager()
        self._register_mock(mgr, "binance")
        exchange = mgr.get_exchange("binance")
        assert exchange is not None

    def test_get_exchange_not_registered_raises(self):
        mgr = ExchangeManager()
        with pytest.raises(KeyError, match="binance"):
            mgr.get_exchange("binance")

    def test_list_exchanges(self):
        mgr = ExchangeManager()
        self._register_mock(mgr, "binance")
        self._register_mock(mgr, "bybit")
        names = mgr.list_exchanges()
        assert "binance" in names
        assert "bybit" in names
        assert len(names) == 2

    def test_get_best_exchange_returns_lowest_fee(self):
        mgr = ExchangeManager()
        self._register_mock(mgr, "binance")  # fee 0.0004
        self._register_mock(mgr, "bybit")    # fee 0.0006
        best = mgr.get_best_exchange_for_pair("BTC/USDT")
        assert best == "binance"

    def test_get_best_exchange_no_exchanges(self):
        mgr = ExchangeManager()
        assert mgr.get_best_exchange_for_pair("BTC/USDT") is None

    def test_get_all_balances(self):
        mgr = ExchangeManager()
        self._register_mock(mgr, "binance")
        balances = mgr.get_all_balances()
        assert "binance" in balances
        assert balances["binance"]["free"]["USDT"] == 1000.0

    def test_get_all_balances_handles_error(self):
        mgr = ExchangeManager()
        mock_ex = _mock_ccxt_exchange()
        mock_ex.fetch_balance.side_effect = Exception("network error")
        mgr._exchanges["binance"] = mock_ex
        balances = mgr.get_all_balances()
        assert "error" in balances["binance"]

    def test_get_total_balance(self):
        mgr = ExchangeManager()
        self._register_mock(mgr, "binance")
        total = mgr.get_total_balance("USDT")
        assert total == pytest.approx(1000.0)

    def test_get_total_balance_multiple_exchanges(self):
        mgr = ExchangeManager()
        self._register_mock(mgr, "binance")  # 1000 USDT
        self._register_mock(mgr, "bybit")    # 1000 USDT
        total = mgr.get_total_balance("USDT")
        assert total == pytest.approx(2000.0)

    def test_register_from_config_skips_disabled(self):
        mgr = ExchangeManager()
        config = [
            {"name": "binance", "enabled": False},
            {"name": "bybit", "enabled": False},
        ]
        # Should register 0 (CCXT may not be available in test env)
        # We just verify it doesn't crash and disabled ones are skipped
        registered = mgr.register_from_config(config)
        assert registered == 0  # All disabled

    def test_register_exchange_without_ccxt(self):
        """register_exchange should return False gracefully if CCXT not available."""
        mgr = ExchangeManager()
        with patch("bot.execution.exchange_manager._CCXT_AVAILABLE", False):
            result = mgr.register_exchange("binance")
        assert result is False
