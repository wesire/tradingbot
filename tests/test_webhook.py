"""
Tests for TradingView webhook gateway.
"""
import pytest
from fastapi.testclient import TestClient
from datetime import datetime
import time

from tv_gateway.main import app
from tv_gateway.auth import WebhookAuth


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def valid_payload():
    """Create a valid webhook payload."""
    return {
        'symbol': 'BTCUSDT',
        'timeframe': '5m',
        'side': 'long',
        'setup_id': 'test_setup',
        'confidence': 0.85,
        'price': 40000.0,
        'event_time': str(int(datetime.now().timestamp() * 1000)),
        'secret': 'your_webhook_secret_here',
        'timestamp': int(datetime.now().timestamp()),
        'nonce': f'test_{int(time.time() * 1000)}'
    }


def test_health_endpoint(client):
    """Test health check endpoint."""
    response = client.get("/health")
    
    assert response.status_code == 200
    data = response.json()
    assert data['status'] == 'healthy'
    assert 'version' in data
    assert 'uptime_seconds' in data


def test_root_endpoint(client):
    """Test root endpoint returns HTML dashboard."""
    response = client.get("/")
    
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Dashboard" in response.text


def test_webhook_endpoint_valid_payload(client, valid_payload):
    """Test webhook endpoint with valid payload."""
    response = client.post("/tv/webhook", json=valid_payload)
    
    assert response.status_code == 200
    data = response.json()
    assert data['success'] is True
    assert 'message' in data
    assert 'alert_id' in data


def test_webhook_endpoint_duplicate_detection(client, valid_payload):
    """Test webhook endpoint detects and handles duplicates."""
    # Send first request
    response1 = client.post("/tv/webhook", json=valid_payload)
    assert response1.status_code == 200
    data1 = response1.json()
    assert data1['success'] is True
    alert_id_1 = data1.get('alert_id')
    
    # Send duplicate with same nonce
    response2 = client.post("/tv/webhook", json=valid_payload)
    assert response2.status_code == 200
    data2 = response2.json()
    assert data2['success'] is True
    assert 'duplicate' in data2.get('action_taken', '').lower()
    
    # Should return same alert ID
    alert_id_2 = data2.get('alert_id')
    assert alert_id_1 == alert_id_2


def test_webhook_endpoint_invalid_secret(client, valid_payload):
    """Test webhook endpoint rejects invalid secret."""
    payload = valid_payload.copy()
    payload['secret'] = 'wrong_secret'
    
    response = client.post("/tv/webhook", json=payload)
    
    assert response.status_code == 401


def test_webhook_endpoint_stale_timestamp(client, valid_payload):
    """Test webhook endpoint rejects stale timestamps."""
    payload = valid_payload.copy()
    # Set timestamp to 60 seconds ago
    payload['timestamp'] = int((datetime.now().timestamp() - 60))
    
    response = client.post("/tv/webhook", json=payload)
    
    assert response.status_code == 401


def test_webhook_endpoint_invalid_side(client, valid_payload):
    """Test webhook endpoint validates side field."""
    payload = valid_payload.copy()
    payload['side'] = 'invalid_side'
    
    response = client.post("/tv/webhook", json=payload)
    
    assert response.status_code == 422  # Validation error


def test_webhook_endpoint_invalid_timeframe(client, valid_payload):
    """Test webhook endpoint validates timeframe field."""
    payload = valid_payload.copy()
    payload['timeframe'] = '99m'  # Invalid timeframe
    
    response = client.post("/tv/webhook", json=payload)
    
    assert response.status_code == 422


def test_webhook_endpoint_missing_required_field(client, valid_payload):
    """Test webhook endpoint requires all fields."""
    payload = valid_payload.copy()
    del payload['symbol']
    
    response = client.post("/tv/webhook", json=payload)
    
    assert response.status_code == 422


def test_alerts_list_endpoint(client):
    """Test GET /alerts endpoint."""
    response = client.get("/alerts?limit=10")
    
    assert response.status_code == 200
    data = response.json()
    assert 'success' in data
    assert 'alerts' in data
    assert 'count' in data
    assert isinstance(data['alerts'], list)


def test_alerts_list_with_status_filter(client):
    """Test GET /alerts with status filter."""
    response = client.get("/alerts?status=accepted&limit=10")
    
    assert response.status_code == 200
    data = response.json()
    assert 'success' in data


def test_alerts_list_with_symbol_filter(client):
    """Test GET /alerts with symbol filter."""
    response = client.get("/alerts?symbol=BTCUSDT&limit=10")
    
    assert response.status_code == 200
    data = response.json()
    assert 'success' in data


