"""
Authentication and security for TradingView webhook gateway.
"""
from typing import Tuple, Optional, Set
from datetime import datetime, timedelta
from collections import deque
import hashlib
import hmac


class WebhookAuth:
    """Authentication and security validation for webhooks."""
    
    def __init__(
        self,
        shared_secret: str,
        max_age_seconds: int = 30,
        nonce_cache_size: int = 1000
    ):
        """
        Initialize webhook authentication.
        
        Args:
            shared_secret: Shared secret key for validation
            max_age_seconds: Maximum age of alerts in seconds
            nonce_cache_size: Size of nonce cache for replay prevention
        """
        self.shared_secret = shared_secret
        self.max_age_seconds = max_age_seconds
        
        # Nonce tracking for replay attack prevention
        self.nonce_cache: Set[str] = set()
        self.nonce_queue: deque = deque(maxlen=nonce_cache_size)
        
        # Rate limiting per IP
        self.request_history: dict = {}
        self.rate_limit_window = 60  # seconds
        self.rate_limit_max_requests = 30  # requests per window
    
    def validate_secret(self, received_secret: str) -> bool:
        """
        Validate shared secret using constant-time comparison.
        
        Args:
            received_secret: Secret from webhook payload
            
        Returns:
            True if secret is valid
        """
        if not self.shared_secret or not received_secret:
            return False
        
        # Use hmac.compare_digest for constant-time comparison
        return hmac.compare_digest(self.shared_secret, received_secret)
    
    def validate_timestamp(self, timestamp: int) -> Tuple[bool, str]:
        """
        Validate alert timestamp to reject stale alerts.
        
        Args:
            timestamp: Unix timestamp in seconds
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            alert_time = datetime.fromtimestamp(timestamp)
            current_time = datetime.now()
            
            # Check if alert is too old
            age = (current_time - alert_time).total_seconds()
            if age > self.max_age_seconds:
                return False, f"Alert too old: {age:.1f}s (max: {self.max_age_seconds}s)"
            
            # Check if alert is from the future (clock skew tolerance: 5 seconds)
            if age < -5:
                return False, "Alert timestamp is in the future"
            
            return True, "Timestamp valid"
            
        except (ValueError, OSError) as e:
            return False, f"Invalid timestamp: {e}"
    
    def validate_nonce(self, nonce: str) -> Tuple[bool, str]:
        """
        Validate nonce to prevent replay attacks.
        
        Args:
            nonce: Unique nonce from payload
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not nonce:
            return False, "Nonce is required"
        
        # Check if nonce has been used before
        if nonce in self.nonce_cache:
            return False, "Nonce has already been used (replay attack)"
        
        # Add to cache
        self.nonce_cache.add(nonce)
        self.nonce_queue.append(nonce)
        
        # Remove oldest nonce if cache is full
        if len(self.nonce_queue) == self.nonce_queue.maxlen:
            oldest = self.nonce_queue[0]
            if oldest in self.nonce_cache:
                self.nonce_cache.remove(oldest)
        
        return True, "Nonce valid"
    
    def check_rate_limit(self, client_ip: str) -> Tuple[bool, str]:
        """
        Check rate limit for client IP.
        
        Args:
            client_ip: Client IP address
            
        Returns:
            Tuple of (is_allowed, error_message)
        """
        current_time = datetime.now()
        
        # Initialize tracking for new IPs
        if client_ip not in self.request_history:
            self.request_history[client_ip] = []
        
        # Clean old requests outside the window
        window_start = current_time - timedelta(seconds=self.rate_limit_window)
        self.request_history[client_ip] = [
            req_time for req_time in self.request_history[client_ip]
            if req_time > window_start
        ]
        
        # Check if rate limit exceeded
        request_count = len(self.request_history[client_ip])
        if request_count >= self.rate_limit_max_requests:
            return False, f"Rate limit exceeded: {request_count}/{self.rate_limit_max_requests} requests in {self.rate_limit_window}s"
        
        # Add current request
        self.request_history[client_ip].append(current_time)
        
        return True, "Rate limit OK"
    
    def validate_all(
        self,
        secret: str,
        timestamp: int,
        nonce: str,
        client_ip: str
    ) -> Tuple[bool, str]:
        """
        Validate all security checks.
        
        Args:
            secret: Shared secret from payload
            timestamp: Unix timestamp
            nonce: Unique nonce
            client_ip: Client IP address
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check rate limit first
        rate_ok, rate_msg = self.check_rate_limit(client_ip)
        if not rate_ok:
            return False, rate_msg
        
        # Validate secret
        if not self.validate_secret(secret):
            return False, "Invalid secret"
        
        # Validate timestamp
        ts_ok, ts_msg = self.validate_timestamp(timestamp)
        if not ts_ok:
            return False, ts_msg
        
        # Validate nonce
        nonce_ok, nonce_msg = self.validate_nonce(nonce)
        if not nonce_ok:
            return False, nonce_msg
        
        return True, "All validations passed"
    
    def clear_nonce_cache(self):
        """Clear nonce cache (for testing)."""
        self.nonce_cache.clear()
        self.nonce_queue.clear()
    
    def clear_rate_limit_history(self):
        """Clear rate limit history (for testing)."""
        self.request_history.clear()
