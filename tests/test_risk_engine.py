"""
Tests for risk engine module.
"""
import pytest
from datetime import datetime, timedelta

from bot.strategy.risk_engine import RiskEngine


def test_risk_engine_initialization():
    """Test RiskEngine initialization with default parameters."""
    engine = RiskEngine()
    
    assert engine.max_risk_per_trade == 0.005
    assert engine.max_daily_drawdown == 0.025
    assert engine.max_consecutive_losses == 3
    assert engine.cooldown_minutes == 30
    assert engine.consecutive_losses == 0
    assert engine.cooldown_until is None


def test_calculate_position_size_long():
    """Test position size calculation for long positions."""
    engine = RiskEngine(max_risk_per_trade=0.01)
    
    equity = 10000.0
    entry_price = 40000.0
    stop_loss_price = 39500.0  # 500 USD risk per unit
    
    position_size = engine.calculate_position_size(
        equity=equity,
        entry_price=entry_price,
        stop_loss_price=stop_loss_price,
        side='long'
    )
    
    # Expected: risk $100 (1% of $10k), risk per unit is $500
    # Position size should be 100 / 500 = 0.2 BTC
    assert position_size == pytest.approx(0.2, rel=0.01)


def test_calculate_position_size_short():
    """Test position size calculation for short positions."""
    engine = RiskEngine(max_risk_per_trade=0.01)
    
    equity = 10000.0
    entry_price = 40000.0
    stop_loss_price = 40500.0  # 500 USD risk per unit
    
    position_size = engine.calculate_position_size(
        equity=equity,
        entry_price=entry_price,
        stop_loss_price=stop_loss_price,
        side='short'
    )
    
    assert position_size == pytest.approx(0.2, rel=0.01)


def test_calculate_stop_loss_long():
    """Test stop loss calculation for long position."""
    engine = RiskEngine(
        stop_loss_atr_multiplier=1.5,
        stop_loss_max_percent=0.02
    )
    
    entry_price = 40000.0
    atr = 200.0
    
    stop_loss = engine.calculate_stop_loss(
        entry_price=entry_price,
        atr=atr,
        side='long'
    )
    
    # ATR-based: 40000 - (200 * 1.5) = 39700
    # Max-based: 40000 - (40000 * 0.02) = 39200
    # Should use tighter (ATR-based)
    assert stop_loss == pytest.approx(39700, rel=0.01)


def test_calculate_stop_loss_short():
    """Test stop loss calculation for short position."""
    engine = RiskEngine(
        stop_loss_atr_multiplier=1.5,
        stop_loss_max_percent=0.02
    )
    
    entry_price = 40000.0
    atr = 200.0
    
    stop_loss = engine.calculate_stop_loss(
        entry_price=entry_price,
        atr=atr,
        side='short'
    )
    
    # ATR-based: 40000 + (200 * 1.5) = 40300
    # Max-based: 40000 + (40000 * 0.02) = 40800
    # Should use tighter (ATR-based)
    assert stop_loss == pytest.approx(40300, rel=0.01)


def test_calculate_take_profit_levels_long():
    """Test take profit level calculation for long position."""
    engine = RiskEngine(take_profit_r_levels=[1.0, 1.5, 2.0])
    
    entry_price = 40000.0
    stop_loss_price = 39600.0  # 400 USD risk (1R)
    
    tp_levels = engine.calculate_take_profit_levels(
        entry_price=entry_price,
        stop_loss_price=stop_loss_price,
        side='long'
    )
    
    assert 'tp1' in tp_levels
    assert 'tp2' in tp_levels
    assert 'tp3' in tp_levels
    
    # TP1 at 1R: 40000 + 400 = 40400
    assert tp_levels['tp1'] == pytest.approx(40400, rel=0.01)
    # TP2 at 1.5R: 40000 + 600 = 40600
    assert tp_levels['tp2'] == pytest.approx(40600, rel=0.01)
    # TP3 at 2R: 40000 + 800 = 40800
    assert tp_levels['tp3'] == pytest.approx(40800, rel=0.01)


