#!/usr/bin/env python3
"""
Run backtest matrix across multiple timeframes using the real MLBacktester.
"""
import argparse
import os
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from bot.config.default_config import config


def run_single_backtest(
    timeframe: str,
    model_path: str,
    pair: str,
    start_date: str,
    end_date: str,
) -> dict:
    """
    Run a single backtest using the real MLBacktester.

    Args:
        timeframe: Timeframe to test (e.g. '5m', '1h', '4h')
        model_path: Path to the trained model .joblib file
        pair: Trading pair (e.g. 'BTC/USDT:USDT')
        start_date: ISO start date string
        end_date: ISO end date string

    Returns:
        Dictionary with backtest results, or None on failure
    """
    print(f"  Running backtest for {timeframe}...")

    try:
        from bot.ml.backtester import MLBacktester

        bt = MLBacktester(model_path=model_path)
        result = bt.run(
            pair=pair,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
        )

        cm = result.confusion_matrix
        row = {
            "timeframe": timeframe,
            "pair": result.pair or pair,
            "precision": round(result.precision, 4),
            "recall": round(result.recall, 4),
            "f1_score": round(result.f1_score, 4),
            "accuracy": round(result.accuracy, 4),
            "total_predictions": result.total_predictions,
            "tp": cm.tp,
            "fp": cm.fp,
            "tn": cm.tn,
            "fn": cm.fn,
            "profit_with_ml": round(result.profit_with_ml, 4),
            "profit_without_ml": round(result.profit_without_ml, 4),
            "profit_improvement_pct": round(result.profit_improvement_pct, 4),
            "is_demo": result.is_demo,
            "model_version": result.model_version or model_path,
        }

        status = "demo" if result.is_demo else "real"
        print(
            f"    ✓ Complete ({status}): accuracy={result.accuracy:.1%}  "
            f"f1={result.f1_score:.3f}  profit_with_ml={result.profit_with_ml:.2f}%"
        )
        return row

    except Exception as exc:
        print(f"    ✗ Error: {exc}")
        return None


def main():
    """Main function."""
    default_model = os.getenv(
        "ML_MODEL_PATH",
        str(Path(__file__).parent.parent / "models" / "signal_classifier_latest.joblib"),
    )

    parser = argparse.ArgumentParser(
        description="Run backtest matrix across timeframes"
    )
    parser.add_argument(
        "--timeframes",
        nargs="+",
        default=config.TIMEFRAMES,
        help="Timeframes to test",
    )
    parser.add_argument(
        "--pair",
        default=config.TRADING_PAIR,
        help="Trading pair to backtest",
    )
    parser.add_argument(
        "--start-date",
        default=config.BACKTEST_START_DATE,
        help="Backtest start date (ISO format)",
    )
    parser.add_argument(
        "--end-date",
        default=config.BACKTEST_END_DATE,
        help="Backtest end date (ISO format)",
    )
    parser.add_argument(
        "--model-path",
        default=default_model,
        help=f"Path to trained model .joblib file (default: {default_model})",
    )
    parser.add_argument(
        "--output-dir",
        default="artifacts",
        help="Output directory",
    )

    args = parser.parse_args()

    print(f"{'='*60}")
    print("BACKTEST MATRIX")
    print("=" * 60)
    print(f"Timeframes:  {args.timeframes}")
    print(f"Pair:        {args.pair}")
    print(f"Date range:  {args.start_date} → {args.end_date}")
    print(f"Model path:  {args.model_path}")
    print()

    results = []

    for timeframe in args.timeframes:
        row = run_single_backtest(
            timeframe=timeframe,
            model_path=args.model_path,
            pair=args.pair,
            start_date=args.start_date,
            end_date=args.end_date,
        )
        if row:
            results.append(row)

    if not results:
        print("No results collected — exiting.")
        sys.exit(1)

    # Save results
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    results_df = pd.DataFrame(results)

    csv_file = output_dir / "metrics.csv"
    results_df.to_csv(csv_file, index=False)
    print(f"\n✓ Results saved to: {csv_file}")

    # Print summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print("=" * 60)
    summary_cols = [
        "timeframe", "accuracy", "precision", "recall", "f1_score",
        "profit_with_ml", "profit_without_ml", "is_demo",
    ]
    display_cols = [c for c in summary_cols if c in results_df.columns]
    print(results_df[display_cols].to_string(index=False))

    print(f"\n{'='*60}")
    print("Backtest matrix complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
