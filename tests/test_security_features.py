"""
Unit tests for Phase 2.1 security features.
Tests HMAC authentication, rate limiting, IP filtering, circuit breaker, and nonce storage.
"""
import pytest
import time
import hmac
import hashlib
from datetime import datetime

from tv_gateway.hmac_auth import HMACAuthenticator
from tv_gateway.rate_limiter import RateLimiter
from tv_gateway.ip_filter import IPFilter
from tv_gateway.circuit_breaker import CircuitBreaker, CircuitState
from tv_gateway.nonce_storage import NonceStorage


class TestHMACAuthenticator:
    """Tests for HMAC authentication."""
    
    def test_hmac_signature_valid(self):
        """Test valid HMAC signature verification."""
        secret = "test_secret"
        authenticator = HMACAuthenticator(secret, skew_seconds=60)
        
        timestamp = str(int(time.time()))
        nonce = "test_nonce_123"
        body = b'{"symbol":"BTCUSDT","side":"long"}'
        
        # Generate signature
        message = f"{timestamp}.{nonce}.".encode('utf-8') + body
        signature = hmac.new(secret.encode('utf-8'), message, hashlib.sha256).hexdigest()
        
        # Verify
        is_valid, error = authenticator.verify_signature(timestamp, nonce, body, signature)
        
        assert is_valid is True
        assert error is None
    
    def test_hmac_signature_invalid(self):
        """Test invalid HMAC signature rejection."""
        secret = "test_secret"
        authenticator = HMACAuthenticator(secret, skew_seconds=60)
        
        timestamp = str(int(time.time()))
        nonce = "test_nonce_123"
        body = b'{"symbol":"BTCUSDT","side":"long"}'
        
        # Wrong signature
        wrong_signature = "0" * 64
        
        is_valid, error = authenticator.verify_signature(timestamp, nonce, body, wrong_signature)
        
        assert is_valid is False
        assert "Invalid HMAC signature" in error
    
    def test_timestamp_within_skew(self):
        """Test timestamp within acceptable skew window."""
        authenticator = HMACAuthenticator("secret", skew_seconds=60)
        
        # Current timestamp
        timestamp = str(int(time.time()))
        
        is_valid, error = authenticator.verify_timestamp(timestamp)
        
        assert is_valid is True
        assert error is None
    
    def test_timestamp_outside_skew(self):
        """Test timestamp outside skew window is rejected."""
        authenticator = HMACAuthenticator("secret", skew_seconds=60)
        
        # Old timestamp (2 minutes ago)
        timestamp = str(int(time.time()) - 120)
        
        is_valid, error = authenticator.verify_timestamp(timestamp)
        
        assert is_valid is False
        assert "outside skew window" in error
    
    def test_hmac_request_complete_valid(self):
        """Test complete HMAC request validation."""
        secret = "test_secret"
        authenticator = HMACAuthenticator(secret, skew_seconds=60, require_hmac=True)
        
        timestamp = str(int(time.time()))
        nonce = "test_nonce_123"
        body = b'{"test":"data"}'
        
        # Generate valid signature
        message = f"{timestamp}.{nonce}.".encode('utf-8') + body
        signature = hmac.new(secret.encode('utf-8'), message, hashlib.sha256).hexdigest()
        
        is_valid, error, used_hmac = authenticator.verify_hmac_request(
            timestamp, nonce, body, signature
        )
        
        assert is_valid is True
        assert error is None
        assert used_hmac is True
    
    def test_hmac_request_missing_when_required(self):
        """Test HMAC required but headers missing."""
        authenticator = HMACAuthenticator("secret", require_hmac=True)
        
        is_valid, error, used_hmac = authenticator.verify_hmac_request(
            None, None, b'{"test":"data"}', None
        )
        
        assert is_valid is False
        assert "HMAC signature required" in error
        assert used_hmac is False
    
    def test_hmac_request_optional_skipped(self):
        """Test HMAC optional and headers not provided - should pass."""
        authenticator = HMACAuthenticator("secret", require_hmac=False)
        
        is_valid, error, used_hmac = authenticator.verify_hmac_request(
            None, None, b'{"test":"data"}', None
        )
        
        assert is_valid is True
        assert error is None
        assert used_hmac is False