def test_calculate_take_profit_levels_short():
    """Test take profit level calculation for short position."""
    engine = RiskEngine(take_profit_r_levels=[1.0, 1.5, 2.0])
    
    entry_price = 40000.0
    stop_loss_price = 40400.0  # 400 USD risk (1R)
    
    tp_levels = engine.calculate_take_profit_levels(
        entry_price=entry_price,
        stop_loss_price=stop_loss_price,
        side='short'
    )
    
    # TP1 at 1R: 40000 - 400 = 39600
    assert tp_levels['tp1'] == pytest.approx(39600, rel=0.01)


def test_check_daily_drawdown():
    """Test daily drawdown check."""
    engine = RiskEngine(max_daily_drawdown=0.025)  # 2.5%
    
    # First check should reset tracking
    result = engine.check_daily_drawdown(equity=10000.0)
    assert result is False  # Not exceeded
    assert engine.daily_start_equity == 10000.0
    
    # Check with 3% drawdown (should exceed limit)
    result = engine.check_daily_drawdown(equity=9700.0)
    assert result is True  # Exceeded
    
    # Check with 1% drawdown (should not exceed)
    engine.reset_state()
    engine.check_daily_drawdown(equity=10000.0)
    result = engine.check_daily_drawdown(equity=9900.0)
    assert result is False


def test_consecutive_losses_cooldown():
    """Test consecutive loss tracking and cooldown trigger."""
    engine = RiskEngine(
        max_consecutive_losses=3,
        cooldown_minutes=30
    )
    
    # Record 2 losses - should not trigger cooldown
    engine.record_trade_result(won=False, pnl=-100)
    engine.record_trade_result(won=False, pnl=-100)
    assert engine.consecutive_losses == 2
    assert engine.cooldown_until is None
    
    # Record 3rd loss - should trigger cooldown
    engine.record_trade_result(won=False, pnl=-100)
    assert engine.consecutive_losses == 3
    assert engine.cooldown_until is not None
    
    # Check cooldown is active
    assert engine.check_cooldown() is True


def test_consecutive_losses_reset_on_win():
    """Test that consecutive losses reset on winning trade."""
    engine = RiskEngine(max_consecutive_losses=3)
    
    # Record 2 losses
    engine.record_trade_result(won=False, pnl=-100)
    engine.record_trade_result(won=False, pnl=-100)
    assert engine.consecutive_losses == 2
    
    # Record a win - should reset
    engine.record_trade_result(won=True, pnl=150)
    assert engine.consecutive_losses == 0


def test_can_trade():
    """Test can_trade safety check."""
    engine = RiskEngine(
        max_daily_drawdown=0.025,
        max_consecutive_losses=3
    )
    
    # Should allow trading initially
    can_trade, reason = engine.can_trade(equity=10000.0)
    assert can_trade is True
    assert "passed" in reason.lower()
    
    # Trigger daily drawdown
    engine.daily_start_equity = 10000.0
    engine.last_reset_date = datetime.now().date()
    can_trade, reason = engine.can_trade(equity=9700.0)
    assert can_trade is False
    assert "drawdown" in reason.lower()


def test_should_move_to_breakeven():
    """Test breakeven logic."""
    engine = RiskEngine(breakeven_after_first_tp=True)
    
    # Should not move if first TP not hit
    result = engine.should_move_to_breakeven(
        current_price=40500.0,
        entry_price=40000.0,
        first_tp_hit=False,
        side='long'
    )
    assert result is False
    
    # Should move if first TP hit
    result = engine.should_move_to_breakeven(
        current_price=40500.0,
        entry_price=40000.0,
        first_tp_hit=True,
        side='long'
    )
    assert result is True


def test_reset_state():
    """Test state reset."""
    engine = RiskEngine()
    
    # Set some state
    engine.consecutive_losses = 5
    engine.cooldown_until = datetime.now() + timedelta(minutes=30)
    engine.daily_pnl = -500.0
    
    # Reset
    engine.reset_state()
    
    assert engine.consecutive_losses == 0
    assert engine.cooldown_until is None
    assert engine.daily_pnl == 0.0
