"""
Integration tests for Phase 2.1 webhook endpoint.
Tests HMAC authentication, replay protection, rate limiting, and kill switches.
"""
import pytest
import time
import hmac
import hashlib
import json
import os
from fastapi.testclient import TestClient
from datetime import datetime

# Set test environment
os.environ["ALERTS_DB_PATH"] = ":memory:"
os.environ["REQUIRE_HMAC"] = "false"
os.environ["EXECUTION_ENABLED"] = "true"
os.environ["WEBHOOK_ACCEPTING_ENABLED"] = "true"
os.environ["RUNMODE"] = "dry-run"
os.environ["RATE_LIMIT_PER_MINUTE"] = "100"  # High limit for tests
os.environ["MAX_PAYLOAD_SIZE_KB"] = "32"

from tv_gateway.main import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def valid_payload():
    """Create valid payload."""
    return {
        'symbol': 'BTCUSDT',
        'timeframe': '5m',
        'side': 'long',
        'setup_id': 'test_setup',
        'confidence': 0.95,
        'price': 40000.0,
        'event_time': str(int(datetime.now().timestamp() * 1000)),
        'secret': 'your_webhook_secret_here',
        'timestamp': int(datetime.now().timestamp()),
        'nonce': f'test_{int(time.time() * 1000000)}'
    }


class TestWebhookHMAC:
    """Tests for HMAC authentication on webhook."""
    
    def test_webhook_without_hmac_when_optional(self, client, valid_payload):
        """Test webhook works without HMAC when not required."""
        response = client.post("/tv/webhook", json=valid_payload)
        
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
    
    def test_webhook_with_valid_hmac(self, client, valid_payload):
        """Test webhook with valid HMAC signature."""
        secret = "your_webhook_secret_here"
        timestamp = str(int(time.time()))
        nonce = f'hmac_test_{int(time.time() * 1000000)}'
        
        # Update payload
        valid_payload['nonce'] = nonce
        valid_payload['timestamp'] = int(timestamp)
        
        body = json.dumps(valid_payload).encode('utf-8')
        
        # Generate HMAC signature
        message = f"{timestamp}.{nonce}.".encode('utf-8') + body
        signature = hmac.new(secret.encode('utf-8'), message, hashlib.sha256).hexdigest()
        
        # Send with HMAC headers
        response = client.post(
            "/tv/webhook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-TV-Timestamp": timestamp,
                "X-TV-Nonce": nonce,
                "X-TV-Signature": signature
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
    
    def test_webhook_with_invalid_hmac(self, client, valid_payload):
        """Test webhook rejects invalid HMAC signature."""
        timestamp = str(int(time.time()))
        nonce = f'hmac_bad_{int(time.time() * 1000000)}'
        
        valid_payload['nonce'] = nonce
        body = json.dumps(valid_payload).encode('utf-8')
        
        # Wrong signature
        wrong_signature = "0" * 64
        
        response = client.post(
            "/tv/webhook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-TV-Timestamp": timestamp,
                "X-TV-Nonce": nonce,
                "X-TV-Signature": wrong_signature
            }
        )
        
        assert response.status_code == 401
        data = response.json()
        assert "Invalid HMAC signature" in data['detail']
    
    def test_webhook_hmac_timestamp_skew(self, client, valid_payload):
        """Test HMAC with timestamp outside skew window."""
        secret = "your_webhook_secret_here"
        # Old timestamp (2 minutes ago, outside default 60s skew)
        timestamp = str(int(time.time()) - 120)
        nonce = f'hmac_old_{int(time.time() * 1000000)}'
        
        valid_payload['nonce'] = nonce
        body = json.dumps(valid_payload).encode('utf-8')
        
        # Generate valid signature
        message = f"{timestamp}.{nonce}.".encode('utf-8') + body
        signature = hmac.new(secret.encode('utf-8'), message, hashlib.sha256).hexdigest()
        
        response = client.post(
            "/tv/webhook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-TV-Timestamp": timestamp,
                "X-TV-Nonce": nonce,
                "X-TV-Signature": signature
            }
        )
        
        assert response.status_code == 401
        assert "skew window" in response.json()['detail']


class TestWebhookReplayProtection:
    """Tests for replay protection."""
    
    def test_webhook_replay_blocked(self, client, valid_payload):
        """Test replay attack is blocked."""
        # First request
        response1 = client.post("/tv/webhook", json=valid_payload)
        assert response1.status_code == 200
        
        # Replay with same nonce - should be blocked
        response2 = client.post("/tv/webhook", json=valid_payload)
        
        assert response2.status_code == 409
        assert "replay attack" in response2.json()['detail']
    
    def test_webhook_different_nonce_allowed(self, client, valid_payload):
        """Test different nonces are allowed."""
        # First request
        response1 = client.post("/tv/webhook", json=valid_payload)
        assert response1.status_code == 200
        
        # Different nonce - should be allowed
        valid_payload['nonce'] = f'different_{int(time.time() * 1000000)}'
        response2 = client.post("/tv/webhook", json=valid_payload)
        
        assert response2.status_code == 200


