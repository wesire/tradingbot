"""
ETH/USDT Perpetual Futures Scalping Strategy for Freqtrade.
Tuned for medium volatility trend continuation.
"""
from typing import Optional
import pandas as pd
from pandas import DataFrame
from freqtrade.strategy import IStrategy, informative
import talib.abstract as ta

from bot.strategy.signal_filters import SignalFilters
from bot.strategy.risk_engine import RiskEngine
from bot.config.default_config import config as app_config


class ETHScalpStrategy(IStrategy):
    """
    ETH/USDT scalping strategy with regime filtering and trend continuation focus.

    Strategy Logic:
    1. Regime Filter (HTF): EMA crossover + ADX for trend direction/strength
    2. Entry Signals (LTF): Trend continuation entries with momentum confirmation
    3. Filters: Volatility (ATR) and volume spike detection
    4. Risk Management: Dynamic stops, partial TPs, breakeven logic
    
    Differences from BTC strategy:
    - Lower ADX threshold (22 vs 25) - ETH can trend with less strong momentum
    - Higher ATR threshold (0.001 vs 0.0005) - ETH typically more volatile
    - Stronger volume confirmation (1.3x vs 1.2x)
    - Slightly wider stops (2.2 ATR vs 2.0) to handle volatility
    """

    # Strategy metadata
    INTERFACE_VERSION = 3

    # Enable shorts (futures)
    can_short = True

    # Minimal ROI - handled by custom exit logic
    minimal_roi = {
        "0": 0.10,
        "30": 0.05,
        "60": 0.02,
        "120": 0.01
    }

    # Stoploss
    stoploss = -0.025  # Slightly wider hard stop for ETH volatility

    # Trailing stop
    trailing_stop = False

    # Optimal timeframe
    timeframe = "5m"

    # Run "populate_indicators()" only for new candle
    process_only_new_candles = True

    # Use exit signals
    use_exit_signal = True
    exit_profit_only = False
    exit_profit_offset = 0.0

    # Number of candles the strategy requires before producing valid signals
    startup_candle_count: int = 250

    # Strategy parameters (can be optimized)
    # Regime Filter - TODO: calibrate via hyperopt/backtest
    regime_htf_timeframe = "15m"
    regime_ema_fast = 50
    regime_ema_slow = 200
    regime_adx_threshold = 22  # Lower for ETH
    regime_adx_period = 14

    # Entry Signals - TODO: calibrate via hyperopt/backtest
    entry_ema_period = 21
    entry_rsi_period = 14
    entry_rsi_long_threshold = 42  # Slightly higher
    entry_rsi_short_threshold = 58  # Slightly lower

    # Filters - TODO: calibrate via hyperopt/backtest
    filter_atr_period = 14
    filter_atr_min_threshold = 0.001  # Higher for ETH
    filter_volume_period = 20
    entry_volume_multiplier = 1.3  # Stronger volume requirement

    # Position sizing
    position_adjustment_enable = True
    max_entry_position_adjustment = 0  # No DCA/averaging

    def __init__(self, config: dict, *args, **kwargs):
        super().__init__(config)

        # Initialize signal filters and risk engine
        self.signal_filters = SignalFilters(
            atr_period=self.filter_atr_period,
            atr_min_threshold=self.filter_atr_min_threshold,
            volume_period=self.filter_volume_period,
            volume_multiplier=self.entry_volume_multiplier
        )

        self.risk_engine = RiskEngine(
            max_risk_per_trade=app_config.MAX_RISK_PER_TRADE,
            max_daily_drawdown=app_config.MAX_DAILY_DRAWDOWN,
            max_consecutive_losses=app_config.MAX_CONSECUTIVE_LOSSES,
            cooldown_minutes=app_config.COOLDOWN_MINUTES,
            stop_loss_atr_multiplier=2.2,  # Wider for ETH
            stop_loss_max_percent=0.025,
            take_profit_r_levels=app_config.TAKE_PROFIT_R_LEVELS,
            breakeven_after_first_tp=app_config.BREAKEVEN_AFTER_FIRST_TP
        )

    @informative('15m')
    def populate_indicators_15m(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Populate indicators for higher timeframe (regime detection).
        """
        # EMA for regime
        dataframe['ema_fast'] = ta.EMA(dataframe, timeperiod=self.regime_ema_fast)
        dataframe['ema_slow'] = ta.EMA(dataframe, timeperiod=self.regime_ema_slow)

        # ADX for trend strength
        dataframe['adx'] = ta.ADX(dataframe, timeperiod=self.regime_adx_period)

        # Regime determination
        dataframe['regime_bullish'] = (
            (dataframe['ema_fast'] > dataframe['ema_slow']) &
            (dataframe['adx'] > self.regime_adx_threshold)
        )

        dataframe['regime_bearish'] = (
            (dataframe['ema_fast'] < dataframe['ema_slow']) &
            (dataframe['adx'] > self.regime_adx_threshold)
        )

        dataframe['regime_neutral'] = ~(
            dataframe['regime_bullish'] | dataframe['regime_bearish']
        )

        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Populate indicators for execution timeframe.
        """
        # Entry EMA
        dataframe['ema'] = ta.EMA(dataframe, timeperiod=self.entry_ema_period)

        # VWAP (approximation using cumulative)
        dataframe['vwap'] = (
            (dataframe['close'] * dataframe['volume']).cumsum() /
            dataframe['volume'].cumsum()
        )

        # RSI for entry triggers
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=self.entry_rsi_period)

        # MACD for momentum confirmation (ETH-specific)
        macd = ta.MACD(dataframe)
        dataframe['macd'] = macd['macd']
        dataframe['macd_signal'] = macd['macdsignal']
        dataframe['macd_hist'] = macd['macdhist']

        # Apply signal filters (ATR, volume)
        dataframe = self.signal_filters.apply_all_filters(
            dataframe,
            enable_mean_reversion=True
        )

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Populate buy/sell signals based on regime and entry conditions.
        """
        # Long Entry Conditions
        long_conditions = [
            # HTF regime is bullish
            (dataframe['regime_bullish_15m'] == True),

            # Price near EMA support
            (dataframe['close'] <= dataframe['ema'] * 1.015),  # Within 1.5% of EMA

            # RSI recovery (slightly different thresholds for ETH)
            (dataframe['rsi'] > self.entry_rsi_long_threshold),
            (dataframe['rsi'].shift(1) <= self.entry_rsi_long_threshold),

            # MACD momentum confirmation
            (dataframe['macd'] > dataframe['macd_signal']),

            # Filters passed
            (dataframe['filters_passed'] == True),

            # Volume condition
            (dataframe['volume'] > 0)
        ]

        # Short Entry Conditions
        short_conditions = [
            # HTF regime is bearish
            (dataframe['regime_bearish_15m'] == True),

            # Price near EMA resistance
            (dataframe['close'] >= dataframe['ema'] * 0.985),  # Within 1.5% of EMA

            # RSI rollover
            (dataframe['rsi'] < self.entry_rsi_short_threshold),
            (dataframe['rsi'].shift(1) >= self.entry_rsi_short_threshold),

            # MACD momentum confirmation
            (dataframe['macd'] < dataframe['macd_signal']),

            # Filters passed
            (dataframe['filters_passed'] == True),

            # Volume condition
            (dataframe['volume'] > 0)
        ]

        # Combine conditions
        dataframe['enter_long'] = 0
        dataframe['enter_short'] = 0

        if long_conditions:
            dataframe.loc[
                pd.concat(long_conditions, axis=1).all(axis=1),
                'enter_long'
            ] = 1

        if short_conditions:
            dataframe.loc[
                pd.concat(short_conditions, axis=1).all(axis=1),
                'enter_short'
            ] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Populate exit signals (optional - mainly using custom exit logic).
        """
        dataframe['exit_long'] = 0
        dataframe['exit_short'] = 0

        # Exit long when regime flips bearish
        dataframe.loc[
            (dataframe['regime_bearish_15m'] == True),
            'exit_long'
        ] = 1

        # Exit short when regime flips bullish
        dataframe.loc[
            (dataframe['regime_bullish_15m'] == True),
            'exit_short'
        ] = 1

        return dataframe

    def custom_stoploss(
        self,
        pair: str,
        trade: 'Trade',
        current_time: 'datetime',
        current_rate: float,
        current_profit: float,
        **kwargs
    ) -> Optional[float]:
        """
        Custom stoploss logic using ATR-based dynamic stops.
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        
        if dataframe is None or len(dataframe) == 0:
            return None
        
        last_candle = dataframe.iloc[-1].squeeze()
        
        # Use risk engine to calculate dynamic stop
        stop_distance = self.risk_engine.calculate_stop_loss(
            entry_price=trade.open_rate,
            current_price=current_rate,
            atr=last_candle.get('atr', 0),
            trade_side='long' if trade.is_short is False else 'short'
        )
        
        if stop_distance:
            return stop_distance
        
        return None

    def custom_exit(
        self,
        pair: str,
        trade: 'Trade',
        current_time: 'datetime',
        current_rate: float,
        current_profit: float,
        **kwargs
    ) -> Optional[str]:
        """
        Custom exit logic for partial profits and breakeven.
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        
        if dataframe is None or len(dataframe) == 0:
            return None
        
        last_candle = dataframe.iloc[-1].squeeze()
        
        # Check if we should exit based on risk engine rules
        should_exit, reason = self.risk_engine.check_exit_conditions(
            entry_price=trade.open_rate,
            current_price=current_rate,
            trade_duration_minutes=(current_time - trade.open_date_utc).total_seconds() / 60,
            current_profit_ratio=current_profit,
            atr=last_candle.get('atr', 0)
        )
        
        if should_exit:
            return reason
        
        return None
