"""
Bot integration client for executing trading signals.
Provides clean abstraction for multiple bot implementations with retry logic.
"""
from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum
import logging
import time
import httpx
import os

logger = logging.getLogger(__name__)


class ExecutionStatus(str, Enum):
    """Execution result status."""
    SUCCESS = "success"
    FAILED = "failed"
    REJECTED = "rejected"


@dataclass
class ExecutionResult:
    """Result of execution attempt."""
    
    status: ExecutionStatus
    message: str
    order_id: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "status": self.status,
            "message": self.message,
            "order_id": self.order_id,
            "details": self.details
        }


@dataclass
class Signal:
    """Trading signal to execute."""
    
    symbol: str
    side: str
    timeframe: str
    setup_id: str
    confidence: float
    price: float
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "symbol": self.symbol,
            "side": self.side,
            "timeframe": self.timeframe,
            "setup_id": self.setup_id,
            "confidence": self.confidence,
            "price": self.price
        }


class BotClient:
    """Base class for bot integration clients."""
    
    def execute_signal(self, signal: Signal) -> ExecutionResult:
        """
        Execute a trading signal.
        
        Args:
            signal: Signal to execute
            
        Returns:
            ExecutionResult
        """
        raise NotImplementedError


class FreqtradeAdapter(BotClient):
    """Adapter for Freqtrade bot API."""
    
    def __init__(
        self,
        api_url: str,
        api_username: Optional[str] = None,
        api_password: Optional[str] = None,
        retry_attempts: int = 3,
        retry_backoff: float = 2.0,
        timeout: float = 10.0
    ):
        """
        Initialize Freqtrade adapter.
        
        Args:
            api_url: Base URL for Freqtrade API
            api_username: API username (if auth enabled)
            api_password: API password (if auth enabled)
            retry_attempts: Number of retry attempts
            retry_backoff: Exponential backoff multiplier
            timeout: Request timeout in seconds
        """
        self.api_url = api_url.rstrip('/')
        self.api_username = api_username
        self.api_password = api_password
        self.retry_attempts = retry_attempts
        self.retry_backoff = retry_backoff
        self.timeout = timeout
        
        logger.info(f"Initialized FreqtradeAdapter: {self.api_url}")
    
    def _get_auth(self) -> Optional[tuple]:
        """Get auth tuple if credentials provided."""
        if self.api_username and self.api_password:
            return (self.api_username, self.api_password)
        return None
    
    def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        attempt: int = 1
    ) -> tuple[bool, Optional[Dict], Optional[str]]:
        """
        Make HTTP request with retry logic.
        
        Args:
            method: HTTP method
            endpoint: API endpoint
            data: Request payload
            attempt: Current attempt number
            
        Returns:
            Tuple of (success, response_data, error_message)
        """
        url = f"{self.api_url}{endpoint}"
        
        try:
            with httpx.Client(timeout=self.timeout) as client:
                if method == "GET":
                    response = client.get(url, auth=self._get_auth())
                elif method == "POST":
                    response = client.post(url, json=data, auth=self._get_auth())
                else:
                    return False, None, f"Unsupported method: {method}"
                
                response.raise_for_status()
                
                return True, response.json(), None
        
        except httpx.TimeoutException as e:
            error_msg = f"Request timeout: {e}"
            logger.warning(f"Attempt {attempt}/{self.retry_attempts}: {error_msg}")
            
            if attempt < self.retry_attempts:
                wait_time = self.retry_backoff ** (attempt - 1)
                logger.info(f"Retrying in {wait_time}s...")
                time.sleep(wait_time)
                return self._make_request(method, endpoint, data, attempt + 1)
            
            return False, None, error_msg
        
        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP {e.response.status_code}: {e.response.text}"
            logger.error(f"Request failed: {error_msg}")
            return False, None, error_msg
        
        except httpx.ConnectError as e:
            error_msg = f"Connection failed: {e}"
            logger.warning(f"Attempt {attempt}/{self.retry_attempts}: {error_msg}")
            
            if attempt < self.retry_attempts:
                wait_time = self.retry_backoff ** (attempt - 1)
                logger.info(f"Retrying in {wait_time}s...")
                time.sleep(wait_time)
                return self._make_request(method, endpoint, data, attempt + 1)
            
            return False, None, error_msg
        
        except Exception as e:
            error_msg = f"Unexpected error: {e}"
            logger.error(error_msg, exc_info=True)
            return False, None, error_msg
    
    def check_health(self) -> bool:
        """Check if bot API is accessible."""
        success, data, error = self._make_request("GET", "/api/v1/ping")
        
        if success:
            logger.info("Bot API health check passed")
            return True
        else:
            logger.warning(f"Bot API health check failed: {error}")
            return False
    
    def execute_signal(self, signal: Signal) -> ExecutionResult:
        """
        Execute signal via Freqtrade forcebuy/forcesell.
        
        Note: In dry-run mode, this simulates the order.
        
        Args:
            signal: Signal to execute
            
        Returns:
            ExecutionResult
        """
        logger.info(
            f"Executing signal: {signal.symbol} {signal.side} "
            f"@ {signal.price}, confidence={signal.confidence}"
        )
        
        # Map side to freqtrade action
        if signal.side.lower() in ['long', 'buy']:
            endpoint = "/api/v1/forcebuy"
            payload = {
                "pair": signal.symbol,
                "price": signal.price
            }
        elif signal.side.lower() in ['short', 'sell']:
            endpoint = "/api/v1/forcesell"
            payload = {
                "pair": signal.symbol,
                "ordertype": "market"
            }
        else:
            return ExecutionResult(
                status=ExecutionStatus.REJECTED,
                message=f"Invalid side: {signal.side}",
                details=signal.to_dict()
            )
        
        # Execute request
        success, response_data, error = self._make_request(
            "POST",
            endpoint,
            payload
        )
        
        if success:
            # Extract order information
            order_id = None
            if response_data:
                order_id = response_data.get('order_id') or response_data.get('trade_id')
            
            logger.info(
                f"Signal executed successfully: order_id={order_id}, "
                f"response={response_data}"
            )
            
            return ExecutionResult(
                status=ExecutionStatus.SUCCESS,
                message=f"Order placed successfully",
                order_id=str(order_id) if order_id else None,
                details=response_data
            )
        else:
            logger.error(f"Signal execution failed: {error}")
            
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                message=error or "Unknown error",
                details=signal.to_dict()
            )


