"""
Risk management engine for the trading bot.
Handles position sizing, stop loss, take profit, and safety mechanisms.
"""
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta
import numpy as np


class RiskEngine:
    """Risk management and position sizing logic."""
    
    def __init__(
        self,
        max_risk_per_trade: float = 0.005,
        max_daily_drawdown: float = 0.025,
        max_consecutive_losses: int = 3,
        cooldown_minutes: int = 30,
        stop_loss_atr_multiplier: float = 1.5,
        stop_loss_max_percent: float = 0.02,
        take_profit_r_levels: list = None,
        breakeven_after_first_tp: bool = True
    ):
        """
        Initialize risk engine.
        
        Args:
            max_risk_per_trade: Maximum risk per trade as fraction of equity
            max_daily_drawdown: Maximum daily drawdown as fraction of equity
            max_consecutive_losses: Max consecutive losses before cooldown
            cooldown_minutes: Cooldown period in minutes
            stop_loss_atr_multiplier: ATR multiplier for stop loss
            stop_loss_max_percent: Hard maximum stop loss percentage
            take_profit_r_levels: List of R multiples for partial take profits
            breakeven_after_first_tp: Move stop to breakeven after first TP
        """
        self.max_risk_per_trade = max_risk_per_trade
        self.max_daily_drawdown = max_daily_drawdown
        self.max_consecutive_losses = max_consecutive_losses
        self.cooldown_minutes = cooldown_minutes
        self.stop_loss_atr_multiplier = stop_loss_atr_multiplier
        self.stop_loss_max_percent = stop_loss_max_percent
        self.take_profit_r_levels = take_profit_r_levels or [1.0, 1.5, 2.0]
        self.breakeven_after_first_tp = breakeven_after_first_tp
        
        # State tracking
        self.consecutive_losses = 0
        self.cooldown_until: Optional[datetime] = None
        self.daily_pnl = 0.0
        self.daily_start_equity = 0.0
        self.last_reset_date: Optional[datetime] = None
    
    def calculate_position_size(
        self,
        equity: float,
        entry_price: float,
        stop_loss_price: float,
        side: str = "long"
    ) -> float:
        """
        Calculate position size based on risk parameters.
        
        Args:
            equity: Current account equity
            entry_price: Planned entry price
            stop_loss_price: Planned stop loss price
            side: Trade side ('long' or 'short')
            
        Returns:
            Position size in base currency units
        """
        # Calculate risk per unit
        if side.lower() == "long":
            risk_per_unit = entry_price - stop_loss_price
        else:  # short
            risk_per_unit = stop_loss_price - entry_price
        
        if risk_per_unit <= 0:
            return 0.0
        
        # Calculate position size to risk max_risk_per_trade
        dollar_risk = equity * self.max_risk_per_trade
        position_size = dollar_risk / risk_per_unit
        
        return position_size
    
    def calculate_stop_loss(
        self,
        entry_price: float,
        atr: float,
        side: str = "long"
    ) -> float:
        """
        Calculate stop loss price using ATR and hard maximum.
        
        Args:
            entry_price: Entry price
            atr: Current ATR value
            side: Trade side ('long' or 'short')
            
        Returns:
            Stop loss price
        """
        # ATR-based stop
        atr_stop_distance = atr * self.stop_loss_atr_multiplier
        
        # Hard maximum stop
        max_stop_distance = entry_price * self.stop_loss_max_percent
        
        # Use the tighter of the two
        stop_distance = min(atr_stop_distance, max_stop_distance)
        
        if side.lower() == "long":
            stop_loss = entry_price - stop_distance
        else:  # short
            stop_loss = entry_price + stop_distance
        
        return stop_loss
    
    def calculate_take_profit_levels(
        self,
        entry_price: float,
        stop_loss_price: float,
        side: str = "long"
    ) -> Dict[str, float]:
        """
        Calculate take profit levels based on R multiples.
        
        Args:
            entry_price: Entry price
            stop_loss_price: Stop loss price
            side: Trade side ('long' or 'short')
            
        Returns:
            Dictionary of TP level names to prices
        """
        # Calculate R (risk) distance
        if side.lower() == "long":
            r_distance = entry_price - stop_loss_price
        else:  # short
            r_distance = stop_loss_price - entry_price
        
        take_profits = {}
        
        for i, r_multiple in enumerate(self.take_profit_r_levels, 1):
            if side.lower() == "long":
                tp_price = entry_price + (r_distance * r_multiple)
            else:  # short
                tp_price = entry_price - (r_distance * r_multiple)
            
            take_profits[f"tp{i}"] = tp_price
        
        return take_profits
    
    def should_move_to_breakeven(
        self,
        current_price: float,
        entry_price: float,
        first_tp_hit: bool,
        side: str = "long"
    ) -> bool:
        """
        Determine if stop should be moved to breakeven.
        
        Args:
            current_price: Current market price
            entry_price: Entry price
            first_tp_hit: Whether first TP has been hit
            side: Trade side
            
        Returns:
            True if stop should be moved to breakeven
        """
        if not self.breakeven_after_first_tp:
            return False
        
        if not first_tp_hit:
            return False
        
        return True
    
    def check_daily_drawdown(self, equity: float) -> bool:
        """
        Check if daily drawdown limit has been reached.
        
        Args:
            equity: Current equity
            
        Returns:
            True if trading should stop due to daily drawdown
        """
        # Reset daily tracking at new day
        today = datetime.now().date()
        if self.last_reset_date is None or self.last_reset_date != today:
            self.daily_pnl = 0.0
            self.daily_start_equity = equity
            self.last_reset_date = today
            return False
        
        # Calculate current daily drawdown
        daily_return = (equity - self.daily_start_equity) / self.daily_start_equity
        
        if daily_return < -self.max_daily_drawdown:
            return True
        
        return False
    
    def check_cooldown(self) -> bool:
        """
        Check if bot is in cooldown period.
        
        Returns:
            True if in cooldown period
        """
        if self.cooldown_until is None:
            return False
        
        return datetime.now() < self.cooldown_until
    
    def record_trade_result(self, won: bool, pnl: float):
        """
        Record trade result and update state.
        
        Args:
            won: Whether trade was a winner
            pnl: Profit/loss of the trade
        """
        self.daily_pnl += pnl
        
        if won:
            self.consecutive_losses = 0
        else:
            self.consecutive_losses += 1
            
            # Trigger cooldown if max consecutive losses reached
            if self.consecutive_losses >= self.max_consecutive_losses:
                self.cooldown_until = datetime.now() + timedelta(
                    minutes=self.cooldown_minutes
                )
    
    def can_trade(self, equity: float) -> Tuple[bool, str]:
        """
        Check all safety mechanisms to determine if trading is allowed.
        
        Args:
            equity: Current equity
            
        Returns:
            Tuple of (can_trade, reason)
        """
        # Check daily drawdown
        if self.check_daily_drawdown(equity):
            return False, "Daily drawdown limit reached"
        
        # Check cooldown
        if self.check_cooldown():
            remaining = (self.cooldown_until - datetime.now()).seconds // 60
            return False, f"In cooldown period ({remaining} minutes remaining)"
        
        return True, "All checks passed"
    
    def reset_state(self):
        """Reset risk engine state (for testing or new trading day)."""
        self.consecutive_losses = 0
        self.cooldown_until = None
        self.daily_pnl = 0.0
