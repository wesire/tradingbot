"""
Rate limiting middleware for webhook endpoints.
Uses token bucket algorithm for smooth rate limiting.
"""
import time
import threading
from typing import Dict, Optional, Tuple
from collections import defaultdict
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class TokenBucket:
    """Token bucket for rate limiting."""
    
    def __init__(self, capacity: int, refill_rate: float):
        """
        Initialize token bucket.
        
        Args:
            capacity: Maximum tokens (burst allowance)
            refill_rate: Tokens added per second
        """
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = capacity
        self.last_refill = time.time()
    
    def consume(self, tokens: int = 1) -> bool:
        """
        Attempt to consume tokens.
        
        Args:
            tokens: Number of tokens to consume
            
        Returns:
            True if tokens available, False if rate limited
        """
        # Refill tokens based on elapsed time
        now = time.time()
        elapsed = now - self.last_refill
        
        # Add tokens based on refill rate
        self.tokens = min(
            self.capacity,
            self.tokens + (elapsed * self.refill_rate)
        )
        self.last_refill = now
        
        # Check if enough tokens
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        
        return False
    
    def get_retry_after(self) -> int:
        """
        Calculate seconds until next token available.
        
        Returns:
            Seconds to wait
        """
        if self.tokens >= 1:
            return 0
        
        # Calculate time to refill 1 token
        tokens_needed = 1 - self.tokens
        seconds = tokens_needed / self.refill_rate
        
        return max(1, int(seconds) + 1)


class RateLimiter:
    """
    IP-based rate limiter with token bucket algorithm.
    """
    
    def __init__(
        self,
        requests_per_minute: int = 30,
        burst_multiplier: float = 1.5
    ):
        """
        Initialize rate limiter.
        
        Args:
            requests_per_minute: Base rate limit per IP
            burst_multiplier: Burst capacity multiplier
        """
        self._lock = threading.Lock()
        self.requests_per_minute = requests_per_minute
        self.burst_capacity = int(requests_per_minute * burst_multiplier)
        self.refill_rate = requests_per_minute / 60.0  # tokens per second
        
        # Buckets per IP
        self.buckets: Dict[str, TokenBucket] = {}
        
        # Last cleanup time
        self.last_cleanup = time.time()
        self.cleanup_interval = 300  # 5 minutes
        
        logger.info(
            f"RateLimiter initialized: {requests_per_minute} req/min, "
            f"burst={self.burst_capacity}, refill={self.refill_rate:.2f}/s"
        )

    def reconfigure(self, requests_per_minute: int) -> None:
        """Atomically update the rate limit and clear all existing buckets.

        This is intended for runtime config changes (e.g. reading an updated
        env var).  The new ``burst_capacity`` is set equal to
        ``requests_per_minute`` (strict 1:1, no burst) so that exactly
        *requests_per_minute* requests can be made before the limit fires.

        Args:
            requests_per_minute: New base rate limit per IP.
        """
        with self._lock:
            if requests_per_minute == self.requests_per_minute:
                return
            self.requests_per_minute = requests_per_minute
            self.burst_capacity = requests_per_minute  # strict limit, no burst
            self.refill_rate = requests_per_minute / 60.0
            self.buckets.clear()
            logger.info(
                f"RateLimiter reconfigured: {requests_per_minute} req/min "
                f"(strict, no burst)"
            )

    def _get_bucket(self, client_ip: str) -> TokenBucket:
        """Get or create token bucket for IP."""
        if client_ip not in self.buckets:
            self.buckets[client_ip] = TokenBucket(
                capacity=self.burst_capacity,
                refill_rate=self.refill_rate
            )
        
        return self.buckets[client_ip]
    
    def check_rate_limit(self, client_ip: str) -> Tuple[bool, Optional[int]]:
        """
        Check if request is allowed under rate limit.
        
        Args:
            client_ip: Client IP address
            
        Returns:
            Tuple of (is_allowed, retry_after_seconds)
        """
        # Periodic cleanup of old buckets
        self._cleanup_old_buckets()
        
        # Get bucket for this IP
        bucket = self._get_bucket(client_ip)
        
        # Try to consume a token
        allowed = bucket.consume(1)
        
        if not allowed:
            retry_after = bucket.get_retry_after()
            logger.warning(
                f"Rate limit exceeded for {client_ip}, "
                f"retry_after={retry_after}s"
            )
            return False, retry_after
        
        return True, None
    
    def _cleanup_old_buckets(self):
        """Remove buckets for IPs that haven't been seen recently."""
        now = time.time()
        
        if now - self.last_cleanup < self.cleanup_interval:
            return
        
        # Remove buckets that are at full capacity (inactive)
        inactive_ips = [
            ip for ip, bucket in self.buckets.items()
            if bucket.tokens >= bucket.capacity * 0.99
        ]
        
        for ip in inactive_ips:
            del self.buckets[ip]
        
        if inactive_ips:
            logger.info(f"Cleaned up {len(inactive_ips)} inactive rate limit buckets")
        
        self.last_cleanup = now
    
    def get_stats(self) -> Dict:
        """Get rate limiter statistics."""
        return {
            "active_ips": len(self.buckets),
            "requests_per_minute": self.requests_per_minute,
            "burst_capacity": self.burst_capacity,
            "buckets": {
                ip: {
                    "tokens": round(bucket.tokens, 2),
                    "capacity": bucket.capacity
                }
                for ip, bucket in list(self.buckets.items())[:10]  # Show first 10
            }
        }
    
    def reset(self):
        """Reset all buckets (for testing)."""
        self.buckets.clear()
        logger.info("Rate limiter reset")