class MockBotClient(BotClient):
    """Mock bot client for testing."""
    
    def __init__(self, success: bool = True, fail_reason: Optional[str] = None):
        """
        Initialize mock client.
        
        Args:
            success: Whether to succeed or fail
            fail_reason: Reason for failure (if success=False)
        """
        self.success = success
        self.fail_reason = fail_reason
        logger.info(f"Initialized MockBotClient: success={success}")
    
    def execute_signal(self, signal: Signal) -> ExecutionResult:
        """Mock execution."""
        logger.info(f"Mock executing: {signal.symbol} {signal.side}")
        
        if self.success:
            return ExecutionResult(
                status=ExecutionStatus.SUCCESS,
                message="Mock order placed successfully",
                order_id=f"mock_{signal.symbol}_{int(time.time())}",
                details=signal.to_dict()
            )
        else:
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                message=self.fail_reason or "Mock failure",
                details=signal.to_dict()
            )


def create_bot_client() -> BotClient:
    """
    Factory function to create bot client based on environment config.
    
    Returns:
        BotClient instance
    """
    bot_type = os.getenv("BOT_TYPE", "freqtrade")
    
    if bot_type == "freqtrade":
        api_url = os.getenv("FREQTRADE_API_URL", "http://bot:8080")
        api_username = os.getenv("FREQTRADE_API_USERNAME")
        api_password = os.getenv("FREQTRADE_API_PASSWORD")
        
        return FreqtradeAdapter(
            api_url=api_url,
            api_username=api_username,
            api_password=api_password
        )
    
    elif bot_type == "mock":
        return MockBotClient(success=True)
    
    else:
        logger.warning(f"Unknown bot type: {bot_type}, using mock")
        return MockBotClient(success=True)
