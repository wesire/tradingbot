"""
Tests for broker adapter fetch_my_trades and fetch_positions methods,
and the updated API endpoints that use them.
"""
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# BrokerAdapter unit tests
# ---------------------------------------------------------------------------

class TestBrokerAdapterFetchMyTrades:
    """Tests for BrokerAdapter.fetch_my_trades()."""

    def _make_adapter(self):
        """Return a BrokerAdapter with a mocked CCXT exchange."""
        with patch("bot.execution.broker_adapter.ccxt") as mock_ccxt:
            mock_exchange = MagicMock()
            mock_exchange.load_markets.return_value = {}
            mock_ccxt.binance.return_value = mock_exchange

            from bot.execution.broker_adapter import BrokerAdapter
            adapter = BrokerAdapter(
                exchange_name="binance",
                api_key="test_key",
                api_secret="test_secret",
                sandbox=True,
            )
            # Keep reference to mock exchange
            adapter.exchange = mock_exchange
            return adapter, mock_exchange

    def test_fetch_my_trades_delegates_to_ccxt(self):
        """fetch_my_trades should call exchange.fetch_my_trades with correct args."""
        adapter, mock_exchange = self._make_adapter()
        fake_trades = [
            {"id": "1", "symbol": "BTC/USDT", "side": "buy", "amount": 0.01, "price": 50000.0, "datetime": "2024-01-01T00:00:00Z"},
        ]
        mock_exchange.fetch_my_trades.return_value = fake_trades

        result = adapter.fetch_my_trades(symbol="BTC/USDT", limit=10)

        mock_exchange.fetch_my_trades.assert_called_once_with("BTC/USDT", None, 10)
        assert result == fake_trades

    def test_fetch_my_trades_without_symbol(self):
        """fetch_my_trades should work without a symbol argument."""
        adapter, mock_exchange = self._make_adapter()
        mock_exchange.fetch_my_trades.return_value = []

        result = adapter.fetch_my_trades(limit=50)

        mock_exchange.fetch_my_trades.assert_called_once_with(None, None, 50)
        assert result == []

    def test_fetch_my_trades_raises_on_ccxt_error(self):
        """fetch_my_trades should propagate exchange errors."""
        import ccxt as ccxt_lib
        adapter, mock_exchange = self._make_adapter()
        mock_exchange.fetch_my_trades.side_effect = ccxt_lib.ExchangeError("permission denied")

        with pytest.raises(Exception, match="Exchange error"):
            adapter.fetch_my_trades()


class TestBrokerAdapterFetchPositions:
    """Tests for BrokerAdapter.fetch_positions()."""

    def _make_adapter(self):
        with patch("bot.execution.broker_adapter.ccxt") as mock_ccxt:
            mock_exchange = MagicMock()
            mock_exchange.load_markets.return_value = {}
            mock_ccxt.binance.return_value = mock_exchange

            from bot.execution.broker_adapter import BrokerAdapter
            adapter = BrokerAdapter(
                exchange_name="binance",
                api_key="test_key",
                api_secret="test_secret",
                sandbox=True,
            )
            adapter.exchange = mock_exchange
            return adapter, mock_exchange

    def test_fetch_positions_no_symbols(self):
        """fetch_positions without symbols calls exchange.fetch_positions()."""
        adapter, mock_exchange = self._make_adapter()
        fake_positions = [
            {
                "symbol": "BTC/USDT:USDT",
                "side": "long",
                "contracts": 0.01,
                "entryPrice": 50000.0,
                "markPrice": 51000.0,
                "unrealizedPnl": 10.0,
                "leverage": 5,
            }
        ]
        mock_exchange.fetch_positions.return_value = fake_positions

        result = adapter.fetch_positions()

        mock_exchange.fetch_positions.assert_called_once_with()
        assert result == fake_positions

    def test_fetch_positions_with_symbols(self):
        """fetch_positions with symbol list passes it to exchange."""
        adapter, mock_exchange = self._make_adapter()
        mock_exchange.fetch_positions.return_value = []

        result = adapter.fetch_positions(symbols=["BTC/USDT:USDT"])

        mock_exchange.fetch_positions.assert_called_once_with(["BTC/USDT:USDT"])
        assert result == []

    def test_fetch_positions_raises_on_error(self):
        """fetch_positions propagates exchange errors."""
        import ccxt as ccxt_lib
        adapter, mock_exchange = self._make_adapter()
        mock_exchange.fetch_positions.side_effect = ccxt_lib.NetworkError("timeout")

        with pytest.raises(Exception, match="Network error"):
            adapter.fetch_positions()


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    from tv_gateway.main import app
    return TestClient(app)


