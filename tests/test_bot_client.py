"""
Tests for bot integration client.
"""
import pytest
import httpx
from unittest.mock import Mock, patch
import time

from tv_gateway.bot_client import (
    BotClient,
    FreqtradeAdapter,
    MockBotClient,
    Signal,
    ExecutionResult,
    ExecutionStatus
)


@pytest.fixture
def sample_signal():
    """Create a sample trading signal."""
    return Signal(
        symbol="BTCUSDT",
        side="long",
        timeframe="5m",
        setup_id="test_setup",
        confidence=0.85,
        price=40000.0
    )


def test_signal_to_dict(sample_signal):
    """Test signal serialization."""
    signal_dict = sample_signal.to_dict()
    
    assert signal_dict['symbol'] == "BTCUSDT"
    assert signal_dict['side'] == "long"
    assert signal_dict['confidence'] == 0.85


def test_execution_result_to_dict():
    """Test execution result serialization."""
    result = ExecutionResult(
        status=ExecutionStatus.SUCCESS,
        message="Order placed",
        order_id="12345",
        details={"test": "data"}
    )
    
    result_dict = result.to_dict()
    
    assert result_dict['status'] == ExecutionStatus.SUCCESS
    assert result_dict['message'] == "Order placed"
    assert result_dict['order_id'] == "12345"


def test_mock_bot_client_success(sample_signal):
    """Test mock bot client with success."""
    client = MockBotClient(success=True)
    
    result = client.execute_signal(sample_signal)
    
    assert result.status == ExecutionStatus.SUCCESS
    assert result.order_id is not None
    assert "mock" in result.order_id.lower()


def test_mock_bot_client_failure(sample_signal):
    """Test mock bot client with failure."""
    client = MockBotClient(success=False, fail_reason="Test failure")
    
    result = client.execute_signal(sample_signal)
    
    assert result.status == ExecutionStatus.FAILED
    assert result.message == "Test failure"


@patch('httpx.Client')
def test_freqtrade_adapter_execute_long(mock_client_class, sample_signal):
    """Test Freqtrade adapter executing a long signal."""
    # Mock successful response
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "status": "success",
        "order_id": "test_order_123"
    }
    mock_response.raise_for_status = Mock()
    
    mock_client = Mock()
    mock_client.post.return_value = mock_response
    mock_client.__enter__ = Mock(return_value=mock_client)
    mock_client.__exit__ = Mock(return_value=False)
    mock_client_class.return_value = mock_client
    
    # Create adapter
    adapter = FreqtradeAdapter(api_url="http://test:8080")
    
    # Execute signal
    result = adapter.execute_signal(sample_signal)
    
    assert result.status == ExecutionStatus.SUCCESS
    assert result.order_id == "test_order_123"
    
    # Verify API call
    mock_client.post.assert_called_once()
    call_args = mock_client.post.call_args
    assert "/forcebuy" in call_args[0][0]


@patch('httpx.Client')
def test_freqtrade_adapter_execute_short(mock_client_class):
    """Test Freqtrade adapter executing a short signal."""
    signal = Signal(
        symbol="BTCUSDT",
        side="short",
        timeframe="5m",
        setup_id="test",
        confidence=0.9,
        price=40000.0
    )
    
    # Mock successful response
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "status": "success",
        "trade_id": "trade_456"
    }
    mock_response.raise_for_status = Mock()
    
    mock_client = Mock()
    mock_client.post.return_value = mock_response
    mock_client.__enter__ = Mock(return_value=mock_client)
    mock_client.__exit__ = Mock(return_value=False)
    mock_client_class.return_value = mock_client
    
    # Create adapter
    adapter = FreqtradeAdapter(api_url="http://test:8080")
    
    # Execute signal
    result = adapter.execute_signal(signal)
    
    assert result.status == ExecutionStatus.SUCCESS
    
    # Verify API call
    mock_client.post.assert_called_once()
    call_args = mock_client.post.call_args
    assert "/forcesell" in call_args[0][0]


@patch('httpx.Client')
def test_freqtrade_adapter_connection_error(mock_client_class, sample_signal):
    """Test Freqtrade adapter handling connection errors."""
    # Mock connection error
    mock_client = Mock()
    mock_client.post.side_effect = httpx.ConnectError("Connection failed")
    mock_client.__enter__ = Mock(return_value=mock_client)
    mock_client.__exit__ = Mock(return_value=False)
    mock_client_class.return_value = mock_client
    
    # Create adapter with no retries
    adapter = FreqtradeAdapter(
        api_url="http://test:8080",
        retry_attempts=1
    )
    
    # Execute signal
    result = adapter.execute_signal(sample_signal)
    
    assert result.status == ExecutionStatus.FAILED
    assert "Connection failed" in result.message


