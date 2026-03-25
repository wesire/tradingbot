"""
Order manager for handling order lifecycle, partial fills, and stop adjustments.
"""
from typing import Dict, Optional, List
from enum import Enum
from datetime import datetime
import uuid


class OrderStatus(Enum):
    """Order status states."""
    PENDING = "pending"
    OPEN = "open"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class OrderType(Enum):
    """Order types."""
    MARKET = "market"
    LIMIT = "limit"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"


class Order:
    """Represents a single order."""
    
    def __init__(
        self,
        symbol: str,
        side: str,
        order_type: OrderType,
        amount: float,
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
        parent_id: Optional[str] = None
    ):
        self.id = str(uuid.uuid4())
        self.exchange_id: Optional[str] = None
        self.symbol = symbol
        self.side = side  # 'buy' or 'sell'
        self.order_type = order_type
        self.amount = amount
        self.price = price
        self.stop_price = stop_price
        self.parent_id = parent_id  # For linking TPs/SLs to entry
        
        self.status = OrderStatus.PENDING
        self.filled_amount = 0.0
        self.average_fill_price: Optional[float] = None
        self.created_at = datetime.now()
        self.updated_at = datetime.now()
        self.filled_at: Optional[datetime] = None
        
        self.fills: List[Dict] = []
    
    def update_fill(self, filled_amount: float, fill_price: float):
        """
        Update order with fill information.
        
        Args:
            filled_amount: Amount filled in this update
            fill_price: Price of fill
        """
        self.filled_amount += filled_amount
        self.fills.append({
            'amount': filled_amount,
            'price': fill_price,
            'timestamp': datetime.now()
        })
        
        # Calculate average fill price
        total_value = sum(f['amount'] * f['price'] for f in self.fills)
        self.average_fill_price = total_value / self.filled_amount
        
        # Update status
        if self.filled_amount >= self.amount:
            self.status = OrderStatus.FILLED
            self.filled_at = datetime.now()
        elif self.filled_amount > 0:
            self.status = OrderStatus.PARTIAL
        
        self.updated_at = datetime.now()
    
    def to_dict(self) -> Dict:
        """Convert order to dictionary."""
        return {
            'id': self.id,
            'exchange_id': self.exchange_id,
            'symbol': self.symbol,
            'side': self.side,
            'order_type': self.order_type.value,
            'amount': self.amount,
            'price': self.price,
            'stop_price': self.stop_price,
            'status': self.status.value,
            'filled_amount': self.filled_amount,
            'average_fill_price': self.average_fill_price,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'filled_at': self.filled_at.isoformat() if self.filled_at else None,
            'fills': self.fills
        }


class Position:
    """Represents an open position with associated orders."""
    
    def __init__(
        self,
        symbol: str,
        side: str,
        entry_order: Order
    ):
        self.id = str(uuid.uuid4())
        self.symbol = symbol
        self.side = side  # 'long' or 'short'
        self.entry_order = entry_order
        
        self.stop_loss_order: Optional[Order] = None
        self.take_profit_orders: List[Order] = []
        
        self.first_tp_hit = False
        self.breakeven_set = False
        
        self.opened_at = datetime.now()
        self.closed_at: Optional[datetime] = None
    
    def is_open(self) -> bool:
        """Check if position is still open."""
        return self.entry_order.status in (
            OrderStatus.OPEN, OrderStatus.PARTIAL, OrderStatus.FILLED
        ) and self.closed_at is None
    
    def unrealized_pnl(self, current_price: float) -> float:
        """
        Calculate unrealized PnL.
        
        Args:
            current_price: Current market price
            
        Returns:
            Unrealized PnL
        """
        if not self.entry_order.average_fill_price:
            return 0.0
        
        entry_price = self.entry_order.average_fill_price
        position_size = self.entry_order.filled_amount
        
        if self.side == 'long':
            pnl = (current_price - entry_price) * position_size
        else:  # short
            pnl = (entry_price - current_price) * position_size
        
        return pnl


