"""
HMAC-based authentication for webhook requests.
Provides cryptographic signature verification to prevent tampering.
"""
import hmac
import hashlib
import time
from typing import Tuple, Optional
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class HMACAuthenticator:
    """HMAC signature verification for webhook requests."""
    
    def __init__(
        self,
        shared_secret: str,
        skew_seconds: int = 60,
        require_hmac: bool = False
    ):
        """
        Initialize HMAC authenticator.
        
        Args:
            shared_secret: Shared secret for HMAC signing
            skew_seconds: Maximum timestamp skew in seconds
            require_hmac: Whether HMAC is required (vs optional)
        """
        self.shared_secret = shared_secret.encode('utf-8')
        self.skew_seconds = skew_seconds
        self.require_hmac = require_hmac
    
    def verify_signature(
        self,
        timestamp: str,
        nonce: str,
        body: bytes,
        signature: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Verify HMAC signature.
        
        Signature format: HMAC-SHA256(secret, "{timestamp}.{nonce}.{raw_body}")
        
        Args:
            timestamp: Unix timestamp as string
            nonce: Unique nonce string
            body: Raw request body bytes
            signature: Hex-encoded HMAC signature
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # Build message to sign
            message = f"{timestamp}.{nonce}.".encode('utf-8') + body
            
            # Calculate expected signature
            expected_sig = hmac.new(
                self.shared_secret,
                message,
                hashlib.sha256
            ).hexdigest()
            
            # Constant-time comparison
            is_valid = hmac.compare_digest(signature, expected_sig)
            
            if not is_valid:
                logger.warning(f"HMAC signature mismatch for nonce={nonce}")
                return False, "Invalid HMAC signature"
            
            logger.debug(f"HMAC signature verified for nonce={nonce}")
            return True, None
            
        except Exception as e:
            logger.error(f"HMAC verification error: {e}")
            return False, f"HMAC verification failed: {str(e)}"
    
    def verify_timestamp(self, timestamp: str) -> Tuple[bool, Optional[str]]:
        """
        Verify timestamp is within acceptable skew window.
        
        Args:
            timestamp: Unix timestamp as string (seconds)
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # Parse timestamp
            ts = int(timestamp)
            ts_datetime = datetime.fromtimestamp(ts)
            
            # Check skew
            now = datetime.now()
            age = abs((now - ts_datetime).total_seconds())
            
            if age > self.skew_seconds:
                return False, f"Timestamp outside skew window: {age:.1f}s > {self.skew_seconds}s"
            
            return True, None
            
        except (ValueError, OSError) as e:
            return False, f"Invalid timestamp: {e}"
    
    def verify_hmac_request(
        self,
        timestamp: Optional[str],
        nonce: Optional[str],
        body: bytes,
        signature: Optional[str]
    ) -> Tuple[bool, Optional[str], bool]:
        """
        Verify complete HMAC request.
        
        Args:
            timestamp: X-TV-Timestamp header value
            nonce: X-TV-Nonce header value  
            body: Raw request body
            signature: X-TV-Signature header value
            
        Returns:
            Tuple of (is_valid, error_message, used_hmac)
            - is_valid: Whether authentication passed
            - error_message: Error message if validation failed
            - used_hmac: Whether HMAC was attempted (vs skipped)
        """
        # Check if HMAC headers are provided
        has_hmac_headers = all([timestamp, nonce, signature])
        
        if self.require_hmac and not has_hmac_headers:
            return False, "HMAC signature required but headers missing", False
        
        if not has_hmac_headers:
            # HMAC not required and headers not provided - skip HMAC validation
            return True, None, False
        
        # Validate timestamp
        ts_valid, ts_msg = self.verify_timestamp(timestamp)
        if not ts_valid:
            return False, ts_msg, True
        
        # Verify signature
        sig_valid, sig_msg = self.verify_signature(timestamp, nonce, body, signature)
        if not sig_valid:
            return False, sig_msg, True
        
        return True, None, True