class TestRateLimiter:
    """Tests for rate limiter."""
    
    def test_rate_limit_within_limit(self):
        """Test requests within rate limit are allowed."""
        limiter = RateLimiter(requests_per_minute=10)
        
        # 5 requests should be allowed
        for _ in range(5):
            allowed, retry_after = limiter.check_rate_limit("192.168.1.1")
            assert allowed is True
            assert retry_after is None
    
    def test_rate_limit_exceeded(self):
        """Test rate limit exceeded returns 429."""
        limiter = RateLimiter(requests_per_minute=5, burst_multiplier=1.0)
        
        # Use up all tokens
        for _ in range(5):
            allowed, _ = limiter.check_rate_limit("192.168.1.1")
            assert allowed is True
        
        # Next request should be rate limited
        allowed, retry_after = limiter.check_rate_limit("192.168.1.1")
        
        assert allowed is False
        assert retry_after is not None
        assert retry_after > 0
    
    def test_rate_limit_per_ip(self):
        """Test rate limiting is per-IP."""
        limiter = RateLimiter(requests_per_minute=5, burst_multiplier=1.0)
        
        # IP 1 uses up its limit
        for _ in range(5):
            allowed, _ = limiter.check_rate_limit("192.168.1.1")
            assert allowed is True
        
        # IP 1 should be rate limited
        allowed, _ = limiter.check_rate_limit("192.168.1.1")
        assert allowed is False
        
        # IP 2 should still be allowed
        allowed, _ = limiter.check_rate_limit("192.168.1.2")
        assert allowed is True
    
    def test_rate_limit_burst(self):
        """Test burst capacity allows temporary spikes."""
        limiter = RateLimiter(requests_per_minute=10, burst_multiplier=2.0)
        
        # Should allow burst of 20 requests initially
        for _ in range(20):
            allowed, _ = limiter.check_rate_limit("192.168.1.1")
            assert allowed is True
        
        # 21st should be limited
        allowed, _ = limiter.check_rate_limit("192.168.1.1")
        assert allowed is False


class TestIPFilter:
    """Tests for IP filtering."""
    
    def test_ip_allowed_no_filters(self):
        """Test IP allowed when no filters configured."""
        filter = IPFilter()
        
        allowed, reason = filter.is_allowed("192.168.1.1")
        
        assert allowed is True
        assert reason is None
    
    def test_ip_in_allowlist(self):
        """Test IP in allowlist is allowed."""
        filter = IPFilter(allowlist=["192.168.1.0/24"])
        
        allowed, reason = filter.is_allowed("192.168.1.100")
        
        assert allowed is True
        assert reason is None
    
    def test_ip_not_in_allowlist(self):
        """Test IP not in allowlist is blocked."""
        filter = IPFilter(allowlist=["192.168.1.0/24"])
        
        allowed, reason = filter.is_allowed("10.0.0.1")
        
        assert allowed is False
        assert "not in allowlist" in reason
    
    def test_ip_in_denylist(self):
        """Test IP in denylist is blocked."""
        filter = IPFilter(denylist=["10.0.0.0/8"])
        
        allowed, reason = filter.is_allowed("10.0.0.1")
        
        assert allowed is False
        assert "in denylist" in reason
    
    def test_ip_denylist_overrides_allowlist(self):
        """Test denylist takes precedence over allowlist."""
        filter = IPFilter(
            allowlist=["192.168.0.0/16"],
            denylist=["192.168.1.0/24"]
        )
        
        # IP in both allowlist and denylist - should be blocked
        allowed, reason = filter.is_allowed("192.168.1.100")
        
        assert allowed is False
        assert "in denylist" in reason
    
    def test_extract_client_ip_no_proxy(self):
        """Test client IP extraction without proxy."""
        filter = IPFilter()
        
        ip = filter.extract_client_ip("192.168.1.1", None)
        
        assert ip == "192.168.1.1"
    
    def test_extract_client_ip_untrusted_proxy(self):
        """Test X-Forwarded-For ignored from untrusted proxy."""
        filter = IPFilter(trusted_proxies=["10.0.0.0/8"])
        
        # Request from untrusted proxy
        ip = filter.extract_client_ip("192.168.1.1", "1.2.3.4, 192.168.1.1")
        
        # Should ignore forwarded header
        assert ip == "192.168.1.1"
    
    def test_extract_client_ip_trusted_proxy(self):
        """Test X-Forwarded-For trusted from configured proxy."""
        filter = IPFilter(trusted_proxies=["10.0.0.0/8"])
        
        # Request from trusted proxy
        ip = filter.extract_client_ip("10.0.0.1", "1.2.3.4, 10.0.0.1")
        
        # Should use leftmost IP from forwarded header
        assert ip == "1.2.3.4"