class TestTradesEndpoint:
    """Tests for GET /api/trades with and without exchange connection."""

    def test_trades_no_exchange_falls_back_to_alerts(self, client):
        """When no broker_adapter, /api/trades returns alert storage data."""
        import tv_gateway.main as main_module
        original = main_module.broker_adapter
        main_module.broker_adapter = None
        try:
            response = client.get("/api/trades?limit=5")
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert "trades" in data
            assert data["source"] == "alerts"
        finally:
            main_module.broker_adapter = original

    def test_trades_with_exchange_returns_exchange_data(self, client):
        """When broker_adapter is available, /api/trades returns exchange data."""
        import tv_gateway.main as main_module
        mock_adapter = MagicMock()
        mock_adapter.fetch_my_trades.return_value = [
            {
                "id": "123",
                "datetime": "2024-01-01T12:00:00Z",
                "symbol": "BTC/USDT",
                "side": "buy",
                "amount": 0.001,
                "price": 50000.0,
                "info": {"realizedPnl": "5.0"},
            }
        ]
        original = main_module.broker_adapter
        main_module.broker_adapter = mock_adapter
        try:
            response = client.get("/api/trades?limit=5")
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["source"] == "exchange"
            assert len(data["trades"]) == 1
            trade = data["trades"][0]
            assert trade["symbol"] == "BTC/USDT"
            assert trade["source"] == "exchange"
        finally:
            main_module.broker_adapter = original

    def test_trades_exchange_error_falls_back_to_alerts(self, client):
        """If exchange call fails, /api/trades falls back to alert storage."""
        import tv_gateway.main as main_module
        mock_adapter = MagicMock()
        mock_adapter.fetch_my_trades.side_effect = Exception("connection refused")
        original = main_module.broker_adapter
        main_module.broker_adapter = mock_adapter
        try:
            response = client.get("/api/trades?limit=5")
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["source"] == "alerts"
        finally:
            main_module.broker_adapter = original


