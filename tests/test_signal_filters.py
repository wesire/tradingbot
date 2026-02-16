"""
Tests for signal filters module.
"""
import pytest
import pandas as pd
import numpy as np

from bot.strategy.signal_filters import SignalFilters


def test_signal_filters_initialization():
    """Test SignalFilters initialization with default parameters."""
    filters = SignalFilters()
    
    assert filters.atr_period == 14
    assert filters.atr_min_threshold == 0.0005
    assert filters.volume_period == 20
    assert filters.volume_multiplier == 1.5


def test_signal_filters_custom_parameters():
    """Test SignalFilters initialization with custom parameters."""
    filters = SignalFilters(
        atr_period=20,
        atr_min_threshold=0.001,
        volume_period=30,
        volume_multiplier=2.0
    )
    
    assert filters.atr_period == 20
    assert filters.atr_min_threshold == 0.001
    assert filters.volume_period == 30
    assert filters.volume_multiplier == 2.0


def test_calculate_atr(sample_ohlcv_dataframe):
    """Test ATR calculation."""
    filters = SignalFilters()
    df = filters.calculate_atr(sample_ohlcv_dataframe)
    
    assert 'atr' in df.columns
    assert not df['atr'].iloc[-1] != df['atr'].iloc[-1]  # Check for NaN
    assert df['atr'].iloc[-1] > 0


def test_volatility_filter(sample_ohlcv_dataframe):
    """Test volatility filter logic."""
    filters = SignalFilters(atr_min_threshold=0.001)
    df = filters.volatility_filter(sample_ohlcv_dataframe)
    
    assert 'volatility_ok' in df.columns
    assert 'atr_pct' in df.columns
    assert df['volatility_ok'].dtype == bool


def test_calculate_relative_volume(sample_ohlcv_dataframe):
    """Test relative volume calculation."""
    filters = SignalFilters()
    df = filters.calculate_relative_volume(sample_ohlcv_dataframe)
    
    assert 'volume_ma' in df.columns
    assert 'volume_ratio' in df.columns
    assert not df['volume_ratio'].iloc[-1] != df['volume_ratio'].iloc[-1]  # Not NaN


def test_volume_filter(sample_ohlcv_dataframe):
    """Test volume spike detection."""
    filters = SignalFilters(volume_multiplier=1.5)
    df = filters.volume_filter(sample_ohlcv_dataframe)
    
    assert 'volume_spike' in df.columns
    assert df['volume_spike'].dtype == bool


def test_mean_reversion_signal(sample_ohlcv_dataframe):
    """Test mean reversion signal generation."""
    filters = SignalFilters()
    df = filters.mean_reversion_signal(sample_ohlcv_dataframe)
    
    assert 'bb_upper' in df.columns
    assert 'bb_lower' in df.columns
    assert 'bb_middle' in df.columns
    assert 'rsi_mr' in df.columns
    assert 'mr_long' in df.columns
    assert 'mr_short' in df.columns
    
    assert df['mr_long'].dtype == bool
    assert df['mr_short'].dtype == bool


def test_apply_all_filters(sample_ohlcv_dataframe):
    """Test applying all filters together."""
    filters = SignalFilters()
    df = filters.apply_all_filters(sample_ohlcv_dataframe, enable_mean_reversion=True)
    
    assert 'volatility_ok' in df.columns
    assert 'volume_spike' in df.columns
    assert 'filters_passed' in df.columns
    assert 'mr_long' in df.columns
    assert 'mr_short' in df.columns


def test_filters_passed_logic(sample_ohlcv_dataframe):
    """Test that filters_passed combines conditions correctly."""
    filters = SignalFilters()
    df = filters.apply_all_filters(sample_ohlcv_dataframe)
    
    # filters_passed should be AND of volatility_ok and volume_spike
    for idx in df.index[-10:]:  # Check last 10 rows
        expected = df.loc[idx, 'volatility_ok'] and df.loc[idx, 'volume_spike']
        assert df.loc[idx, 'filters_passed'] == expected


def test_atr_with_missing_data():
    """Test ATR calculation handles missing data."""
    df = pd.DataFrame({
        'open': [100, 101, np.nan, 103],
        'high': [102, 103, 104, 105],
        'low': [99, 100, 101, 102],
        'close': [101, 102, 103, 104],
        'volume': [1000, 1100, 1200, 1300]
    })
    
    filters = SignalFilters()
    result = filters.calculate_atr(df)
    
    assert 'atr' in result.columns
    # ATR should handle NaN gracefully


def test_volume_filter_with_low_volume(sample_ohlcv_dataframe):
    """Test volume filter with consistently low volume."""
    df = sample_ohlcv_dataframe.copy()
    df['volume'] = 100  # Set all volume to same low value
    
    filters = SignalFilters(volume_multiplier=1.5)
    result = filters.volume_filter(df)
    
    # Should have volume_spike column even with low volume
    assert 'volume_spike' in result.columns