class TestCircuitBreaker:
    """Tests for circuit breaker."""
    
    def test_circuit_breaker_closed_initially(self):
        """Test circuit breaker starts in closed state."""
        breaker = CircuitBreaker(failure_threshold=3, window_seconds=60)
        
        assert breaker.state == CircuitState.CLOSED
    
    def test_circuit_breaker_opens_on_failures(self):
        """Test circuit opens after threshold failures."""
        breaker = CircuitBreaker(failure_threshold=3, window_seconds=60)
        
        # Record failures
        for _ in range(3):
            breaker.record_failure()
        
        assert breaker.state == CircuitState.OPEN
    
    def test_circuit_breaker_blocks_when_open(self):
        """Test circuit blocks requests when open."""
        breaker = CircuitBreaker(failure_threshold=2, window_seconds=60)
        
        # Open the circuit
        breaker.record_failure()
        breaker.record_failure()
        
        assert breaker.state == CircuitState.OPEN
        
        # Should block requests
        allowed, reason = breaker.is_request_allowed()
        
        assert allowed is False
        assert "circuit breaker open" in reason.lower()
    
    def test_circuit_breaker_half_open_after_cooldown(self):
        """Test circuit transitions to half-open after cooldown."""
        breaker = CircuitBreaker(
            failure_threshold=2,
            window_seconds=60,
            cooldown_seconds=1  # 1 second cooldown for test
        )
        
        # Open circuit
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN
        
        # Wait for cooldown
        time.sleep(1.1)
        
        # Next request should transition to half-open
        allowed, reason = breaker.is_request_allowed()
        
        assert breaker.state == CircuitState.HALF_OPEN
        assert allowed is True
    
    def test_circuit_breaker_closes_on_success(self):
        """Test circuit closes after successful half-open attempts."""
        breaker = CircuitBreaker(
            failure_threshold=2,
            window_seconds=60,
            cooldown_seconds=0,
            half_open_attempts=2
        )
        
        # Open circuit
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN
        
        # Transition to half-open
        breaker._try_half_open()
        
        # Record successes
        breaker.record_success()
        assert breaker.state == CircuitState.HALF_OPEN
        
        breaker.record_success()
        assert breaker.state == CircuitState.CLOSED
    
    def test_circuit_breaker_reopens_on_half_open_failure(self):
        """Test circuit reopens if half-open attempt fails."""
        breaker = CircuitBreaker(
            failure_threshold=2,
            window_seconds=60,
            cooldown_seconds=0
        )
        
        # Open circuit then half-open
        breaker.record_failure()
        breaker.record_failure()
        breaker._try_half_open()
        assert breaker.state == CircuitState.HALF_OPEN
        
        # Failure in half-open
        breaker.record_failure()
        
        assert breaker.state == CircuitState.OPEN
    
    def test_circuit_breaker_force_reset(self):
        """Test admin force reset."""
        breaker = CircuitBreaker(failure_threshold=2, window_seconds=60)
        
        # Open circuit
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN
        
        # Force reset
        breaker.force_reset()
        
        assert breaker.state == CircuitState.CLOSED


class TestNonceStorage:
    """Tests for nonce storage."""
    
    @pytest.fixture
    def nonce_storage(self, tmp_path):
        """Create temporary nonce storage."""
        db_path = tmp_path / "test_nonces.db"
        return NonceStorage(str(db_path), ttl_seconds=10)
    
    def test_nonce_first_use_allowed(self, nonce_storage):
        """Test first use of nonce is allowed."""
        is_new, error = nonce_storage.check_and_store("nonce_123", "1234567890")
        
        assert is_new is True
        assert error is None
    
    def test_nonce_replay_blocked(self, nonce_storage):
        """Test replay of nonce is blocked."""
        # First use
        is_new, error = nonce_storage.check_and_store("nonce_123", "1234567890")
        assert is_new is True
        
        # Replay attempt
        is_new, error = nonce_storage.check_and_store("nonce_123", "1234567890")
        
        assert is_new is False
        assert "replay attack" in error
    
    def test_nonce_cleanup_expired(self, nonce_storage):
        """Test expired nonces are cleaned up."""
        # Store nonce
        nonce_storage.check_and_store("nonce_old", "1234567890")
        
        # Verify it exists
        count_before = nonce_storage.count_nonces()
        assert count_before == 1
        
        # Wait for expiry (TTL is 10 seconds in fixture)
        time.sleep(11)
        
        # Cleanup
        deleted = nonce_storage.cleanup_expired()
        
        assert deleted == 1
        assert nonce_storage.count_nonces() == 0
    
    def test_nonce_storage_persistence(self, tmp_path):
        """Test nonces persist across restarts."""
        db_path = tmp_path / "test_persist.db"
        
        # First instance
        storage1 = NonceStorage(str(db_path), ttl_seconds=600)
        storage1.check_and_store("nonce_persist", "1234567890")
        
        # Second instance (simulating restart)
        storage2 = NonceStorage(str(db_path), ttl_seconds=600)
        
        # Should still detect replay
        is_new, error = storage2.check_and_store("nonce_persist", "1234567890")
        
        assert is_new is False
        assert "replay attack" in error
