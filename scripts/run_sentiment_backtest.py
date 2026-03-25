"""
Script: run_sentiment_backtest.py

Demonstrates the SentimentBacktester with synthetic price and sentiment data.
Run with:

    python scripts/run_sentiment_backtest.py [--output /tmp/report.json]
"""
import argparse
import math
import random
import sys
from pathlib import Path

# Make the project root importable when run directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.sentiment.backtester import SentimentBacktester


def _generate_synthetic_prices(
    n: int = 500, seed: int = 42
) -> list:
    """Generate a synthetic BTC-like price series using a random walk."""
    rng = random.Random(seed)
    price = 50_000.0
    prices = [price]
    for _ in range(n - 1):
        change = rng.gauss(0.0002, 0.015)  # slight upward drift
        price *= 1.0 + change
        prices.append(price)
    return prices


def _generate_synthetic_sentiment(
    prices: list, noise: float = 0.3, seed: int = 99
) -> list:
    """
    Generate sentiment that loosely correlates with price momentum.

    The sentiment is noisy momentum (5-period return normalised to [-1, 1])
    with added Gaussian noise.
    """
    rng = random.Random(seed)
    n = len(prices)
    sentiment = []
    for i in range(n):
        if i < 5:
            s = rng.gauss(0.0, noise)
        else:
            mom = (prices[i] - prices[i - 5]) / prices[i - 5]
            # normalise roughly to [-1, 1]
            s = max(-1.0, min(1.0, mom * 20 + rng.gauss(0.0, noise)))
        sentiment.append(s)
    return sentiment


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run sentiment backtester with synthetic data"
    )
    parser.add_argument(
        "--output",
        default="/tmp/sentiment_backtest_report.json",
        help="Path to save the JSON report (default: /tmp/sentiment_backtest_report.json)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.3,
        help="Sentiment threshold for trade entry (default: 0.3)",
    )
    parser.add_argument(
        "--bars",
        type=int,
        default=500,
        help="Number of synthetic price bars (default: 500)",
    )
    args = parser.parse_args()

    print(f"Generating {args.bars} synthetic price bars...")
    prices = _generate_synthetic_prices(args.bars)
    sentiment = _generate_synthetic_sentiment(prices)

    print(f"Running backtest (sentiment_threshold={args.threshold})...")
    backtester = SentimentBacktester(sentiment_threshold=args.threshold)
    result_no_sent, result_with_sent = backtester.run_backtest(
        prices, sentiment
    )

    report = backtester.compare_results()
    edge = backtester.calculate_sentiment_edge()

    print("\n" + "=" * 60)
    print("SENTIMENT BACKTEST RESULTS")
    print("=" * 60)
    print(f"{'Metric':<30} {'Without Sentiment':>18} {'With Sentiment':>18}")
    print("-" * 66)
    print(
        f"{'Trades':<30} {result_no_sent.total_trades:>18} "
        f"{result_with_sent.total_trades:>18}"
    )
    print(
        f"{'Win Rate':<30} {result_no_sent.win_rate:>17.1%} "
        f"{result_with_sent.win_rate:>17.1%}"
    )
    print(
        f"{'Profit Factor':<30} {result_no_sent.profit_factor:>18.3f} "
        f"{result_with_sent.profit_factor:>18.3f}"
    )
    print(
        f"{'Sharpe Ratio':<30} {result_no_sent.sharpe_ratio:>18.3f} "
        f"{result_with_sent.sharpe_ratio:>18.3f}"
    )
    print(
        f"{'Max Drawdown':<30} {result_no_sent.max_drawdown:>17.1%} "
        f"{result_with_sent.max_drawdown:>17.1%}"
    )
    print(
        f"{'Total Return':<30} {result_no_sent.total_return:>17.1%} "
        f"{result_with_sent.total_return:>17.1%}"
    )
    print("-" * 66)
    print(f"\nSentiment Edge Summary:")
    print(f"  Sharpe improvement : {edge['sharpe_improvement_pct']:+.2f}%")
    print(f"  Win rate delta     : {edge['win_rate_delta']:+.3f}")
    print(f"  Drawdown delta     : {edge['drawdown_delta']:+.3f}")
    print(
        f"\n  Sentiment adds value: "
        f"{'YES ✓' if report.sentiment_adds_value else 'NO ✗'}"
    )
    print("=" * 60)

    output_path = backtester.generate_report(args.output)
    print(f"\nDetailed report saved to: {output_path}")


if __name__ == "__main__":
    main()
