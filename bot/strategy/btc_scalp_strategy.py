"""
BTC/USDT Perpetual Futures Scalping Strategy for Freqtrade.
Implements regime filtering, multi-timeframe analysis, and dynamic entries.
"""
from typing import Optional
import numpy as np
import pandas as pd
from pandas import DataFrame
from freqtrade.strategy import IStrategy, informative
import talib.abstract as ta

from bot.strategy.signal_filters import SignalFilters
from bot.strategy.risk_engine import RiskEngine
from bot.config.default_config import config


class BTCScalpStrategy(IStrategy):
    """
    BTC/USDT scalping strategy with regime filtering and dynamic risk management.
    
    Strategy Logic:
    1. Regime Filter (HTF): EMA crossover + ADX for trend direction/strength
    2. Entry Signals (LTF): Pullback/bounce entries with RSI confirmation
    3. Filters: Volatility (ATR) and volume spike detection
    4. Risk Management: Dynamic stops, partial TPs, breakeven logic
    """
    
    # Strategy metadata
    INTERFACE_VERSION = 3
    
    # Minimal ROI - handled by custom exit logic
    minimal_roi = {
        "0": 0.10,
        "30": 0.05,
        "60": 0.02,
        "120": 0.01
    }
    
    # Stoploss
    stoploss = -0.02  # Hard 2% stop as fallback
    
    # Trailing stop
    trailing_stop = False
    
    # Optimal timeframe
    timeframe = config.PRIMARY_TIMEFRAME
    
    # Run "populate_indicators()" only for new candle
    process_only_new_candles = True
    
    # Use exit signals
    use_exit_signal = True
    exit_profit_only = False
    exit_profit_offset = 0.0
    
    # Number of candles the strategy requires before producing valid signals
    startup_candle_count: int = 250
    
    # Strategy parameters (can be optimized)
    # Regime Filter
    regime_htf_timeframe = config.REGIME_HTF_TIMEFRAME
    regime_ema_fast = config.REGIME_EMA_FAST
    regime_ema_slow = config.REGIME_EMA_SLOW
    regime_adx_threshold = config.REGIME_ADX_THRESHOLD
    regime_adx_period = config.REGIME_ADX_PERIOD
    
    # Entry Signals
    entry_ema_period = config.ENTRY_EMA_PERIOD
    entry_rsi_period = config.ENTRY_RSI_PERIOD
    entry_rsi_long_threshold = config.ENTRY_RSI_LONG_THRESHOLD
    entry_rsi_short_threshold = config.ENTRY_RSI_SHORT_THRESHOLD
    
    # Filters
    filter_atr_period = config.FILTER_ATR_PERIOD
    filter_atr_min_threshold = config.FILTER_ATR_MIN_THRESHOLD
    filter_volume_period = config.FILTER_VOLUME_PERIOD
    entry_volume_multiplier = config.ENTRY_VOLUME_MULTIPLIER
    
    # Position sizing
    position_adjustment_enable = True
    max_entry_position_adjustment = 0  # No DCA/averaging
    
    def __init__(self, config_dict: dict):
        super().__init__(config_dict)
        
        # Initialize signal filters and risk engine
        self.signal_filters = SignalFilters(
            atr_period=self.filter_atr_period,
            atr_min_threshold=self.filter_atr_min_threshold,
            volume_period=self.filter_volume_period,
            volume_multiplier=self.entry_volume_multiplier
        )
        
        self.risk_engine = RiskEngine(
            max_risk_per_trade=config.MAX_RISK_PER_TRADE,
            max_daily_drawdown=config.MAX_DAILY_DRAWDOWN,
            max_consecutive_losses=config.MAX_CONSECUTIVE_LOSSES,
            cooldown_minutes=config.COOLDOWN_MINUTES,
            stop_loss_atr_multiplier=config.STOP_LOSS_ATR_MULTIPLIER,
            stop_loss_max_percent=config.STOP_LOSS_MAX_PERCENT,
            take_profit_r_levels=config.TAKE_PROFIT_R_LEVELS,
            breakeven_after_first_tp=config.BREAKEVEN_AFTER_FIRST_TP
        )
    
    @informative('1h')
    def populate_indicators_1h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
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
            (dataframe['regime_bullish_1h'] == True),
            
            # Price pulled back to EMA/VWAP zone
            (dataframe['close'] <= dataframe['ema'] * 1.01),  # Within 1% of EMA
            
            # RSI recovery
            (dataframe['rsi'] > self.entry_rsi_long_threshold),
            (dataframe['rsi'].shift(1) <= self.entry_rsi_long_threshold),  # Cross above
            
            # Filters passed
            (dataframe['filters_passed'] == True),
            
            # Volume condition
            (dataframe['volume'] > 0)
        ]
        
        # Short Entry Conditions
        short_conditions = [
            # HTF regime is bearish
            (dataframe['regime_bearish_1h'] == True),
            
            # Price bounced to resistance/EMA zone
            (dataframe['close'] >= dataframe['ema'] * 0.99),  # Within 1% of EMA
            
            # RSI rollover
            (dataframe['rsi'] < self.entry_rsi_short_threshold),
            (dataframe['rsi'].shift(1) >= self.entry_rsi_short_threshold),  # Cross below
            
            # Filters passed
            (dataframe['filters_passed'] == True),
            
            # Volume condition
            (dataframe['volume'] > 0)
        ]
        
        # Combine conditions
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
        # Exit long when regime flips bearish
        dataframe.loc[
            (dataframe['regime_bearish_1h'] == True),
            'exit_long'
        ] = 1
        
        # Exit short when regime flips bullish
        dataframe.loc[
            (dataframe['regime_bullish_1h'] == True),
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
        Custom stoploss logic using ATR.
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        
        if len(dataframe) == 0:
            return None
        
        current_candle = dataframe.iloc[-1]
        
        if 'atr' not in current_candle or pd.isna(current_candle['atr']):
            return None
        
        # Calculate dynamic stop
        side = 'long' if trade.is_short is False else 'short'
        stop_loss_price = self.risk_engine.calculate_stop_loss(
            entry_price=trade.open_rate,
            atr=current_candle['atr'],
            side=side
        )
        
        # Convert to stop loss ratio
        if side == 'long':
            stop_loss_ratio = (stop_loss_price / trade.open_rate) - 1
        else:
            stop_loss_ratio = 1 - (stop_loss_price / trade.open_rate)
        
        return stop_loss_ratio
    
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
        Custom exit logic for partial take profits.
        This is a simplified version - full implementation would track partials.
        """
        # Check if daily drawdown limit reached
        # Note: In production, you'd get actual equity from exchange
        # For backtesting, this is approximate
        
        # Exit at first TP level (simplified)
        if current_profit >= 0.01:  # 1% profit (1R approximate)
            return 'take_profit_1'
        
        return None
    
    def confirm_trade_entry(
        self,
        pair: str,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        current_time: 'datetime',
        entry_tag: Optional[str],
        side: str,
        **kwargs
    ) -> bool:
        """
        Confirm trade entry with risk engine checks.
        """
        # Check if trading is allowed (daily drawdown, cooldown, etc.)
        # Note: In backtesting, equity tracking is approximate
        can_trade, reason = self.risk_engine.can_trade(equity=10000.0)
        
        if not can_trade:
            return False
        
        return True
    
    def leverage(
        self,
        pair: str,
        current_time: 'datetime',
        current_rate: float,
        proposed_leverage: float,
        max_leverage: float,
        entry_tag: Optional[str],
        side: str,
        **kwargs
    ) -> float:
        """
        Set leverage for futures trading.
        Conservative 3x leverage for scalping.
        """
        return 3.0
