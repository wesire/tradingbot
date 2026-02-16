"""
Basic tests for strategy module.
"""
import pytest
import pandas as pd
import numpy as np

from bot.strategy.signal_filters import SignalFilters
from bot.strategy.risk_engine import RiskEngine


def test_strategy_imports():
    """Test that strategy modules can be imported."""
    try:
        from bot.strategy.btc_scalp_strategy import BTCScalpStrategy
        assert BTCScalpStrategy is not None
    except ImportError as e:
        pytest.skip(f"Strategy import requires Freqtrade: {e}")


def test_signal_filters_integration(sample_ohlcv_dataframe):
    """Test signal filters work together."""
    filters = SignalFilters()
    
    # Apply all filters
    result = filters.apply_all_filters(
        sample_ohlcv_dataframe,
        enable_mean_reversion=True
    )
    
    # Should have all expected columns
    expected_cols = [
        'volatility_ok', 'volume_spike', 'filters_passed',
        'mr_long', 'mr_short'
    ]
    
    for col in expected_cols:
        assert col in result.columns


def test_risk_engine_integration():
    """Test risk engine workflow."""
    engine = RiskEngine()
    
    equity = 10000.0
    entry_price = 40000.0
    atr = 200.0
    
    # Calculate stop loss
    stop_loss = engine.calculate_stop_loss(
        entry_price=entry_price,
        atr=atr,
        side='long'
    )
    
    # Calculate position size
    position_size = engine.calculate_position_size(
        equity=equity,
        entry_price=entry_price,
        stop_loss_price=stop_loss,
        side='long'
    )
    
    # Calculate take profits
    tp_levels = engine.calculate_take_profit_levels(
        entry_price=entry_price,
        stop_loss_price=stop_loss,
        side='long'
    )
    
    # Verify workflow produces valid values
    assert stop_loss < entry_price
    assert position_size > 0
    assert len(tp_levels) > 0
    assert all(tp > entry_price for tp in tp_levels.values())


def test_strategy_configuration():
    """Test strategy configuration parameters."""
    from bot.config.default_config import config
    
    # Verify key strategy parameters are set
    assert config.REGIME_EMA_FAST > 0
    assert config.REGIME_EMA_SLOW > config.REGIME_EMA_FAST
    assert config.ENTRY_RSI_PERIOD > 0
    assert config.FILTER_ATR_PERIOD > 0


def test_strategy_timeframes():
    """Test configured timeframes."""
    from bot.config.default_config import config
    
    assert '5m' in config.TIMEFRAMES
    assert len(config.TIMEFRAMES) > 0
    assert config.PRIMARY_TIMEFRAME in config.TIMEFRAMES


def test_regime_detection_logic(sample_ohlcv_dataframe):
    """Test regime detection with sample data."""
    df = sample_ohlcv_dataframe.copy()
    
    # Calculate EMAs for regime
    df['ema_fast'] = df['close'].ewm(span=50).mean()
    df['ema_slow'] = df['close'].ewm(span=200).mean()
    
    # Mock ADX
    df['adx'] = 30
    
    # Determine regimes
    df['regime_bullish'] = (df['ema_fast'] > df['ema_slow']) & (df['adx'] > 25)
    df['regime_bearish'] = (df['ema_fast'] < df['ema_slow']) & (df['adx'] > 25)
    df['regime_neutral'] = ~(df['regime_bullish'] | df['regime_bearish'])
    
    # Should have at least one regime active for each row
    assert all(
        df['regime_bullish'] | df['regime_bearish'] | df['regime_neutral']
    )


def test_entry_signal_components(sample_ohlcv_dataframe):
    """Test components of entry signal generation."""
    df = sample_ohlcv_dataframe.copy()
    
    # EMA
    df['ema'] = df['close'].ewm(span=21).mean()
    
    # RSI
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(window=14).mean()
    loss = -delta.where(delta < 0, 0).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    # Volume
    df['volume_ma'] = df['volume'].rolling(window=20).mean()
    
    # All components should be calculated
    assert 'ema' in df.columns
    assert 'rsi' in df.columns
    assert 'volume_ma' in df.columns
    
    # Values should be reasonable
    assert df['rsi'].iloc[-1] >= 0
    assert df['rsi'].iloc[-1] <= 100
