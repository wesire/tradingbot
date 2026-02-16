#!/usr/bin/env python3
"""
Select champion strategy based on composite scoring and rejection thresholds.
"""
import pandas as pd
import json
import argparse
from pathlib import Path
from typing import Dict, List
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from bot.config.default_config import config


def normalize_metric(values: pd.Series, higher_is_better: bool = True) -> pd.Series:
    """
    Normalize metric to 0-1 range.
    
    Args:
        values: Series of metric values
        higher_is_better: Whether higher values are better
        
    Returns:
        Normalized series
    """
    min_val = values.min()
    max_val = values.max()
    
    if max_val == min_val:
        return pd.Series([0.5] * len(values), index=values.index)
    
    normalized = (values - min_val) / (max_val - min_val)
    
    if not higher_is_better:
        normalized = 1 - normalized
    
    return normalized


def calculate_composite_score(results_df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate composite score for each strategy configuration.
    
    Score formula:
    score = (0.30 * pf_norm) + (0.20 * exp_norm) + (0.20 * sharpe_norm) + 
            (0.15 * wr_norm) - (0.15 * dd_norm)
    
    Args:
        results_df: DataFrame with backtest results
        
    Returns:
        DataFrame with composite scores added
    """
    df = results_df.copy()
    
    # Normalize each metric
    df['profit_factor_norm'] = normalize_metric(df['profit_factor'], higher_is_better=True)
    df['expectancy_norm'] = normalize_metric(df['expectancy'], higher_is_better=True)
    df['sharpe_norm'] = normalize_metric(df['sharpe_ratio'], higher_is_better=True)
    df['win_rate_norm'] = normalize_metric(df['win_rate'], higher_is_better=True)
    df['drawdown_norm'] = normalize_metric(df['max_drawdown_pct'], higher_is_better=False)
    
    # Calculate composite score
    df['composite_score'] = (
        config.SCORE_WEIGHT_PROFIT_FACTOR * df['profit_factor_norm'] +
        config.SCORE_WEIGHT_EXPECTANCY * df['expectancy_norm'] +
        config.SCORE_WEIGHT_SHARPE * df['sharpe_norm'] +
        config.SCORE_WEIGHT_WIN_RATE * df['win_rate_norm'] -
        config.SCORE_WEIGHT_DRAWDOWN * df['drawdown_norm']
    )
    
    return df


def apply_rejection_filters(results_df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply hard rejection thresholds to filter out poor strategies.
    
    Args:
        results_df: DataFrame with backtest results
        
    Returns:
        DataFrame with only strategies that pass all filters
    """
    df = results_df.copy()
    
    # Apply filters
    filters = {
        'win_rate': df['win_rate'] >= config.MIN_WIN_RATE,
        'profit_factor': df['profit_factor'] >= config.MIN_PROFIT_FACTOR,
        'expectancy': df['expectancy'] > config.MIN_EXPECTANCY,
        'max_drawdown': df['max_drawdown_pct'] <= config.MAX_DRAWDOWN_PERCENT,
        'trade_count': df['total_trades'] >= config.MIN_TRADES_PER_PERIOD
    }
    
    # Combined filter
    df['passes_filters'] = True
    for filter_name, condition in filters.items():
        df['passes_filters'] = df['passes_filters'] & condition
        df[f'filter_{filter_name}'] = condition
    
    # Count failures for reporting
    df['failed_filters'] = sum(~condition for condition in filters.values())
    
    return df


def generate_recommendation(champion_row: pd.Series) -> Dict:
    """
    Generate recommendation based on champion strategy.
    
    Args:
        champion_row: Series with champion strategy metrics
        
    Returns:
        Recommendation dictionary
    """
    # Determine go/no-go
    go_live = (
        champion_row['passes_filters'] and
        champion_row['composite_score'] > 0.6 and
        champion_row['win_rate'] > 0.55 and
        champion_row['profit_factor'] > 1.4
    )
    
    recommendation = {
        'verdict': 'GO' if go_live else 'NO-GO',
        'timeframe': champion_row['timeframe'],
        'composite_score': float(champion_row['composite_score']),
        'parameters': champion_row.get('parameters', {}),
        'metrics': {
            'win_rate': float(champion_row['win_rate']),
            'profit_factor': float(champion_row['profit_factor']),
            'expectancy': float(champion_row['expectancy']),
            'sharpe_ratio': float(champion_row['sharpe_ratio']),
            'max_drawdown_pct': float(champion_row['max_drawdown_pct']),
            'total_trades': int(champion_row['total_trades']),
            'total_profit_pct': float(champion_row.get('total_profit_pct', 0))
        },
        'risk_return': {
            'expected_annual_return': float(champion_row.get('annual_return_pct', 0)),
            'expected_max_drawdown': float(champion_row['max_drawdown_pct']),
            'risk_reward_ratio': float(champion_row['profit_factor'])
        },
        'recommendation': (
            'Strategy meets all thresholds and is recommended for dry-run testing.' 
            if go_live 
            else 'Strategy does not meet minimum thresholds. Further optimization needed.'
        ),
        'next_steps': (
            [
                'Deploy to dry-run environment',
                'Monitor performance for 1 week',
                'Compare dry-run results to backtest',
                'Consider live deployment if dry-run successful'
            ] if go_live else [
                'Review failed filters',
                'Adjust strategy parameters',
                'Run additional optimization',
                'Consider different timeframes or market conditions'
            ]
        )
    }
    
    return recommendation


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Select champion strategy from backtest results"
    )
    parser.add_argument(
        '--results-file',
        default='artifacts/metrics.csv',
        help='Path to backtest results CSV'
    )
    parser.add_argument(
        '--output-dir',
        default='artifacts/champion',
        help='Output directory for champion results'
    )
    
    args = parser.parse_args()
    
    # Load results
    results_file = Path(args.results_file)
    if not results_file.exists():
        print(f"Error: Results file not found: {results_file}")
        print("Run backtest matrix first to generate results.")
        sys.exit(1)
    
    print(f"Loading results from: {results_file}")
    results_df = pd.read_csv(results_file)
    print(f"Loaded {len(results_df)} strategy configurations")
    
    # Calculate composite scores
    print("\nCalculating composite scores...")
    results_df = calculate_composite_score(results_df)
    
    # Apply rejection filters
    print("Applying rejection filters...")
    results_df = apply_rejection_filters(results_df)
    
    passing = results_df[results_df['passes_filters']]
    failing = results_df[~results_df['passes_filters']]
    
    print(f"  Passing: {len(passing)}")
    print(f"  Failing: {len(failing)}")
    
    if len(passing) == 0:
        print("\n⚠️  NO STRATEGIES PASSED ALL FILTERS")
        print("\nTop 5 by composite score (failed filters):")
        top_failed = failing.nlargest(5, 'composite_score')
        print(top_failed[['timeframe', 'composite_score', 'failed_filters', 
                          'win_rate', 'profit_factor', 'max_drawdown_pct']])
        
        # Generate no-go recommendation with best failing strategy
        champion = failing.nlargest(1, 'composite_score').iloc[0]
    else:
        # Select champion (highest composite score among passing strategies)
        print("\nSelecting champion strategy...")
        champion = passing.nlargest(1, 'composite_score').iloc[0]
    
    # Display champion
    print(f"\n{'='*60}")
    print("CHAMPION STRATEGY")
    print('='*60)
    print(f"Timeframe: {champion['timeframe']}")
    print(f"Composite Score: {champion['composite_score']:.4f}")
    print(f"Passes Filters: {champion['passes_filters']}")
    print(f"\nMetrics:")
    print(f"  Win Rate: {champion['win_rate']:.2%}")
    print(f"  Profit Factor: {champion['profit_factor']:.2f}")
    print(f"  Expectancy: {champion['expectancy']:.4f}")
    print(f"  Sharpe Ratio: {champion['sharpe_ratio']:.2f}")
    print(f"  Max Drawdown: {champion['max_drawdown_pct']:.2f}%")
    print(f"  Total Trades: {int(champion['total_trades'])}")
    
    # Generate recommendation
    recommendation = generate_recommendation(champion)
    
    print(f"\n{'='*60}")
    print(f"VERDICT: {recommendation['verdict']}")
    print('='*60)
    print(recommendation['recommendation'])
    
    # Save outputs
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Save ranked results
    ranked_file = output_dir / 'ranked_strategies.csv'
    results_df.sort_values('composite_score', ascending=False).to_csv(ranked_file, index=False)
    print(f"\nRanked strategies saved to: {ranked_file}")
    
    # Save recommendation
    recommendation_file = output_dir / 'recommendation.json'
    with open(recommendation_file, 'w') as f:
        json.dump(recommendation, f, indent=2)
    print(f"Recommendation saved to: {recommendation_file}")
    
    # Save champion parameters
    champion_params_file = output_dir / 'champion_parameters.json'
    champion_params = {
        'timeframe': champion['timeframe'],
        'parameters': champion.get('parameters', {}),
        'composite_score': float(champion['composite_score'])
    }
    with open(champion_params_file, 'w') as f:
        json.dump(champion_params, f, indent=2)
    print(f"Champion parameters saved to: {champion_params_file}")
    
    print(f"\n{'='*60}")
    print("Selection complete!")
    print('='*60)


if __name__ == "__main__":
    main()
