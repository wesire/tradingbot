"""
SOL/USDT Perpetual Futures Momentum Strategy for Freqtrade.
Tuned for strong momentum with stricter RSI/volume filters.
"""
from typing import Optional
import pandas as pd
from pandas import DataFrame
from freqtrade.strategy import IStrategy, informative
import talib.abstract as ta

from bot.strategy.signal_filters import SignalFilters
from bot.strategy.risk_engine import RiskEngine
from bot.config.default_config import config as app_config


class SOLMomentumStrategy(IStrategy):
    """
    SOL/USDT momentum strategy with strict filters for high-quality setups.

    Strategy Logic:
    1. Regime Filter (HTF): EMA crossover + ADX for trend direction/strength
    2. Entry Signals (LTF): Strong momentum entries with multiple confirmations
    3. Filters: Volatility (ATR) and strong volume spike detection
    4. Risk Management: Tighter stops, trailing enabled, partial TPs
    
    Differences from BTC/ETH strategies:
    - Higher ADX threshold (28 vs 25) - only trade strong trends
    - More conservative RSI entries (45/55 vs 40/60)
    - Stronger volume confirmation (1.5x vs 1.2x)
    - Additional MACD confirmation required
    - Tighter stops (1.8 ATR vs 2.0) for momentum protection
    - Trailing stop enabled for momentum rides
    - Max ATR threshold to avoid extreme volatility
    """

    # Strategy metadata
    INTERFACE_VERSION = 3

    # Enable shorts (futures)
    can_short = True

    # Minimal ROI - handled by custom exit logic
    minimal_roi = {
        "0": 0.12,  # Higher targets for momentum
        "30": 0.06,
        "60": 0.03,
        "120": 0.015
    }

    # Stoploss
    stoploss = -0.022  # Tighter for momentum

    # Trailing stop (enabled for SOL momentum)
    trailing_stop = True
    trailing_stop_positive = 0.015
    trailing_stop_positive_offset = 0.025
    trailing_only_offset_is_reached = True

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
    regime_adx_threshold = 28  # Higher for SOL - only strong trends
    regime_adx_period = 14

    # Entry Signals - TODO: calibrate via hyperopt/backtest
    entry_ema_period = 21
    entry_rsi_period = 14
    entry_rsi_long_threshold = 45  # More conservative
    entry_rsi_short_threshold = 55  # More conservative

    # Filters - TODO: calibrate via hyperopt/backtest
    filter_atr_period = 14
    filter_atr_min_threshold = 0.002  # Higher minimum for SOL
    filter_atr_max_threshold = 0.015  # Avoid extreme volatility
    filter_volume_period = 20
    entry_volume_multiplier = 1.5  # Strong volume requirement for momentum

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
            stop_loss_atr_multiplier=1.8,  # Tighter for momentum
            stop_loss_max_percent=0.022,
            take_profit_r_levels=[1.5, 2.5, 4.5],  # Larger R:R for momentum
            breakeven_after_first_tp=True
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

        # Regime determination (stricter for SOL)
        dataframe['regime_bullish'] = (
            (dataframe['ema_fast'] > dataframe['ema_slow']) &
            (dataframe['adx'] > self.regime_adx_threshold) &
            (dataframe['ema_fast'] > dataframe['ema_fast'].shift(1))  # Momentum check
        )

        dataframe['regime_bearish'] = (
            (dataframe['ema_fast'] < dataframe['ema_slow']) &
            (dataframe['adx'] > self.regime_adx_threshold) &
            (dataframe['ema_fast'] < dataframe['ema_fast'].shift(1))  # Momentum check
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
        dataframe['ema_fast'] = ta.EMA(dataframe, timeperiod=9)  # Faster EMA for momentum

        # VWAP (approximation using cumulative)
        dataframe['vwap'] = (
            (dataframe['close'] * dataframe['volume']).cumsum() /
            dataframe['volume'].cumsum()
        )

        # RSI for entry triggers
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=self.entry_rsi_period)

        # MACD for momentum confirmation (required for SOL)
        macd = ta.MACD(dataframe)
        dataframe['macd'] = macd['macd']
        dataframe['macd_signal'] = macd['macdsignal']
        dataframe['macd_hist'] = macd['macdhist']

        # Stochastic for momentum confirmation
        stoch = ta.STOCH(dataframe)
        dataframe['stoch_k'] = stoch['slowk']
        dataframe['stoch_d'] = stoch['slowd']

        # Apply signal filters (ATR, volume)
        dataframe = self.signal_filters.apply_all_filters(
            dataframe,
            enable_mean_reversion=False  # Momentum strategy, not mean reversion
        )

        # Additional ATR max filter for SOL
        dataframe['atr_ok'] = dataframe['atr'] < self.filter_atr_max_threshold

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Populate buy/sell signals based on regime and entry conditions.
        """
        # Long Entry Conditions (strict momentum)
        long_conditions = [
            # HTF regime is strongly bullish
            (dataframe['regime_bullish_15m'] == True),

            # Price above fast EMA (momentum)
            (dataframe['close'] > dataframe['ema_fast']),
            (dataframe['ema_fast'] > dataframe['ema']),

            # RSI in momentum zone
            (dataframe['rsi'] > self.entry_rsi_long_threshold),
            (dataframe['rsi'] < 70),  # Not overbought

            # MACD momentum confirmation
            (dataframe['macd'] > dataframe['macd_signal']),
            (dataframe['macd_hist'] > 0),
            (dataframe['macd_hist'] > dataframe['macd_hist'].shift(1)),  # Increasing histogram

            # Stochastic confirmation
            (dataframe['stoch_k'] > dataframe['stoch_d']),
            (dataframe['stoch_k'] > 20),  # Not oversold

            # Filters passed
            (dataframe['filters_passed'] == True),
            (dataframe['atr_ok'] == True),

            # Volume condition
            (dataframe['volume'] > 0)
        ]

        # Short Entry Conditions (strict momentum)
        short_conditions = [
            # HTF regime is strongly bearish
            (dataframe['regime_bearish_15m'] == True),

            # Price below fast EMA (momentum)
            (dataframe['close'] < dataframe['ema_fast']),
            (dataframe['ema_fast'] < dataframe['ema']),

            # RSI in momentum zone
            (dataframe['rsi'] < self.entry_rsi_short_threshold),
            (dataframe['rsi'] > 30),  # Not oversold

            # MACD momentum confirmation
            (dataframe['macd'] < dataframe['macd_signal']),
            (dataframe['macd_hist'] < 0),
            (dataframe['macd_hist'] < dataframe['macd_hist'].shift(1)),  # Decreasing histogram

            # Stochastic confirmation
            (dataframe['stoch_k'] < dataframe['stoch_d']),
            (dataframe['stoch_k'] < 80),  # Not overbought

            # Filters passed
            (dataframe['filters_passed'] == True),
            (dataframe['atr_ok'] == True),

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

        # Exit long when momentum weakens
        dataframe.loc[
            (
                (dataframe['regime_bearish_15m'] == True) |
                (dataframe['macd'] < dataframe['macd_signal']) |
                (dataframe['stoch_k'] < dataframe['stoch_d'])
            ),
            'exit_long'
        ] = 1

        # Exit short when momentum weakens
        dataframe.loc[
            (
                (dataframe['regime_bullish_15m'] == True) |
                (dataframe['macd'] > dataframe['macd_signal']) |
                (dataframe['stoch_k'] > dataframe['stoch_d'])
            ),
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
        Custom stoploss logic using ATR-based dynamic stops with trailing.
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
