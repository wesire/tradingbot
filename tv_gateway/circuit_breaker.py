"""
Circuit breaker pattern for bot execution failures.
Opens circuit after N failures in M minutes, preventing cascading failures.
"""
import time
from typing import Optional, Dict
from datetime import datetime, timedelta
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    """Circuit breaker states."""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Circuit is open, rejecting requests
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreaker:
    """
    Circuit breaker for bot execution failures.
    
    Prevents cascading failures by temporarily stopping execution attempts
    when the bot is consistently failing.
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        window_seconds: int = 300,
        cooldown_seconds: int = 60,
        half_open_attempts: int = 3
    ):
        """
        Initialize circuit breaker.
        
        Args:
            failure_threshold: Number of failures to open circuit
            window_seconds: Time window for counting failures
            cooldown_seconds: Cooldown before trying half-open
            half_open_attempts: Success attempts needed to close from half-open
        """
        self.failure_threshold = failure_threshold
        self.window_seconds = window_seconds
        self.cooldown_seconds = cooldown_seconds
        self.half_open_attempts = half_open_attempts
        
        self.state = CircuitState.CLOSED
        self.failure_times = []
        self.opened_at = None
        self.half_open_successes = 0
        
        logger.info(
            f"CircuitBreaker initialized: threshold={failure_threshold} "
            f"failures in {window_seconds}s, cooldown={cooldown_seconds}s"
        )
    
    def _clean_old_failures(self):
        """Remove failures outside the time window."""
        now = time.time()
        cutoff = now - self.window_seconds
        
        self.failure_times = [
            t for t in self.failure_times
            if t > cutoff
        ]
    
    def record_success(self):
        """Record a successful execution."""
        if self.state == CircuitState.HALF_OPEN:
            self.half_open_successes += 1
            
            if self.half_open_successes >= self.half_open_attempts:
                # Close the circuit
                self._close_circuit()
        
        elif self.state == CircuitState.CLOSED:
            # Clean up old failures on success
            self._clean_old_failures()
    
    def record_failure(self):
        """Record a failed execution."""
        now = time.time()
        
        if self.state == CircuitState.HALF_OPEN:
            # Failure during half-open - reopen circuit
            logger.warning("Failure during half-open, reopening circuit")
            self._open_circuit()
        
        elif self.state == CircuitState.CLOSED:
            # Add failure and check threshold
            self.failure_times.append(now)
            self._clean_old_failures()
            
            if len(self.failure_times) >= self.failure_threshold:
                self._open_circuit()
    
    def _open_circuit(self):
        """Open the circuit."""
        self.state = CircuitState.OPEN
        self.opened_at = time.time()
        self.half_open_successes = 0
        
        logger.error(
            f"Circuit breaker OPENED: {len(self.failure_times)} failures "
            f"in {self.window_seconds}s window"
        )
    
    def _close_circuit(self):
        """Close the circuit."""
        self.state = CircuitState.CLOSED
        self.opened_at = None
        self.half_open_successes = 0
        self.failure_times = []
        
        logger.info("Circuit breaker CLOSED: service recovered")
    
    def _try_half_open(self):
        """Transition to half-open state."""
        self.state = CircuitState.HALF_OPEN
        self.half_open_successes = 0
        
        logger.info("Circuit breaker HALF-OPEN: testing recovery")
    
    def is_request_allowed(self) -> tuple[bool, Optional[str]]:
        """
        Check if execution request should be allowed.
        
        Returns:
            Tuple of (is_allowed, reason)
        """
        if self.state == CircuitState.CLOSED:
            return True, None
        
        elif self.state == CircuitState.HALF_OPEN:
            # Allow limited requests in half-open state
            return True, None
        
        elif self.state == CircuitState.OPEN:
            # Check if cooldown period has passed
            if self.opened_at:
                elapsed = time.time() - self.opened_at
                
                if elapsed >= self.cooldown_seconds:
                    # Try half-open
                    self._try_half_open()
                    return True, None
                else:
                    remaining = int(self.cooldown_seconds - elapsed)
                    reason = (
                        f"Circuit breaker open (bot unavailable), "
                        f"retry in {remaining}s"
                    )
                    return False, reason
            
            return False, "Circuit breaker open (bot unavailable)"
        
        return False, "Unknown circuit state"
    
    def force_reset(self):
        """Force reset circuit to closed state (admin action)."""
        logger.warning("Circuit breaker force reset by admin")
        self._close_circuit()
    
    def get_status(self) -> Dict:
        """Get circuit breaker status."""
        self._clean_old_failures()
        
        status = {
            "state": self.state,
            "failure_count": len(self.failure_times),
            "failure_threshold": self.failure_threshold,
            "window_seconds": self.window_seconds,
        }
        
        if self.state == CircuitState.OPEN and self.opened_at:
            elapsed = time.time() - self.opened_at
            remaining = max(0, int(self.cooldown_seconds - elapsed))
            status["opened_at"] = datetime.fromtimestamp(self.opened_at).isoformat()
            status["cooldown_remaining_seconds"] = remaining
        
        if self.state == CircuitState.HALF_OPEN:
            status["half_open_successes"] = self.half_open_successes
            status["half_open_required"] = self.half_open_attempts
        
        return status
