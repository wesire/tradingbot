"""
Pytest configuration and shared fixtures.
"""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock


@pytest.fixture
def sample_ohlcv_data():
    """Generate sample OHLCV data for testing."""
    dates = pd.date_range(start='2024-01-01', periods=200, freq='5min')
    
    # Generate realistic price data
    np.random.seed(42)
    close_prices = 40000 + np.cumsum(np.random.randn(200) * 100)
    
    df = pd.DataFrame({
        'timestamp': dates,
        'open': close_prices + np.random.randn(200) * 50,
        'high': close_prices + np.abs(np.random.randn(200) * 100),
        'low': close_prices - np.abs(np.random.randn(200) * 100),
        'close': close_prices,
        'volume': np.random.uniform(1000, 5000, 200)
    })
    
    df.set_index('timestamp', inplace=True)
    return df


@pytest.fixture
def sample_ohlcv_dataframe():
    """Generate sample OHLCV DataFrame in Freqtrade format."""
    dates = pd.date_range(start='2024-01-01', periods=200, freq='5min')
    
    np.random.seed(42)
    close_prices = 40000 + np.cumsum(np.random.randn(200) * 100)
    
    df = pd.DataFrame({
        'date': dates,
        'open': close_prices + np.random.randn(200) * 50,
        'high': close_prices + np.abs(np.random.randn(200) * 100),
        'low': close_prices - np.abs(np.random.randn(200) * 100),
        'close': close_prices,
        'volume': np.random.uniform(1000, 5000, 200)
    })
    
    return df


@pytest.fixture
def mock_exchange():
    """Create a mock CCXT exchange."""
    exchange = Mock()
    exchange.name = "binance"
    exchange.load_markets = Mock()
    exchange.fetch_ticker = Mock(return_value={
        'symbol': 'BTC/USDT',
        'last': 40000.0,
        'bid': 39995.0,
        'ask': 40005.0,
        'volume': 10000
    })
    exchange.fetch_balance = Mock(return_value={
        'total': {'USDT': 10000.0},
        'free': {'USDT': 10000.0},
        'used': {'USDT': 0.0}
    })
    exchange.create_order = Mock(return_value={
        'id': '12345',
        'status': 'open',
        'symbol': 'BTC/USDT',
        'type': 'limit',
        'side': 'buy',
        'price': 40000.0,
        'amount': 0.1,
        'filled': 0.0
    })
    exchange.fetch_order = Mock(return_value={
        'id': '12345',
        'status': 'closed',
        'filled': 0.1,
        'average': 40000.0
    })
    exchange.cancel_order = Mock(return_value={'status': 'cancelled'})
    exchange.set_leverage = Mock(return_value={'leverage': 3})
    
    return exchange


@pytest.fixture
def sample_trade():
    """Create a sample trade object."""
    trade = Mock()
    trade.pair = 'BTC/USDT:USDT'
    trade.is_short = False
    trade.open_rate = 40000.0
    trade.stake_amount = 1000.0
    trade.amount = 0.025
    trade.open_date = datetime.now()
    
    return trade


@pytest.fixture
def sample_backtest_results():
    """Generate sample backtest results."""
    return {
        'timeframe': '5m',
        'total_trades': 150,
        'win_rate': 0.56,
        'profit_factor': 1.35,
        'expectancy': 0.008,
        'sharpe_ratio': 1.2,
        'max_drawdown_pct': 8.5,
        'total_profit_pct': 12.5,
        'annual_return_pct': 25.0
    }


@pytest.fixture
def mock_broker_adapter(mock_exchange):
    """Create a mock broker adapter."""
    from bot.execution.broker_adapter import BrokerAdapter
    
    adapter = Mock(spec=BrokerAdapter)
    adapter.exchange = mock_exchange
    adapter.health_check = Mock(return_value=True)
    adapter.fetch_ticker = mock_exchange.fetch_ticker
    adapter.fetch_balance = mock_exchange.fetch_balance
    adapter.create_order = mock_exchange.create_order
    adapter.fetch_order = mock_exchange.fetch_order
    adapter.cancel_order = mock_exchange.cancel_order
    adapter.set_leverage = mock_exchange.set_leverage
    
    return adapter


@pytest.fixture
def sample_webhook_payload():
    """Create a sample webhook payload."""
    return {
        'symbol': 'BTCUSDT',
        'timeframe': '5m',
        'side': 'long',
        'setup_id': 'ema_rsi_regime',
        'confidence': 0.85,
        'price': 40000.0,
        'event_time': str(datetime.now().timestamp() * 1000),
        'secret': 'test_secret_123',
        'timestamp': int(datetime.now().timestamp()),
        'nonce': f'test_nonce_{datetime.now().timestamp()}'
    }


@pytest.fixture(autouse=True)
def reset_config():
    """Reset configuration before each test."""
    # This ensures tests don't affect each other
    yield
    # Cleanup if needed


@pytest.fixture
def temp_data_dir(tmp_path):
    """Create a temporary data directory."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    return data_dir


@pytest.fixture
def temp_artifacts_dir(tmp_path):
    """Create a temporary artifacts directory."""
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir()
    return artifacts_dir