def test_get_alert_by_id(client, valid_payload):
    """Test GET /alerts/{id} endpoint."""
    # First create an alert
    response = client.post("/tv/webhook", json=valid_payload)
    assert response.status_code == 200
    alert_id = response.json().get('alert_id')
    
    if alert_id:
        # Get the alert by ID
        response = client.get(f"/alerts/{alert_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert 'success' in data
        assert 'alert' in data
        assert data['alert']['id'] == int(alert_id)


def test_get_alert_not_found(client):
    """Test GET /alerts/{id} with non-existent ID."""
    response = client.get("/alerts/999999")
    
    assert response.status_code == 404


def test_stats_endpoint(client):
    """Test GET /stats endpoint."""
    response = client.get("/stats")
    
    assert response.status_code == 200
    data = response.json()
    assert 'success' in data
    assert 'service' in data
    assert 'alerts' in data
    
    # Check service info
    service = data['service']
    assert 'status' in service
    assert 'uptime_seconds' in service
    
    # Check alerts stats
    alerts = data['alerts']
    assert 'total_alerts' in alerts
    assert 'by_status' in alerts


def test_webhook_auth_validate_secret():
    """Test secret validation."""
    auth = WebhookAuth(shared_secret='test_secret_123')
    
    # Valid secret
    assert auth.validate_secret('test_secret_123') is True
    
    # Invalid secret
    assert auth.validate_secret('wrong_secret') is False
    
    # Empty secret
    assert auth.validate_secret('') is False


def test_webhook_auth_validate_timestamp():
    """Test timestamp validation."""
    auth = WebhookAuth(shared_secret='test_secret', max_age_seconds=30)
    
    # Current timestamp should be valid
    current_ts = int(datetime.now().timestamp())
    is_valid, msg = auth.validate_timestamp(current_ts)
    assert is_valid is True
    
    # Old timestamp should be invalid
    old_ts = int((datetime.now().timestamp() - 60))
    is_valid, msg = auth.validate_timestamp(old_ts)
    assert is_valid is False
    assert 'too old' in msg.lower()
    
    # Future timestamp should be invalid (beyond tolerance)
    future_ts = int((datetime.now().timestamp() + 10))
    is_valid, msg = auth.validate_timestamp(future_ts)
    assert is_valid is False


def test_webhook_auth_validate_nonce():
    """Test nonce validation for replay attack prevention."""
    auth = WebhookAuth(shared_secret='test_secret')
    
    # First use of nonce should be valid
    is_valid, msg = auth.validate_nonce('nonce_1')
    assert is_valid is True
    
    # Reuse of same nonce should be invalid
    is_valid, msg = auth.validate_nonce('nonce_1')
    assert is_valid is False
    assert 'replay' in msg.lower()
    
    # Different nonce should be valid
    is_valid, msg = auth.validate_nonce('nonce_2')
    assert is_valid is True


def test_webhook_auth_rate_limiting():
    """Test rate limiting per IP."""
    auth = WebhookAuth(shared_secret='test_secret')
    auth.rate_limit_max_requests = 5
    
    client_ip = '192.168.1.1'
    
    # First 5 requests should pass
    for i in range(5):
        is_allowed, msg = auth.check_rate_limit(client_ip)
        assert is_allowed is True
    
    # 6th request should be blocked
    is_allowed, msg = auth.check_rate_limit(client_ip)
    assert is_allowed is False
    assert 'rate limit' in msg.lower()


def test_webhook_auth_validate_all():
    """Test combined validation."""
    auth = WebhookAuth(shared_secret='test_secret')
    
    current_ts = int(datetime.now().timestamp())
    nonce = f'test_{current_ts}'
    client_ip = '192.168.1.1'
    
    # All valid
    is_valid, msg = auth.validate_all(
        secret='test_secret',
        timestamp=current_ts,
        nonce=nonce,
        client_ip=client_ip
    )
    assert is_valid is True
    
    # Invalid secret
    is_valid, msg = auth.validate_all(
        secret='wrong_secret',
        timestamp=current_ts,
        nonce=f'test_{current_ts}_2',
        client_ip=client_ip
    )
    assert is_valid is False
    assert 'secret' in msg.lower()


def test_webhook_payload_schema_validation():
    """Test Pydantic schema validation."""
    from tv_gateway.schemas import WebhookPayload
    
    # Valid payload
    payload = WebhookPayload(
        symbol='BTCUSDT',
        timeframe='5m',
        side='long',
        setup_id='test',
        confidence=0.8,
        price=40000.0,
        event_time=str(int(datetime.now().timestamp() * 1000)),
        secret='secret',
        timestamp=int(datetime.now().timestamp()),
        nonce='nonce123'
    )
    
    assert payload.symbol == 'BTCUSDT'
    assert payload.side == 'long'
    
    # Test side normalization
    payload_buy = WebhookPayload(
        symbol='BTCUSDT',
        timeframe='5m',
        side='BUY',  # Should be normalized to 'buy'
        setup_id='test',
        confidence=0.8,
        price=40000.0,
        event_time=str(int(datetime.now().timestamp() * 1000)),
        secret='secret',
        timestamp=int(datetime.now().timestamp()),
        nonce='nonce124'
    )
    
    assert payload_buy.side == 'buy'