class OrderManager:
    """
    Manages order lifecycle, partial fills, and position tracking.
    """
    
    def __init__(self, broker_adapter):
        """
        Initialize order manager.
        
        Args:
            broker_adapter: BrokerAdapter instance for exchange communication
        """
        self.broker = broker_adapter
        self.orders: Dict[str, Order] = {}
        self.positions: Dict[str, Position] = {}
    
    def create_entry_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        order_type: OrderType = OrderType.LIMIT,
        price: Optional[float] = None
    ) -> Order:
        """
        Create an entry order.
        
        Args:
            symbol: Trading pair symbol
            side: 'long' or 'short'
            amount: Order amount
            order_type: Order type
            price: Limit price (if limit order)
            
        Returns:
            Created Order object
        """
        # Convert side to buy/sell
        order_side = 'buy' if side == 'long' else 'sell'
        
        order = Order(
            symbol=symbol,
            side=order_side,
            order_type=order_type,
            amount=amount,
            price=price
        )
        
        try:
            # Submit to exchange
            result = self.broker.create_order(
                symbol=symbol,
                order_type=order_type.value,
                side=order_side,
                amount=amount,
                price=price
            )
            
            order.exchange_id = result['id']
            order.status = OrderStatus.OPEN
            
            self.orders[order.id] = order
            
            # Create position
            position = Position(
                symbol=symbol,
                side=side,
                entry_order=order
            )
            self.positions[position.id] = position
            
        except Exception as e:
            order.status = OrderStatus.REJECTED
            raise Exception(f"Failed to create entry order: {e}")
        
        return order
    
    def create_stop_loss(
        self,
        position_id: str,
        stop_price: float,
        amount: float
    ) -> Order:
        """
        Create stop loss order for position.
        
        Args:
            position_id: Position ID
            stop_price: Stop loss trigger price
            amount: Order amount
            
        Returns:
            Created stop loss order
        """
        if position_id not in self.positions:
            raise ValueError(f"Position {position_id} not found")
        
        position = self.positions[position_id]
        
        # Opposite side of entry
        order_side = 'sell' if position.side == 'long' else 'buy'
        
        stop_order = Order(
            symbol=position.symbol,
            side=order_side,
            order_type=OrderType.STOP_LOSS,
            amount=amount,
            stop_price=stop_price,
            parent_id=position.entry_order.id
        )
        
        try:
            # Submit to exchange
            result = self.broker.create_order(
                symbol=position.symbol,
                order_type='stop_loss_limit',
                side=order_side,
                amount=amount,
                price=stop_price,
                params={'stopPrice': stop_price}
            )
            
            stop_order.exchange_id = result['id']
            stop_order.status = OrderStatus.OPEN
            
            self.orders[stop_order.id] = stop_order
            position.stop_loss_order = stop_order
            
        except Exception as e:
            stop_order.status = OrderStatus.REJECTED
            raise Exception(f"Failed to create stop loss: {e}")
        
        return stop_order
    
    def create_take_profit(
        self,
        position_id: str,
        tp_price: float,
        amount: float
    ) -> Order:
        """
        Create take profit order for position.
        
        Args:
            position_id: Position ID
            tp_price: Take profit target price
            amount: Order amount
            
        Returns:
            Created take profit order
        """
        if position_id not in self.positions:
            raise ValueError(f"Position {position_id} not found")
        
        position = self.positions[position_id]
        
        # Opposite side of entry
        order_side = 'sell' if position.side == 'long' else 'buy'
        
        tp_order = Order(
            symbol=position.symbol,
            side=order_side,
            order_type=OrderType.TAKE_PROFIT,
            amount=amount,
            price=tp_price,
            parent_id=position.entry_order.id
        )
        
        try:
            # Submit as limit order at TP price
            result = self.broker.create_order(
                symbol=position.symbol,
                order_type='limit',
                side=order_side,
                amount=amount,
                price=tp_price
            )
            
            tp_order.exchange_id = result['id']
            tp_order.status = OrderStatus.OPEN
            
            self.orders[tp_order.id] = tp_order
            position.take_profit_orders.append(tp_order)
            
        except Exception as e:
            tp_order.status = OrderStatus.REJECTED
            raise Exception(f"Failed to create take profit: {e}")
        
        return tp_order
    
    def move_stop_to_breakeven(self, position_id: str) -> bool:
        """
        Move stop loss to breakeven for position.
        
        Args:
            position_id: Position ID
            
        Returns:
            True if successful
        """
        if position_id not in self.positions:
            return False
        
        position = self.positions[position_id]
        
        if not position.stop_loss_order or position.breakeven_set:
            return False
        
        entry_price = position.entry_order.average_fill_price
        if not entry_price:
            return False
        
        try:
            # Cancel old stop loss
            if position.stop_loss_order.exchange_id:
                self.broker.cancel_order(
                    position.stop_loss_order.exchange_id,
                    position.symbol
                )
            
            # Create new stop at breakeven
            position.stop_loss_order = self.create_stop_loss(
                position_id=position_id,
                stop_price=entry_price,
                amount=position.entry_order.filled_amount
            )
            
            position.breakeven_set = True
            return True
            
        except Exception:
            return False
    
    def update_order_status(self, order_id: str) -> Order:
        """
        Fetch and update order status from exchange.
        
        Args:
            order_id: Internal order ID
            
        Returns:
            Updated order
        """
        if order_id not in self.orders:
            raise ValueError(f"Order {order_id} not found")
        
        order = self.orders[order_id]
        
        if not order.exchange_id:
            return order
        
        try:
            exchange_order = self.broker.fetch_order(
                order.exchange_id,
                order.symbol
            )
            
            # Update order with exchange data
            if exchange_order['filled'] > order.filled_amount:
                new_fill = exchange_order['filled'] - order.filled_amount
                fill_price = exchange_order.get('average', exchange_order.get('price', 0))
                order.update_fill(new_fill, fill_price)
            
            # Map exchange status
            if exchange_order['status'] == 'closed':
                order.status = OrderStatus.FILLED
            elif exchange_order['status'] == 'canceled':
                order.status = OrderStatus.CANCELLED
            
        except Exception as e:
            print(f"Failed to update order status: {e}")
        
        return order
    
    def get_open_positions(self) -> List[Position]:
        """Get all open positions."""
        return [p for p in self.positions.values() if p.is_open()]
    
    def close_position(self, position_id: str, current_price: float):
        """
        Close a position.
        
        Args:
            position_id: Position ID
            current_price: Current market price for PnL calculation
        """
        if position_id not in self.positions:
            return
        
        position = self.positions[position_id]
        position.closed_at = datetime.now()
        
        # Cancel all open orders for this position
        if position.stop_loss_order and position.stop_loss_order.status == OrderStatus.OPEN:
            try:
                self.broker.cancel_order(
                    position.stop_loss_order.exchange_id,
                    position.symbol
                )
            except Exception:
                pass
        
        for tp_order in position.take_profit_orders:
            if tp_order.status == OrderStatus.OPEN:
                try:
                    self.broker.cancel_order(
                        tp_order.exchange_id,
                        position.symbol
                    )
                except Exception:
                    pass
