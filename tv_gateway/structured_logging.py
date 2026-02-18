"""
Structured JSON logging for security and audit trails.
"""
import json
import logging
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class StructuredLogger:
    """
    Structured logging for security and operational events.
    Produces JSON log lines for easy parsing and analysis.
    """
    
    def __init__(self, name: str = "webhook_audit"):
        """
        Initialize structured logger.
        
        Args:
            name: Logger name
        """
        self.logger = logging.getLogger(name)
    
    def _log_event(self, level: str, event_type: str, data: Dict[str, Any]):
        """
        Log a structured event.
        
        Args:
            level: Log level (info, warning, error)
            event_type: Type of event
            data: Event data
        """
        # Build structured log entry
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            **data
        }
        
        # Convert to JSON (single line)
        log_line = json.dumps(log_entry)
        
        # Log at appropriate level
        if level == "info":
            self.logger.info(log_line)
        elif level == "warning":
            self.logger.warning(log_line)
        elif level == "error":
            self.logger.error(log_line)
    
    def log_request_accepted(
        self,
        alert_id: int,
        symbol: str,
        side: str,
        setup_id: str,
        confidence: float,
        client_ip: str,
        auth_method: str,
        idempotency_key: str
    ):
        """Log successful request acceptance."""
        self._log_event("info", "request_accepted", {
            "alert_id": alert_id,
            "symbol": symbol,
            "side": side,
            "setup_id": setup_id,
            "confidence": confidence,
            "client_ip": client_ip,
            "auth_method": auth_method,
            "idempotency_key": idempotency_key
        })
    
    def log_request_rejected(
        self,
        reason: str,
        client_ip: str,
        symbol: Optional[str] = None,
        nonce: Optional[str] = None
    ):
        """Log rejected request."""
        self._log_event("warning", "request_rejected", {
            "reason": reason,
            "client_ip": client_ip,
            "symbol": symbol,
            "nonce": nonce
        })
    
    def log_rate_limit(self, client_ip: str, retry_after: int):
        """Log rate limit event."""
        self._log_event("warning", "rate_limit_exceeded", {
            "client_ip": client_ip,
            "retry_after_seconds": retry_after
        })
    
    def log_replay_detected(self, nonce: str, client_ip: str):
        """Log replay attack detection."""
        self._log_event("warning", "replay_detected", {
            "nonce": nonce,
            "client_ip": client_ip
        })
    
    def log_ip_blocked(self, client_ip: str, reason: str):
        """Log IP blocked by filter."""
        self._log_event("warning", "ip_blocked", {
            "client_ip": client_ip,
            "reason": reason
        })
    
    def log_status_transition(
        self,
        alert_id: int,
        old_status: str,
        new_status: str,
        symbol: str,
        side: str,
        setup_id: str,
        reason: Optional[str] = None,
        execution_ref: Optional[str] = None
    ):
        """Log alert status transition."""
        self._log_event("info", "status_transition", {
            "alert_id": alert_id,
            "old_status": old_status,
            "new_status": new_status,
            "symbol": symbol,
            "side": side,
            "setup_id": setup_id,
            "reason": reason,
            "execution_ref": execution_ref
        })
    
    def log_circuit_state_change(self, old_state: str, new_state: str, reason: str):
        """Log circuit breaker state change."""
        self._log_event("warning", "circuit_state_change", {
            "old_state": old_state,
            "new_state": new_state,
            "reason": reason
        })
    
    def log_kill_switch(self, switch_name: str, enabled: bool):
        """Log kill switch activation/deactivation."""
        self._log_event("warning", "kill_switch", {
            "switch_name": switch_name,
            "enabled": enabled
        })
    
    def log_hmac_verification(
        self,
        success: bool,
        nonce: str,
        client_ip: str,
        reason: Optional[str] = None
    ):
        """Log HMAC signature verification."""
        level = "info" if success else "warning"
        self._log_event(level, "hmac_verification", {
            "success": success,
            "nonce": nonce,
            "client_ip": client_ip,
            "reason": reason
        })


# Global structured logger instance
audit_logger = StructuredLogger("webhook_audit")