@patch('httpx.Client')
def test_freqtrade_adapter_retry_logic(mock_client_class, sample_signal):
    """Test retry logic with exponential backoff."""
    # Mock: fail twice, succeed on third attempt
    mock_response_success = Mock()
    mock_response_success.status_code = 200
    mock_response_success.json.return_value = {"order_id": "123"}
    mock_response_success.raise_for_status = Mock()
    
    mock_client = Mock()
    mock_client.post.side_effect = [
        httpx.ConnectError("Temp fail 1"),
        httpx.ConnectError("Temp fail 2"),
        mock_response_success
    ]
    mock_client.__enter__ = Mock(return_value=mock_client)
    mock_client.__exit__ = Mock(return_value=False)
    mock_client_class.return_value = mock_client
    
    # Create adapter with 3 retries
    adapter = FreqtradeAdapter(
        api_url="http://test:8080",
        retry_attempts=3,
        retry_backoff=0.1  # Fast backoff for testing
    )
    
    # Execute signal
    start_time = time.time()
    result = adapter.execute_signal(sample_signal)
    elapsed = time.time() - start_time
    
    # Should succeed after retries
    assert result.status == ExecutionStatus.SUCCESS
    
    # Should have taken some time due to retries
    assert elapsed > 0.1


@patch('httpx.Client')
def test_freqtrade_adapter_http_error(mock_client_class, sample_signal):
    """Test handling of HTTP errors."""
    # Mock HTTP error
    mock_response = Mock()
    mock_response.status_code = 400
    mock_response.text = "Bad request"
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "400 error", request=Mock(), response=mock_response
    )
    
    mock_client = Mock()
    mock_client.post.return_value = mock_response
    mock_client.__enter__ = Mock(return_value=mock_client)
    mock_client.__exit__ = Mock(return_value=False)
    mock_client_class.return_value = mock_client
    
    # Create adapter
    adapter = FreqtradeAdapter(api_url="http://test:8080")
    
    # Execute signal
    result = adapter.execute_signal(sample_signal)
    
    assert result.status == ExecutionStatus.FAILED
    assert "400" in result.message


@patch('httpx.Client')
def test_freqtrade_adapter_timeout(mock_client_class, sample_signal):
    """Test handling of timeouts."""
    # Mock timeout
    mock_client = Mock()
    mock_client.post.side_effect = httpx.TimeoutException("Request timeout")
    mock_client.__enter__ = Mock(return_value=mock_client)
    mock_client.__exit__ = Mock(return_value=False)
    mock_client_class.return_value = mock_client
    
    # Create adapter with no retries
    adapter = FreqtradeAdapter(
        api_url="http://test:8080",
        retry_attempts=1
    )
    
    # Execute signal
    result = adapter.execute_signal(sample_signal)
    
    assert result.status == ExecutionStatus.FAILED
    assert "timeout" in result.message.lower()


@patch('httpx.Client')
def test_freqtrade_adapter_health_check(mock_client_class):
    """Test health check endpoint."""
    # Mock successful ping
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": "ok"}
    mock_response.raise_for_status = Mock()
    
    mock_client = Mock()
    mock_client.get.return_value = mock_response
    mock_client.__enter__ = Mock(return_value=mock_client)
    mock_client.__exit__ = Mock(return_value=False)
    mock_client_class.return_value = mock_client
    
    # Create adapter
    adapter = FreqtradeAdapter(api_url="http://test:8080")
    
    # Check health
    is_healthy = adapter.check_health()
    
    assert is_healthy is True
    mock_client.get.assert_called_once()


def test_freqtrade_adapter_invalid_side(sample_signal):
    """Test rejection of invalid trade side."""
    signal = Signal(
        symbol="BTCUSDT",
        side="invalid_side",
        timeframe="5m",
        setup_id="test",
        confidence=0.9,
        price=40000.0
    )
    
    adapter = FreqtradeAdapter(api_url="http://test:8080")
    
    result = adapter.execute_signal(signal)
    
    assert result.status == ExecutionStatus.REJECTED
    assert "Invalid side" in result.message


def test_freqtrade_adapter_with_auth():
    """Test adapter with authentication."""
    adapter = FreqtradeAdapter(
        api_url="http://test:8080",
        api_username="testuser",
        api_password="testpass"
    )
    
    auth = adapter._get_auth()
    
    assert auth is not None
    assert auth == ("testuser", "testpass")


def test_freqtrade_adapter_without_auth():
    """Test adapter without authentication."""
    adapter = FreqtradeAdapter(api_url="http://test:8080")
    
    auth = adapter._get_auth()
    
    assert auth is None
