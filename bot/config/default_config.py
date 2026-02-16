"""
Default configuration for the BTC/USDT scalping bot.
All parameters can be overridden via environment variables.
"""
from typing import Dict, Any
import os


class DefaultConfig:
    """Default configuration parameters for the trading bot."""
    
    # Exchange Configuration
    EXCHANGE_NAME: str = os.getenv("EXCHANGE_NAME", "binance")
    EXCHANGE_SANDBOX: bool = os.getenv("EXCHANGE_SANDBOX", "true").lower() == "true"
    
    # Trading Mode - CRITICAL SAFETY DEFAULTS
    TRADING_MODE: str = os.getenv("TRADING_MODE", "dry_run")  # dry_run, live
    LIVE_TRADING_ENABLED: bool = os.getenv("LIVE_TRADING_ENABLED", "false").lower() == "true"
    LIVE_CONFIRMATION_TOKEN: str = os.getenv("LIVE_CONFIRMATION_TOKEN", "")
    
    # Symbol Configuration
    STAKE_CURRENCY: str = "USDT"
    STAKE_AMOUNT: float = 100.0  # Default stake per trade
    TRADING_PAIR: str = "BTC/USDT:USDT"  # Perpetual futures notation
    
    # Risk Management Parameters
    MAX_RISK_PER_TRADE: float = float(os.getenv("MAX_RISK_PER_TRADE", "0.005"))  # 0.5%
    MAX_DAILY_DRAWDOWN: float = float(os.getenv("MAX_DAILY_DRAWDOWN", "0.025"))  # 2.5%
    MAX_CONSECUTIVE_LOSSES: int = int(os.getenv("MAX_CONSECUTIVE_LOSSES", "3"))
    COOLDOWN_MINUTES: int = int(os.getenv("COOLDOWN_MINUTES", "30"))
    MAX_OPEN_TRADES: int = 1  # Only BTC
    
    # Stop Loss & Take Profit
    STOP_LOSS_ATR_MULTIPLIER: float = 1.5
    STOP_LOSS_MAX_PERCENT: float = 0.02  # Hard 2% max stop
    TAKE_PROFIT_R_LEVELS: list = [1.0, 1.5, 2.0]  # R multiples for partials
    BREAKEVEN_AFTER_FIRST_TP: bool = True
    
    # Strategy Parameters - Regime Filter
    REGIME_HTF_TIMEFRAME: str = "1h"  # Higher timeframe for regime
    REGIME_EMA_FAST: int = 50
    REGIME_EMA_SLOW: int = 200
    REGIME_ADX_THRESHOLD: int = 25
    REGIME_ADX_PERIOD: int = 14
    
    # Strategy Parameters - Entry Signals
    ENTRY_EMA_PERIOD: int = 21
    ENTRY_RSI_PERIOD: int = 14
    ENTRY_RSI_LONG_THRESHOLD: int = 40  # RSI crosses above
    ENTRY_RSI_SHORT_THRESHOLD: int = 60  # RSI crosses below
    ENTRY_VOLUME_MULTIPLIER: float = 1.5  # Relative volume spike
    
    # Strategy Parameters - Filters
    FILTER_ATR_PERIOD: int = 14
    FILTER_ATR_MIN_THRESHOLD: float = 0.0005  # Minimum ATR to avoid dead markets
    FILTER_VOLUME_PERIOD: int = 20
    
    # Timeframes to Test
    TIMEFRAMES: list = ["1m", "3m", "5m", "15m", "30m"]
    PRIMARY_TIMEFRAME: str = "5m"  # Default execution timeframe
    
    # Backtesting Configuration
    BACKTEST_START_DATE: str = os.getenv("BACKTEST_START_DATE", "2023-01-01")
    BACKTEST_END_DATE: str = os.getenv("BACKTEST_END_DATE", "2024-12-31")
    BACKTEST_INITIAL_BALANCE: float = 10000.0
    
    # Optimization Configuration
    OPTIMIZATION_EPOCHS: int = int(os.getenv("OPTIMIZATION_EPOCHS", "100"))
    OPTIMIZATION_TIMERANGE: str = "20230101-20241231"
    
    # Walk-Forward Configuration
    WALKFORWARD_WINDOW_DAYS: int = int(os.getenv("WALKFORWARD_WINDOW_DAYS", "90"))
    WALKFORWARD_VALIDATION_DAYS: int = int(os.getenv("WALKFORWARD_VALIDATION_DAYS", "30"))
    WALKFORWARD_STEP_DAYS: int = 30
    
    # Performance Thresholds (Hard Rejection Filters)
    MIN_WIN_RATE: float = float(os.getenv("MIN_WIN_RATE", "0.54"))  # 54%
    MIN_PROFIT_FACTOR: float = float(os.getenv("MIN_PROFIT_FACTOR", "1.25"))
    MIN_EXPECTANCY: float = 0.0
    MAX_DRAWDOWN_PERCENT: float = float(os.getenv("MAX_DRAWDOWN_PERCENT", "12.0"))
    MIN_TRADES_PER_PERIOD: int = int(os.getenv("MIN_TRADES_PER_PERIOD", "30"))
    
    # Composite Scoring Weights
    SCORE_WEIGHT_PROFIT_FACTOR: float = 0.30
    SCORE_WEIGHT_EXPECTANCY: float = 0.20
    SCORE_WEIGHT_SHARPE: float = 0.20
    SCORE_WEIGHT_WIN_RATE: float = 0.15
    SCORE_WEIGHT_DRAWDOWN: float = 0.15  # Negative contribution
    
    # TradingView Webhook Configuration
    TV_WEBHOOK_SECRET: str = os.getenv("TV_WEBHOOK_SECRET", "")
    TV_WEBHOOK_PORT: int = int(os.getenv("TV_WEBHOOK_PORT", "8000"))
    TV_MAX_ALERT_AGE_SECONDS: int = 30  # Reject stale alerts
    TV_CONFIDENCE_THRESHOLD: float = 0.7  # Minimum confidence to act
    
    # Circuit Breaker Configuration
    CIRCUIT_BREAKER_FAIL_COUNT: int = 5
    CIRCUIT_BREAKER_COOLDOWN_MINUTES: int = 15
    STALE_DATA_THRESHOLD_SECONDS: int = 60
    
    # Database Configuration
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./alerts.db")
    
    # Logging Configuration
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE: str = os.getenv("LOG_FILE", "bot.log")
    
    # Rate Limiting
    EXCHANGE_RATE_LIMIT: int = 50  # Requests per second
    
    # Notification Configuration
    TELEGRAM_ENABLED: bool = bool(os.getenv("TELEGRAM_BOT_TOKEN"))
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")
    DISCORD_WEBHOOK_URL: str = os.getenv("DISCORD_WEBHOOK_URL", "")
    
    @classmethod
    def to_dict(cls) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            key: value
            for key, value in cls.__dict__.items()
            if not key.startswith("_") and not callable(value)
        }
    
    @classmethod
    def validate_live_trading(cls) -> bool:
        """
        Validate that live trading is properly configured.
        Returns True only if ALL safety checks pass.
        """
        if not cls.LIVE_TRADING_ENABLED:
            return False
        
        if cls.TRADING_MODE != "live":
            return False
        
        if not cls.LIVE_CONFIRMATION_TOKEN:
            return False
        
        # Additional validation: require explicit token
        expected_token = "I_UNDERSTAND_LIVE_TRADING_RISKS"
        if cls.LIVE_CONFIRMATION_TOKEN != expected_token:
            return False
        
        return True


# Create singleton instance
config = DefaultConfig()
