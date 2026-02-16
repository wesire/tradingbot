"""
Signal filters for the BTC scalping strategy.
Implements volatility, volume, and mean-reversion filters.
"""
from typing import Tuple
import pandas as pd
import numpy as np
from pandas import DataFrame


class SignalFilters:
    """Signal filtering logic to refine entry conditions."""
    
    def __init__(
        self,
        atr_period: int = 14,
        atr_min_threshold: float = 0.0005,
        volume_period: int = 20,
        volume_multiplier: float = 1.5
    ):
        """
        Initialize signal filters.
        
        Args:
            atr_period: Period for ATR calculation
            atr_min_threshold: Minimum ATR value to avoid dead markets
            volume_period: Period for volume moving average
            volume_multiplier: Multiplier for relative volume spike detection
        """
        self.atr_period = atr_period
        self.atr_min_threshold = atr_min_threshold
        self.volume_period = volume_period
        self.volume_multiplier = volume_multiplier
    
    def calculate_atr(self, dataframe: DataFrame) -> DataFrame:
        """
        Calculate Average True Range (ATR).
        
        Args:
            dataframe: OHLCV dataframe
            
        Returns:
            Dataframe with ATR column added
        """
        df = dataframe.copy()
        
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['atr'] = true_range.rolling(window=self.atr_period).mean()
        
        return df
    
    def volatility_filter(self, dataframe: DataFrame) -> DataFrame:
        """
        Apply volatility filter to avoid dead/choppy markets.
        
        Args:
            dataframe: OHLCV dataframe with ATR
            
        Returns:
            Dataframe with volatility_ok column
        """
        df = dataframe.copy()
        
        if 'atr' not in df.columns:
            df = self.calculate_atr(df)
        
        # Normalize ATR by price to make threshold meaningful across price ranges
        df['atr_pct'] = df['atr'] / df['close']
        df['volatility_ok'] = df['atr_pct'] > self.atr_min_threshold
        
        return df
    
    def calculate_relative_volume(self, dataframe: DataFrame) -> DataFrame:
        """
        Calculate relative volume compared to moving average.
        
        Args:
            dataframe: OHLCV dataframe
            
        Returns:
            Dataframe with relative volume columns
        """
        df = dataframe.copy()
        
        df['volume_ma'] = df['volume'].rolling(window=self.volume_period).mean()
        df['volume_ratio'] = df['volume'] / df['volume_ma']
        
        return df
    
    def volume_filter(self, dataframe: DataFrame) -> DataFrame:
        """
        Apply volume filter to detect volume spikes.
        
        Args:
            dataframe: OHLCV dataframe
            
        Returns:
            Dataframe with volume_spike column
        """
        df = dataframe.copy()
        
        if 'volume_ratio' not in df.columns:
            df = self.calculate_relative_volume(df)
        
        df['volume_spike'] = df['volume_ratio'] > self.volume_multiplier
        
        return df
    
    def mean_reversion_signal(
        self,
        dataframe: DataFrame,
        bb_period: int = 20,
        bb_std: float = 2.0,
        rsi_period: int = 14,
        rsi_oversold: int = 30,
        rsi_overbought: int = 70
    ) -> DataFrame:
        """
        Generate mean-reversion signals for neutral regime.
        Uses Bollinger Bands + RSI for micro-entries.
        
        Args:
            dataframe: OHLCV dataframe
            bb_period: Bollinger Bands period
            bb_std: Bollinger Bands standard deviation
            rsi_period: RSI period
            rsi_oversold: RSI oversold threshold
            rsi_overbought: RSI overbought threshold
            
        Returns:
            Dataframe with mean reversion signals
        """
        df = dataframe.copy()
        
        # Bollinger Bands
        df['bb_middle'] = df['close'].rolling(window=bb_period).mean()
        df['bb_std'] = df['close'].rolling(window=bb_period).std()
        df['bb_upper'] = df['bb_middle'] + (bb_std * df['bb_std'])
        df['bb_lower'] = df['bb_middle'] - (bb_std * df['bb_std'])
        
        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=rsi_period).mean()
        rs = gain / loss
        df['rsi_mr'] = 100 - (100 / (1 + rs))
        
        # Mean reversion long: price touches lower BB and RSI oversold
        df['mr_long'] = (
            (df['close'] <= df['bb_lower']) &
            (df['rsi_mr'] < rsi_oversold)
        )
        
        # Mean reversion short: price touches upper BB and RSI overbought
        df['mr_short'] = (
            (df['close'] >= df['bb_upper']) &
            (df['rsi_mr'] > rsi_overbought)
        )
        
        return df
    
    def apply_all_filters(
        self,
        dataframe: DataFrame,
        enable_mean_reversion: bool = False
    ) -> DataFrame:
        """
        Apply all signal filters to dataframe.
        
        Args:
            dataframe: OHLCV dataframe
            enable_mean_reversion: Whether to calculate mean reversion signals
            
        Returns:
            Dataframe with all filter columns
        """
        df = dataframe.copy()
        
        # Apply filters
        df = self.volatility_filter(df)
        df = self.volume_filter(df)
        
        if enable_mean_reversion:
            df = self.mean_reversion_signal(df)
        
        # Combined filter: all conditions must be true
        df['filters_passed'] = (
            df['volatility_ok'] &
            df['volume_spike']
        )
        
        return df
