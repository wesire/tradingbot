"""
Broker adapter for exchange connectivity using CCXT.
Provides abstraction layer for multiple exchanges with health monitoring.
"""
from typing import Dict, Optional, List, Any
import ccxt
import time
from datetime import datetime, timedelta
from enum import Enum
import asyncio


class ConnectionStatus(Enum):
    """Connection status states."""
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    RECONNECTING = "reconnecting"
    ERROR = "error"


class BrokerAdapter:
    """
    Exchange adapter using CCXT with connection health monitoring.
    """
    
    def __init__(
        self,
        exchange_name: str = "binance",
        api_key: str = "",
        api_secret: str = "",
        sandbox: bool = True,
        rate_limit: int = 50,
        testnet: bool = False
    ):
        """
        Initialize broker adapter.
        
        Args:
            exchange_name: Exchange name (e.g., 'binance', 'bybit')
            api_key: API key
            api_secret: API secret
            sandbox: Use sandbox/testnet mode
            rate_limit: Rate limit in requests per second
            testnet: Use testnet (for exchanges that support it)
        """
        self.exchange_name = exchange_name
        self.api_key = api_key
        self.api_secret = api_secret
        self.sandbox = sandbox
        self.rate_limit = rate_limit
        self.testnet = testnet
        
        # State
        self.status = ConnectionStatus.DISCONNECTED
        self.last_successful_request: Optional[datetime] = None
        self.failed_requests = 0
        self.max_failed_requests = 5
        self.reconnect_delay = 5  # seconds
        
        # Initialize exchange
        self.exchange: Optional[ccxt.Exchange] = None
        self._initialize_exchange()
    
    def _initialize_exchange(self):
        """Initialize CCXT exchange instance."""
        try:
            exchange_class = getattr(ccxt, self.exchange_name)
            
            config = {
                'apiKey': self.api_key,
                'secret': self.api_secret,
                'enableRateLimit': True,
                'rateLimit': self.rate_limit,
                'options': {
                    'defaultType': 'future'  # For futures trading
                }
            }
            
            if self.sandbox or self.testnet:
                config['options']['sandboxMode'] = True
            
            self.exchange = exchange_class(config)
            
            # Load markets
            self.exchange.load_markets()
            
            self.status = ConnectionStatus.CONNECTED
            self.last_successful_request = datetime.now()
            self.failed_requests = 0
            
        except Exception as e:
            self.status = ConnectionStatus.ERROR
            raise Exception(f"Failed to initialize exchange: {e}")
    
    def health_check(self) -> bool:
        """
        Check connection health.
        
        Returns:
            True if connection is healthy
        """
        if self.status != ConnectionStatus.CONNECTED:
            return False
        
        if self.failed_requests >= self.max_failed_requests:
            return False
        
        # Check if last successful request was recent
        if self.last_successful_request:
            time_since_success = datetime.now() - self.last_successful_request
            if time_since_success > timedelta(minutes=5):
                return False
        
        return True
    
    def reconnect(self) -> bool:
        """
        Attempt to reconnect to exchange.
        
        Returns:
            True if reconnection successful
        """
        self.status = ConnectionStatus.RECONNECTING
        
        try:
            time.sleep(self.reconnect_delay)
            self._initialize_exchange()
            return True
        except Exception:
            return False
    
    def _handle_request(self, func, *args, **kwargs) -> Any:
        """
        Wrapper for exchange requests with error handling.
        
        Args:
            func: Function to call
            *args: Positional arguments
            **kwargs: Keyword arguments
            
        Returns:
            Function result
        """
        try:
            result = func(*args, **kwargs)
            self.last_successful_request = datetime.now()
            self.failed_requests = 0
            return result
        
        except ccxt.NetworkError as e:
            self.failed_requests += 1
            if self.failed_requests >= self.max_failed_requests:
                self.status = ConnectionStatus.ERROR
            raise Exception(f"Network error: {e}")
        
        except ccxt.ExchangeError as e:
            self.failed_requests += 1
            raise Exception(f"Exchange error: {e}")
        
        except Exception as e:
            self.failed_requests += 1
            raise Exception(f"Unexpected error: {e}")
    
    def fetch_ticker(self, symbol: str) -> Dict:
        """
        Fetch ticker data for symbol.
        
        Args:
            symbol: Trading pair symbol
            
        Returns:
            Ticker data dictionary
        """
        if not self.health_check():
            if not self.reconnect():
                raise Exception("Exchange connection unhealthy and reconnection failed")
        
        return self._handle_request(self.exchange.fetch_ticker, symbol)
    
    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = '5m',
        since: Optional[int] = None,
        limit: int = 500
    ) -> List[List]:
        """
        Fetch OHLCV data.
        
        Args:
            symbol: Trading pair symbol
            timeframe: Timeframe (e.g., '1m', '5m', '1h')
            since: Timestamp in milliseconds
            limit: Number of candles to fetch
            
        Returns:
            List of OHLCV candles
        """
        if not self.health_check():
            if not self.reconnect():
                raise Exception("Exchange connection unhealthy and reconnection failed")
        
        return self._handle_request(
            self.exchange.fetch_ohlcv,
            symbol,
            timeframe,
            since,
            limit
        )
    
    def fetch_balance(self) -> Dict:
        """
        Fetch account balance.
        
        Returns:
            Balance dictionary
        """
        if not self.health_check():
            if not self.reconnect():
                raise Exception("Exchange connection unhealthy and reconnection failed")
        
        return self._handle_request(self.exchange.fetch_balance)
    
    def create_order(
        self,
        symbol: str,
        order_type: str,
        side: str,
        amount: float,
        price: Optional[float] = None,
        params: Optional[Dict] = None
    ) -> Dict:
        """
        Create an order.
        
        Args:
            symbol: Trading pair symbol
            order_type: Order type ('limit', 'market')
            side: Order side ('buy', 'sell')
            amount: Order amount
            price: Order price (for limit orders)
            params: Additional parameters
            
        Returns:
            Order result dictionary
        """
        if not self.health_check():
            if not self.reconnect():
                raise Exception("Exchange connection unhealthy and reconnection failed")
        
        return self._handle_request(
            self.exchange.create_order,
            symbol,
            order_type,
            side,
            amount,
            price,
            params or {}
        )
    
    def cancel_order(self, order_id: str, symbol: str) -> Dict:
        """
        Cancel an order.
        
        Args:
            order_id: Order ID
            symbol: Trading pair symbol
            
        Returns:
            Cancellation result
        """
        if not self.health_check():
            if not self.reconnect():
                raise Exception("Exchange connection unhealthy and reconnection failed")
        
        return self._handle_request(
            self.exchange.cancel_order,
            order_id,
            symbol
        )
    
    def fetch_order(self, order_id: str, symbol: str) -> Dict:
        """
        Fetch order details.
        
        Args:
            order_id: Order ID
            symbol: Trading pair symbol
            
        Returns:
            Order details dictionary
        """
        if not self.health_check():
            if not self.reconnect():
                raise Exception("Exchange connection unhealthy and reconnection failed")
        
        return self._handle_request(
            self.exchange.fetch_order,
            order_id,
            symbol
        )
    
    def fetch_open_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        """
        Fetch open orders.
        
        Args:
            symbol: Trading pair symbol (optional)
            
        Returns:
            List of open orders
        """
        if not self.health_check():
            if not self.reconnect():
                raise Exception("Exchange connection unhealthy and reconnection failed")
        
        return self._handle_request(
            self.exchange.fetch_open_orders,
            symbol
        )
    
    def fetch_my_trades(
        self,
        symbol: Optional[str] = None,
        since: Optional[int] = None,
        limit: int = 50
    ) -> List[Dict]:
        """
        Fetch personal trade history from the exchange.

        Args:
            symbol: Trading pair symbol (optional — fetch all if None)
            since: Start timestamp in milliseconds (optional)
            limit: Maximum number of trades to return

        Returns:
            List of trade dictionaries
        """
        if not self.health_check():
            if not self.reconnect():
                raise Exception("Exchange connection unhealthy and reconnection failed")

        return self._handle_request(
            self.exchange.fetch_my_trades,
            symbol,
            since,
            limit
        )

    def fetch_positions(self, symbols: Optional[List[str]] = None) -> List[Dict]:
        """
        Fetch current open positions from the exchange.

        Args:
            symbols: List of trading pair symbols to filter (optional)

        Returns:
            List of position dictionaries
        """
        if not self.health_check():
            if not self.reconnect():
                raise Exception("Exchange connection unhealthy and reconnection failed")

        if symbols:
            return self._handle_request(self.exchange.fetch_positions, symbols)
        return self._handle_request(self.exchange.fetch_positions)

    def set_leverage(self, leverage: int, symbol: str) -> Dict:
        """
        Set leverage for symbol.
        
        Args:
            leverage: Leverage multiplier
            symbol: Trading pair symbol
            
        Returns:
            Result dictionary
        """
        if not self.health_check():
            if not self.reconnect():
                raise Exception("Exchange connection unhealthy and reconnection failed")
        
        return self._handle_request(
            self.exchange.set_leverage,
            leverage,
            symbol
        )
    
    def close(self):
        """Close exchange connection."""
        if self.exchange:
            try:
                self.exchange.close()
            except Exception:
                pass
        
        self.status = ConnectionStatus.DISCONNECTED
