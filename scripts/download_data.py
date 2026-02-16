#!/usr/bin/env python3
"""
Download historical OHLCV data for backtesting.
Supports multiple timeframes and validates data quality.
"""
import ccxt
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import argparse
import json
import sys
from typing import List, Optional

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from bot.config.default_config import config


def download_ohlcv(
    exchange: ccxt.Exchange,
    symbol: str,
    timeframe: str,
    since: datetime,
    until: Optional[datetime] = None
) -> pd.DataFrame:
    """
    Download OHLCV data from exchange.
    
    Args:
        exchange: CCXT exchange instance
        symbol: Trading pair symbol
        timeframe: Timeframe (e.g., '5m', '1h')
        since: Start date
        until: End date (optional, defaults to now)
        
    Returns:
        DataFrame with OHLCV data
    """
    if until is None:
        until = datetime.now()
    
    print(f"Downloading {symbol} {timeframe} from {since} to {until}")
    
    # Convert to milliseconds
    since_ms = int(since.timestamp() * 1000)
    until_ms = int(until.timestamp() * 1000)
    
    all_candles = []
    current_since = since_ms
    
    while current_since < until_ms:
        try:
            candles = exchange.fetch_ohlcv(
                symbol=symbol,
                timeframe=timeframe,
                since=current_since,
                limit=1000
            )
            
            if not candles:
                break
            
            all_candles.extend(candles)
            
            # Update since to last candle timestamp + 1
            current_since = candles[-1][0] + 1
            
            print(f"  Downloaded {len(candles)} candles, total: {len(all_candles)}")
            
            # Rate limiting
            exchange.sleep(exchange.rateLimit / 1000)
            
        except Exception as e:
            print(f"  Error downloading data: {e}")
            break
    
    # Convert to DataFrame
    df = pd.DataFrame(
        all_candles,
        columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
    )
    
    # Convert timestamp to datetime
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    
    # Remove duplicates
    df = df[~df.index.duplicated(keep='first')]
    
    # Sort by timestamp
    df.sort_index(inplace=True)
    
    return df


def validate_data(df: pd.DataFrame, timeframe: str) -> dict:
    """
    Validate data quality and detect gaps.
    
    Args:
        df: OHLCV DataFrame
        timeframe: Expected timeframe
        
    Returns:
        Dictionary with validation results
    """
    results = {
        'total_candles': len(df),
        'start_date': df.index[0].isoformat() if len(df) > 0 else None,
        'end_date': df.index[-1].isoformat() if len(df) > 0 else None,
        'missing_values': df.isnull().sum().to_dict(),
        'gaps': []
    }
    
    # Check for gaps
    timeframe_delta = pd.Timedelta(timeframe)
    expected_freq = timeframe_delta
    
    time_diffs = df.index.to_series().diff()
    large_gaps = time_diffs[time_diffs > expected_freq * 1.5]
    
    if len(large_gaps) > 0:
        for ts, gap in large_gaps.items():
            results['gaps'].append({
                'timestamp': ts.isoformat(),
                'gap_duration': str(gap)
            })
    
    results['gap_count'] = len(results['gaps'])
    results['data_quality'] = 'good' if results['gap_count'] == 0 else 'gaps_detected'
    
    return results


def save_data(df: pd.DataFrame, symbol: str, timeframe: str, output_dir: Path):
    """
    Save data in Freqtrade-compatible format.
    
    Args:
        df: OHLCV DataFrame
        symbol: Trading pair symbol
        timeframe: Timeframe
        output_dir: Output directory
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Freqtrade expects JSON format
    # Symbol format: BTC_USDT for filenames
    safe_symbol = symbol.replace('/', '_').replace(':', '')
    filename = f"{safe_symbol}-{timeframe}.json"
    filepath = output_dir / filename
    
    # Convert to Freqtrade format
    data = []
    for idx, row in df.iterrows():
        data.append([
            int(idx.timestamp() * 1000),  # timestamp in ms
            row['open'],
            row['high'],
            row['low'],
            row['close'],
            row['volume']
        ])
    
    # Save as JSON
    with open(filepath, 'w') as f:
        json.dump(data, f)
    
    print(f"  Saved to: {filepath}")
    
    # Also save as CSV for easy inspection
    csv_path = output_dir / f"{safe_symbol}-{timeframe}.csv"
    df.to_csv(csv_path)
    print(f"  CSV saved to: {csv_path}")


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Download historical data for backtesting"
    )
    parser.add_argument(
        '--exchange',
        default=config.EXCHANGE_NAME,
        help='Exchange name (default: binance)'
    )
    parser.add_argument(
        '--symbol',
        default=config.TRADING_PAIR,
        help='Trading pair symbol (default: BTC/USDT:USDT)'
    )
    parser.add_argument(
        '--timeframes',
        nargs='+',
        default=config.TIMEFRAMES,
        help='Timeframes to download (default: 1m 3m 5m 15m 30m)'
    )
    parser.add_argument(
        '--start-date',
        default=config.BACKTEST_START_DATE,
        help='Start date (YYYY-MM-DD)'
    )
    parser.add_argument(
        '--end-date',
        default=config.BACKTEST_END_DATE,
        help='End date (YYYY-MM-DD)'
    )
    parser.add_argument(
        '--output-dir',
        default='bot/data',
        help='Output directory for data files'
    )
    
    args = parser.parse_args()
    
    # Parse dates
    start_date = datetime.strptime(args.start_date, '%Y-%m-%d')
    end_date = datetime.strptime(args.end_date, '%Y-%m-%d')
    
    # Initialize exchange
    print(f"Initializing {args.exchange} exchange...")
    exchange_class = getattr(ccxt, args.exchange)
    exchange = exchange_class({
        'enableRateLimit': True,
        'options': {'defaultType': 'future'}
    })
    
    # Load markets
    exchange.load_markets()
    print(f"Exchange initialized: {len(exchange.markets)} markets available")
    
    output_dir = Path(args.output_dir)
    
    # Download data for each timeframe
    for timeframe in args.timeframes:
        print(f"\n{'='*60}")
        print(f"Timeframe: {timeframe}")
        print('='*60)
        
        try:
            # Download data
            df = download_ohlcv(
                exchange=exchange,
                symbol=args.symbol,
                timeframe=timeframe,
                since=start_date,
                until=end_date
            )
            
            if df.empty:
                print(f"  No data downloaded for {timeframe}")
                continue
            
            # Validate data
            validation = validate_data(df, timeframe)
            print(f"\n  Validation Results:")
            print(f"    Total candles: {validation['total_candles']}")
            print(f"    Date range: {validation['start_date']} to {validation['end_date']}")
            print(f"    Data quality: {validation['data_quality']}")
            print(f"    Gaps detected: {validation['gap_count']}")
            
            if validation['gaps']:
                print(f"    First 5 gaps:")
                for gap in validation['gaps'][:5]:
                    print(f"      {gap['timestamp']}: {gap['gap_duration']}")
            
            # Save data
            save_data(df, args.symbol, timeframe, output_dir)
            
            print(f"  ✓ Successfully downloaded {timeframe} data")
            
        except Exception as e:
            print(f"  ✗ Error processing {timeframe}: {e}")
            continue
    
    print(f"\n{'='*60}")
    print("Download complete!")
    print('='*60)


if __name__ == "__main__":
    main()