class TestWebhookRateLimiting:
    """Tests for rate limiting."""
    
    def test_webhook_rate_limit_applied(self):
        """Test rate limiting blocks excessive requests."""
        # Create client with low rate limit
        os.environ["RATE_LIMIT_PER_MINUTE"] = "5"
        
        # Import after setting env var
        from tv_gateway.main import app
        client = TestClient(app)
        
        # Make requests up to limit
        for i in range(5):
            payload = {
                'symbol': 'BTCUSDT',
                'timeframe': '5m',
                'side': 'long',
                'setup_id': 'test_setup',
                'confidence': 0.95,
                'price': 40000.0,
                'event_time': str(int(datetime.now().timestamp() * 1000)),
                'secret': 'your_webhook_secret_here',
                'timestamp': int(datetime.now().timestamp()),
                'nonce': f'rate_test_{i}_{int(time.time() * 1000000)}'
            }
            response = client.post("/tv/webhook", json=payload)
            if response.status_code != 200:
                print(f"Request {i} failed: {response.status_code} - {response.text}")
        
        # Next request should be rate limited
        payload = {
            'symbol': 'BTCUSDT',
            'timeframe': '5m',
            'side': 'long',
            'setup_id': 'test_setup',
            'confidence': 0.95,
            'price': 40000.0,
            'event_time': str(int(datetime.now().timestamp() * 1000)),
            'secret': 'your_webhook_secret_here',
            'timestamp': int(datetime.now().timestamp()),
            'nonce': f'rate_test_overflow_{int(time.time() * 1000000)}'
        }
        response = client.post("/tv/webhook", json=payload)
        
        assert response.status_code == 429
        assert 'Retry-After' in response.headers
        
        # Reset for other tests
        os.environ["RATE_LIMIT_PER_MINUTE"] = "100"


class TestWebhookPayloadSize:
    """Tests for payload size limit."""
    
    def test_webhook_payload_too_large(self, client):
        """Test payload exceeding size limit is rejected."""
        # Create a large payload (>32KB)
        large_payload = {
            'symbol': 'BTCUSDT',
            'timeframe': '5m',
            'side': 'long',
            'setup_id': 'test_setup',
            'confidence': 0.95,
            'price': 40000.0,
            'event_time': str(int(datetime.now().timestamp() * 1000)),
            'secret': 'your_webhook_secret_here',
            'timestamp': int(datetime.now().timestamp()),
            'nonce': f'large_{int(time.time() * 1000000)}',
            'notes': 'x' * 50000  # 50KB of data
        }
        
        response = client.post("/tv/webhook", json=large_payload)
        
        assert response.status_code == 413
        assert "too large" in response.json()['detail'].lower()


class TestWebhookKillSwitches:
    """Tests for operational kill switches."""
    
    def test_webhook_disabled(self):
        """Test webhook disabled kill switch."""
        os.environ["WEBHOOK_ACCEPTING_ENABLED"] = "false"
        
        # Reimport to apply env change
        from tv_gateway.main import app
        client = TestClient(app)
        
        payload = {
            'symbol': 'BTCUSDT',
            'timeframe': '5m',
            'side': 'long',
            'setup_id': 'test_setup',
            'confidence': 0.95,
            'price': 40000.0,
            'event_time': str(int(datetime.now().timestamp() * 1000)),
            'secret': 'your_webhook_secret_here',
            'timestamp': int(datetime.now().timestamp()),
            'nonce': f'disabled_{int(time.time() * 1000000)}'
        }
        
        response = client.post("/tv/webhook", json=payload)
        
        assert response.status_code == 503
        assert "disabled" in response.json()['detail'].lower()
        
        # Reset
        os.environ["WEBHOOK_ACCEPTING_ENABLED"] = "true"


class TestAdminEndpoints:
    """Tests for admin endpoints."""
    
    def test_admin_config_without_token(self, client):
        """Test admin endpoint requires token."""
        response = client.get("/admin/config")
        
        # Should fail without token (if ADMIN_TOKEN is not set, it returns 503)
        assert response.status_code in [401, 503]
    
    def test_admin_circuit_reset_without_token(self, client):
        """Test circuit reset requires token."""
        response = client.post("/admin/circuit/reset")
        
        assert response.status_code in [401, 503]


class TestStatsEndpoint:
    """Tests for /stats endpoint."""
    
    def test_stats_includes_circuit_breaker(self, client):
        """Test /stats includes circuit breaker status."""
        response = client.get("/stats")
        
        assert response.status_code == 200
        data = response.json()
        
        assert 'circuit_breaker' in data
        assert 'state' in data['circuit_breaker']
        assert data['circuit_breaker']['state'] in ['closed', 'open', 'half_open']
    
    def test_stats_includes_operational_flags(self, client):
        """Test /stats includes operational flags."""
        response = client.get("/stats")
        
        assert response.status_code == 200
        data = response.json()
        
        assert 'operational' in data
        assert 'webhook_accepting' in data['operational']
        assert 'execution_enabled' in data['operational']
        assert 'runmode' in data['operational']
    
    def test_stats_includes_security_info(self, client):
        """Test /stats includes security information."""
        response = client.get("/stats")
        
        assert response.status_code == 200
        data = response.json()
        
        assert 'security' in data
        assert 'require_hmac' in data['security']
        assert 'rate_limit_per_minute' in data['security']