class TestPositionsEndpoint:
    """Tests for GET /api/positions."""

    def test_positions_no_exchange_returns_empty(self, client):
        """Without exchange credentials, /api/positions returns empty list."""
        import tv_gateway.main as main_module
        original = main_module.broker_adapter
        main_module.broker_adapter = None
        try:
            response = client.get("/api/positions")
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["positions"] == []
            assert data["exchange_configured"] is False
        finally:
            main_module.broker_adapter = original

    def test_positions_with_exchange_returns_real_positions(self, client):
        """With exchange, /api/positions returns fetch_positions() data."""
        import tv_gateway.main as main_module
        mock_adapter = MagicMock()
        mock_adapter.fetch_positions.return_value = [
            {
                "symbol": "BTC/USDT:USDT",
                "side": "long",
                "contracts": 0.01,
                "entryPrice": 50000.0,
                "markPrice": 51000.0,
                "unrealizedPnl": 10.0,
                "leverage": 5,
            }
        ]
        original = main_module.broker_adapter
        main_module.broker_adapter = mock_adapter
        try:
            response = client.get("/api/positions")
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["source"] == "exchange"
            assert len(data["positions"]) == 1
            pos = data["positions"][0]
            assert pos["symbol"] == "BTC/USDT:USDT"
            assert pos["side"] == "long"
            assert pos["source"] == "exchange"
        finally:
            main_module.broker_adapter = original

    def test_positions_skips_zero_size_entries(self, client):
        """Positions with zero contracts and notional are filtered out."""
        import tv_gateway.main as main_module
        mock_adapter = MagicMock()
        mock_adapter.fetch_positions.return_value = [
            {"symbol": "BTC/USDT:USDT", "contracts": 0, "notional": 0},
            {"symbol": "ETH/USDT:USDT", "contracts": 0.1, "notional": 300.0, "entryPrice": 3000.0, "side": "long"},
        ]
        original = main_module.broker_adapter
        main_module.broker_adapter = mock_adapter
        try:
            response = client.get("/api/positions")
            assert response.status_code == 200
            data = response.json()
            positions = data["positions"]
            symbols = [p["symbol"] for p in positions]
            assert "BTC/USDT:USDT" not in symbols
            assert "ETH/USDT:USDT" in symbols
        finally:
            main_module.broker_adapter = original

    def test_positions_exchange_error_returns_empty(self, client):
        """Exchange fetch_positions failure returns empty positions gracefully."""
        import tv_gateway.main as main_module
        mock_adapter = MagicMock()
        mock_adapter.fetch_positions.side_effect = Exception("API error")
        original = main_module.broker_adapter
        main_module.broker_adapter = mock_adapter
        try:
            response = client.get("/api/positions")
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["positions"] == []
        finally:
            main_module.broker_adapter = original


class TestPnlHistoryEndpoint:
    """Tests for GET /api/pnl-history."""

    def test_pnl_history_no_exchange_uses_alerts(self, client):
        """Without exchange, /api/pnl-history falls back to alert storage."""
        import tv_gateway.main as main_module
        original = main_module.broker_adapter
        main_module.broker_adapter = None
        try:
            response = client.get("/api/pnl-history?period=24h")
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["source"] == "alerts"
            assert "data" in data
        finally:
            main_module.broker_adapter = original

    def test_pnl_history_with_exchange_uses_trade_fills(self, client):
        """With exchange, /api/pnl-history uses fetch_my_trades data."""
        import tv_gateway.main as main_module
        mock_adapter = MagicMock()
        mock_adapter.fetch_my_trades.return_value = [
            {
                "datetime": "2024-01-01T12:00:00Z",
                "info": {"realizedPnl": "50.0"},
            }
        ]
        original = main_module.broker_adapter
        main_module.broker_adapter = mock_adapter
        try:
            response = client.get("/api/pnl-history?period=24h")
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["source"] == "exchange"
        finally:
            main_module.broker_adapter = original

    def test_pnl_history_exchange_error_falls_back(self, client):
        """Exchange failure falls back to alert storage for PnL history."""
        import tv_gateway.main as main_module
        mock_adapter = MagicMock()
        mock_adapter.fetch_my_trades.side_effect = Exception("timeout")
        original = main_module.broker_adapter
        main_module.broker_adapter = mock_adapter
        try:
            response = client.get("/api/pnl-history?period=24h")
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["source"] == "alerts"
        finally:
            main_module.broker_adapter = original


class TestHealthEndpointExchangeStatus:
    """Tests for exchange_connected field in /health response."""

    def test_health_includes_exchange_connected_false(self, client):
        """Health endpoint reports exchange_connected=False when no adapter."""
        import tv_gateway.main as main_module
        original = main_module.broker_adapter
        main_module.broker_adapter = None
        try:
            response = client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert data["exchange_connected"] is False
        finally:
            main_module.broker_adapter = original

    def test_health_includes_exchange_connected_true(self, client):
        """Health endpoint reports exchange_connected=True when adapter is set."""
        import tv_gateway.main as main_module
        mock_adapter = MagicMock()
        original = main_module.broker_adapter
        main_module.broker_adapter = mock_adapter
        try:
            response = client.get("/health")
            assert response.status_code in (200, 503)
            data = response.json()
            assert data["exchange_connected"] is True
        finally:
            main_module.broker_adapter = original
