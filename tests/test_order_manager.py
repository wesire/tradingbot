"""
Tests for order manager module.
"""
import pytest
from unittest.mock import Mock, MagicMock

from bot.execution.order_manager import (
    OrderManager,
    Order,
    OrderStatus,
    OrderType,
    Position
)


def test_order_creation():
    """Test Order object creation."""
    order = Order(
        symbol='BTC/USDT',
        side='buy',
        order_type=OrderType.LIMIT,
        amount=0.1,
        price=40000.0
    )
    
    assert order.symbol == 'BTC/USDT'
    assert order.side == 'buy'
    assert order.order_type == OrderType.LIMIT
    assert order.amount == 0.1
    assert order.price == 40000.0
    assert order.status == OrderStatus.PENDING
    assert order.filled_amount == 0.0


def test_order_update_fill():
    """Test order fill update."""
    order = Order(
        symbol='BTC/USDT',
        side='buy',
        order_type=OrderType.LIMIT,
        amount=0.1,
        price=40000.0
    )
    
    # Partial fill
    order.update_fill(filled_amount=0.05, fill_price=40000.0)
    
    assert order.filled_amount == 0.05
    assert order.average_fill_price == 40000.0
    assert order.status == OrderStatus.PARTIAL
    
    # Complete fill
    order.update_fill(filled_amount=0.05, fill_price=40010.0)
    
    assert order.filled_amount == 0.1
    assert order.status == OrderStatus.FILLED
    # Average price should be (0.05 * 40000 + 0.05 * 40010) / 0.1 = 40005
    assert order.average_fill_price == pytest.approx(40005, rel=0.01)


def test_position_creation():
    """Test Position object creation."""
    entry_order = Order(
        symbol='BTC/USDT',
        side='buy',
        order_type=OrderType.LIMIT,
        amount=0.1,
        price=40000.0
    )
    entry_order.status = OrderStatus.FILLED
    entry_order.update_fill(0.1, 40000.0)
    
    position = Position(
        symbol='BTC/USDT',
        side='long',
        entry_order=entry_order
    )
    
    assert position.symbol == 'BTC/USDT'
    assert position.side == 'long'
    assert position.entry_order == entry_order
    assert position.is_open() is True


def test_position_unrealized_pnl_long():
    """Test unrealized PnL calculation for long position."""
    entry_order = Order(
        symbol='BTC/USDT',
        side='buy',
        order_type=OrderType.MARKET,
        amount=0.1
    )
    entry_order.update_fill(0.1, 40000.0)
    
    position = Position(
        symbol='BTC/USDT',
        side='long',
        entry_order=entry_order
    )
    
    # Price up 5%
    pnl = position.unrealized_pnl(current_price=42000.0)
    # PnL = (42000 - 40000) * 0.1 = 200
    assert pnl == pytest.approx(200.0, rel=0.01)
    
    # Price down 5%
    pnl = position.unrealized_pnl(current_price=38000.0)
    # PnL = (38000 - 40000) * 0.1 = -200
    assert pnl == pytest.approx(-200.0, rel=0.01)


def test_position_unrealized_pnl_short():
    """Test unrealized PnL calculation for short position."""
    entry_order = Order(
        symbol='BTC/USDT',
        side='sell',
        order_type=OrderType.MARKET,
        amount=0.1
    )
    entry_order.update_fill(0.1, 40000.0)
    
    position = Position(
        symbol='BTC/USDT',
        side='short',
        entry_order=entry_order
    )
    
    # Price down 5% (profit for short)
    pnl = position.unrealized_pnl(current_price=38000.0)
    # PnL = (40000 - 38000) * 0.1 = 200
    assert pnl == pytest.approx(200.0, rel=0.01)
    
    # Price up 5% (loss for short)
    pnl = position.unrealized_pnl(current_price=42000.0)
    # PnL = (40000 - 42000) * 0.1 = -200
    assert pnl == pytest.approx(-200.0, rel=0.01)


def test_order_manager_create_entry_order(mock_broker_adapter):
    """Test creating entry order."""
    manager = OrderManager(mock_broker_adapter)
    
    order = manager.create_entry_order(
        symbol='BTC/USDT',
        side='long',
        amount=0.1,
        order_type=OrderType.LIMIT,
        price=40000.0
    )
    
    assert order.symbol == 'BTC/USDT'
    assert order.side == 'buy'  # Converted from 'long'
    assert order.amount == 0.1
    assert order.status == OrderStatus.OPEN
    assert order.id in manager.orders
    
    # Should have created a position
    assert len(manager.positions) == 1


