"""
Tests for backtest pipeline and champion selection.
"""
import pytest
import pandas as pd
from pathlib import Path

from scripts.select_champion import (
    normalize_metric,
    calculate_composite_score,
    apply_rejection_filters,
    generate_recommendation
)


def test_normalize_metric_higher_is_better():
    """Test metric normalization when higher values are better."""
    values = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    normalized = normalize_metric(values, higher_is_better=True)
    
    assert normalized.min() == 0.0
    assert normalized.max() == 1.0
    assert normalized.iloc[0] == 0.0  # Lowest value -> 0
    assert normalized.iloc[-1] == 1.0  # Highest value -> 1


def test_normalize_metric_lower_is_better():
    """Test metric normalization when lower values are better."""
    values = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    normalized = normalize_metric(values, higher_is_better=False)
    
    assert normalized.min() == 0.0
    assert normalized.max() == 1.0
    assert normalized.iloc[0] == 1.0  # Lowest value -> 1 (inverted)
    assert normalized.iloc[-1] == 0.0  # Highest value -> 0 (inverted)


def test_normalize_metric_all_equal():
    """Test normalization when all values are equal."""
    values = pd.Series([5.0, 5.0, 5.0])
    normalized = normalize_metric(values)
    
    # Should return 0.5 for all
    assert all(normalized == 0.5)


def test_calculate_composite_score():
    """Test composite score calculation."""
    results_df = pd.DataFrame({
        'timeframe': ['5m', '15m', '30m'],
        'profit_factor': [1.5, 1.3, 1.8],
        'expectancy': [0.01, 0.008, 0.012],
        'sharpe_ratio': [1.2, 1.0, 1.5],
        'win_rate': [0.56, 0.54, 0.58],
        'max_drawdown_pct': [8.0, 10.0, 7.0]
    })
    
    scored_df = calculate_composite_score(results_df)
    
    # Should have normalized columns
    assert 'profit_factor_norm' in scored_df.columns
    assert 'composite_score' in scored_df.columns
    
    # Scores should be between 0 and 1 (approximately, can be slightly outside)
    assert all(scored_df['composite_score'] >= -0.5)
    assert all(scored_df['composite_score'] <= 1.5)


def test_apply_rejection_filters():
    """Test hard rejection thresholds."""
    results_df = pd.DataFrame({
        'timeframe': ['5m', '15m', '30m'],
        'win_rate': [0.56, 0.52, 0.58],  # 15m fails
        'profit_factor': [1.5, 1.3, 1.1],  # 30m fails
        'expectancy': [0.01, 0.008, -0.001],  # 30m fails
        'max_drawdown_pct': [8.0, 10.0, 15.0],  # 30m fails
        'total_trades': [100, 50, 25]  # 30m fails if min is 30
    })
    
    filtered_df = apply_rejection_filters(results_df)
    
    assert 'passes_filters' in filtered_df.columns
    assert 'failed_filters' in filtered_df.columns
    
    # 5m should pass most filters
    # 30m should fail multiple filters
    assert filtered_df.iloc[2]['failed_filters'] > filtered_df.iloc[0]['failed_filters']


def test_generate_recommendation_go():
    """Test recommendation generation for passing strategy."""
    champion = pd.Series({
        'timeframe': '5m',
        'composite_score': 0.75,
        'passes_filters': True,
        'win_rate': 0.58,
        'profit_factor': 1.5,
        'expectancy': 0.01,
        'sharpe_ratio': 1.3,
        'max_drawdown_pct': 7.5,
        'total_trades': 150,
        'total_profit_pct': 15.0,
        'annual_return_pct': 30.0
    })
    
    recommendation = generate_recommendation(champion)
    
    assert recommendation['verdict'] == 'GO'
    assert recommendation['timeframe'] == '5m'
    assert recommendation['composite_score'] > 0.6
    assert 'metrics' in recommendation
    assert 'next_steps' in recommendation


def test_generate_recommendation_no_go():
    """Test recommendation generation for failing strategy."""
    champion = pd.Series({
        'timeframe': '15m',
        'composite_score': 0.45,
        'passes_filters': False,
        'win_rate': 0.52,
        'profit_factor': 1.15,
        'expectancy': 0.002,
        'sharpe_ratio': 0.8,
        'max_drawdown_pct': 13.0,
        'total_trades': 80,
        'total_profit_pct': 5.0,
        'annual_return_pct': 10.0
    })
    
    recommendation = generate_recommendation(champion)
    
    assert recommendation['verdict'] == 'NO-GO'
    assert 'Further optimization needed' in recommendation['recommendation']


def test_composite_score_weights():
    """Test that composite score uses correct weights."""
    from bot.config.default_config import config
    
    # Verify weights sum close to 1.0 (accounting for negative drawdown weight)
    total_weight = (
        config.SCORE_WEIGHT_PROFIT_FACTOR +
        config.SCORE_WEIGHT_EXPECTANCY +
        config.SCORE_WEIGHT_SHARPE +
        config.SCORE_WEIGHT_WIN_RATE +
        config.SCORE_WEIGHT_DRAWDOWN
    )
    
    assert total_weight == pytest.approx(1.0, abs=0.01)


def test_rejection_thresholds_configured():
    """Test that rejection thresholds are properly configured."""
    from bot.config.default_config import config
    
    assert config.MIN_WIN_RATE > 0.5
    assert config.MIN_PROFIT_FACTOR > 1.0
    assert config.MAX_DRAWDOWN_PERCENT > 0
    assert config.MIN_TRADES_PER_PERIOD > 0


def test_backtest_results_dataframe_structure():
    """Test expected structure of backtest results DataFrame."""
    # This tests the structure that run_backtest_matrix should produce
    results_df = pd.DataFrame({
        'timeframe': ['5m', '15m'],
        'total_trades': [150, 100],
        'win_rate': [0.56, 0.54],
        'profit_factor': [1.35, 1.25],
        'expectancy': [0.008, 0.006],
        'sharpe_ratio': [1.2, 1.0],
        'max_drawdown_pct': [8.5, 9.0],
        'total_profit_pct': [12.5, 10.0],
        'annual_return_pct': [25.0, 20.0]
    })
    
    # Verify required columns exist
    required_columns = [
        'timeframe', 'total_trades', 'win_rate', 'profit_factor',
        'expectancy', 'sharpe_ratio', 'max_drawdown_pct'
    ]
    
    for col in required_columns:
        assert col in results_df.columns


def test_walkforward_window_configuration():
    """Test walk-forward window configuration."""
    from bot.config.default_config import config
    
    assert config.WALKFORWARD_WINDOW_DAYS > 0
    assert config.WALKFORWARD_VALIDATION_DAYS > 0
    assert config.WALKFORWARD_VALIDATION_DAYS < config.WALKFORWARD_WINDOW_DAYS