def test_order_manager_create_stop_loss(mock_broker_adapter):
    """Test creating stop loss order."""
    manager = OrderManager(mock_broker_adapter)
    
    # Create entry order first
    entry_order = manager.create_entry_order(
        symbol='BTC/USDT',
        side='long',
        amount=0.1,
        order_type=OrderType.LIMIT,
        price=40000.0
    )
    
    # Get position ID
    position_id = list(manager.positions.keys())[0]
    
    # Create stop loss
    stop_order = manager.create_stop_loss(
        position_id=position_id,
        stop_price=39500.0,
        amount=0.1
    )
    
    assert stop_order.order_type == OrderType.STOP_LOSS
    assert stop_order.stop_price == 39500.0
    assert stop_order.status == OrderStatus.OPEN


def test_order_manager_create_take_profit(mock_broker_adapter):
    """Test creating take profit order."""
    manager = OrderManager(mock_broker_adapter)
    
    # Create entry order first
    entry_order = manager.create_entry_order(
        symbol='BTC/USDT',
        side='long',
        amount=0.1,
        order_type=OrderType.LIMIT,
        price=40000.0
    )
    
    position_id = list(manager.positions.keys())[0]
    
    # Create take profit
    tp_order = manager.create_take_profit(
        position_id=position_id,
        tp_price=41000.0,
        amount=0.05
    )
    
    assert tp_order.order_type == OrderType.TAKE_PROFIT
    assert tp_order.price == 41000.0
    assert tp_order.status == OrderStatus.OPEN


def test_order_manager_move_stop_to_breakeven(mock_broker_adapter):
    """Test moving stop loss to breakeven."""
    manager = OrderManager(mock_broker_adapter)
    
    # Create entry and stop loss
    entry_order = manager.create_entry_order(
        symbol='BTC/USDT',
        side='long',
        amount=0.1,
        price=40000.0
    )
    
    position_id = list(manager.positions.keys())[0]
    position = manager.positions[position_id]
    position.entry_order.update_fill(0.1, 40000.0)
    
    manager.create_stop_loss(
        position_id=position_id,
        stop_price=39500.0,
        amount=0.1
    )
    
    # Move to breakeven
    result = manager.move_stop_to_breakeven(position_id)
    
    assert result is True
    assert position.breakeven_set is True
    # New stop should be at entry price (40000)
    assert position.stop_loss_order.stop_price == 40000.0


def test_order_manager_get_open_positions(mock_broker_adapter):
    """Test getting open positions."""
    manager = OrderManager(mock_broker_adapter)
    
    # Create multiple positions
    manager.create_entry_order(
        symbol='BTC/USDT',
        side='long',
        amount=0.1,
        price=40000.0
    )
    
    open_positions = manager.get_open_positions()
    
    assert len(open_positions) == 1
    assert open_positions[0].is_open() is True


def test_order_manager_close_position(mock_broker_adapter):
    """Test closing a position."""
    manager = OrderManager(mock_broker_adapter)
    
    # Create position with stop and TP
    entry_order = manager.create_entry_order(
        symbol='BTC/USDT',
        side='long',
        amount=0.1,
        price=40000.0
    )
    
    position_id = list(manager.positions.keys())[0]
    
    manager.create_stop_loss(position_id, 39500.0, 0.1)
    manager.create_take_profit(position_id, 41000.0, 0.05)
    
    # Close position
    manager.close_position(position_id, current_price=40500.0)
    
    position = manager.positions[position_id]
    assert position.closed_at is not None


def test_order_to_dict():
    """Test order serialization to dictionary."""
    order = Order(
        symbol='BTC/USDT',
        side='buy',
        order_type=OrderType.LIMIT,
        amount=0.1,
        price=40000.0
    )
    
    order_dict = order.to_dict()
    
    assert order_dict['symbol'] == 'BTC/USDT'
    assert order_dict['side'] == 'buy'
    assert order_dict['order_type'] == 'limit'
    assert order_dict['amount'] == 0.1
    assert order_dict['status'] == 'pending'
