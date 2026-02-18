"""
Background execution worker that processes queued alerts.
Phase 2.1: Integrated with circuit breaker and kill switches.
"""
import asyncio
from typing import Optional, List
from datetime import datetime, timedelta
import logging
import os

from tv_gateway.alert_storage import AlertStorage, Alert, AlertStatus
from tv_gateway.bot_client import BotClient, Signal, ExecutionStatus, create_bot_client
from tv_gateway.circuit_breaker import CircuitBreaker
from tv_gateway.structured_logging import audit_logger

logger = logging.getLogger(__name__)


class ExecutionWorker:
    """Background worker for processing queued alerts."""
    
    def __init__(
        self,
        storage: AlertStorage,
        bot_client: BotClient,
        circuit_breaker: Optional[CircuitBreaker] = None,
        poll_interval: int = 2,
        max_alert_age: int = 600,
        min_confidence: float = 0.9,
        allowed_symbols: Optional[List[str]] = None,
        allowed_timeframes: Optional[List[str]] = None,
        execution_enabled: bool = True,
        get_execution_enabled_func: Optional[callable] = None
    ):
        """
        Initialize execution worker.
        
        Args:
            storage: Alert storage instance
            bot_client: Bot client for execution
            circuit_breaker: Circuit breaker instance (Phase 2.1)
            poll_interval: Polling interval in seconds
            max_alert_age: Maximum alert age in seconds
            min_confidence: Minimum confidence threshold
            allowed_symbols: List of allowed symbols (None = all allowed)
            allowed_timeframes: List of allowed timeframes (None = all allowed)
            execution_enabled: Enable actual execution (False = dry-run only)
            get_execution_enabled_func: Function to get current execution_enabled state
        """
        self.storage = storage
        self.bot_client = bot_client
        self.circuit_breaker = circuit_breaker
        self.poll_interval = poll_interval
        self.max_alert_age = max_alert_age
        self.min_confidence = min_confidence
        self.allowed_symbols = allowed_symbols or []
        self.allowed_timeframes = allowed_timeframes or []
        self.get_execution_enabled = get_execution_enabled_func
        
        # Use initial execution_enabled if no dynamic func provided
        if not self.get_execution_enabled:
            self.execution_enabled = execution_enabled
        self.execution_enabled = execution_enabled
        
        self._running = False
        
        logger.info(
            f"Initialized ExecutionWorker: "
            f"max_age={max_alert_age}s, min_confidence={min_confidence}, "
            f"allowed_symbols={allowed_symbols}, allowed_timeframes={allowed_timeframes}, "
            f"execution_enabled={execution_enabled}"
        )
    
    def _check_freshness(self, alert: Alert) -> tuple[bool, Optional[str]]:
        """
        Check if alert is fresh enough to execute.
        
        Args:
            alert: Alert to check
            
        Returns:
            Tuple of (is_fresh, fail_reason)
        """
        try:
            received_time = datetime.fromisoformat(alert.received_at)
            current_time = datetime.now()
            age = (current_time - received_time).total_seconds()
            
            if age > self.max_alert_age:
                reason = f"Alert too old: {age:.1f}s > {self.max_alert_age}s"
                logger.info(f"Alert {alert.id} failed freshness check: {reason}")
                return False, reason
            
            return True, None
        
        except Exception as e:
            reason = f"Failed to parse timestamp: {e}"
            logger.error(f"Alert {alert.id} freshness check error: {reason}")
            return False, reason
    
    def _check_confidence(self, alert: Alert) -> tuple[bool, Optional[str]]:
        """
        Check if alert meets minimum confidence threshold.
        
        Args:
            alert: Alert to check
            
        Returns:
            Tuple of (passes, fail_reason)
        """
        if alert.confidence < self.min_confidence:
            reason = (
                f"Confidence too low: {alert.confidence} < {self.min_confidence}"
            )
            logger.info(f"Alert {alert.id} failed confidence check: {reason}")
            return False, reason
        
        return True, None
    
    def _check_symbol(self, alert: Alert) -> tuple[bool, Optional[str]]:
        """
        Check if symbol is in allowed list.
        
        Args:
            alert: Alert to check
            
        Returns:
            Tuple of (allowed, fail_reason)
        """
        if not self.allowed_symbols:
            # Empty list means all symbols allowed
            return True, None
        
        # Normalize symbol for comparison (remove all separators)
        normalized_symbol = alert.symbol.upper().replace('/', '').replace(':', '')
        
        for allowed in self.allowed_symbols:
            # Normalize allowed symbol
            normalized_allowed = allowed.upper().replace('/', '').replace(':', '')
            
            # Also try matching just the base part (before first separator)
            # E.g., "BTC/USDT:USDT" -> "BTC" matches "BTCUSDT" base "BTC"
            if ':' in allowed:
                # Format is like "BTC/USDT:USDT" - split on colon and take first part
                base_part = allowed.split(':')[0].upper().replace('/', '')
                if normalized_symbol.startswith(base_part) or normalized_symbol == base_part:
                    return True, None
            
            # Direct match after normalization
            if normalized_symbol == normalized_allowed:
                return True, None
        
        reason = f"Symbol not allowed: {alert.symbol} not in {self.allowed_symbols}"
        logger.info(f"Alert {alert.id} failed symbol check: {reason}")
        return False, reason
    
    def _check_timeframe(self, alert: Alert) -> tuple[bool, Optional[str]]:
        """
        Check if timeframe is in allowed list.
        
        Args:
            alert: Alert to check
            
        Returns:
            Tuple of (allowed, fail_reason)
        """
        if not self.allowed_timeframes:
            # Empty list means all timeframes allowed
            return True, None
        
        if alert.timeframe not in self.allowed_timeframes:
            reason = (
                f"Timeframe not allowed: {alert.timeframe} "
                f"not in {self.allowed_timeframes}"
            )
            logger.info(f"Alert {alert.id} failed timeframe check: {reason}")
            return False, reason
        
        return True, None
    
    def _apply_risk_gates(self, alert: Alert) -> tuple[bool, Optional[str]]:
        """
        Apply all risk gate checks.
        
        Args:
            alert: Alert to check
            
        Returns:
            Tuple of (passes, fail_reason)
        """
        # Check freshness
        passes, reason = self._check_freshness(alert)
        if not passes:
            return False, reason
        
        # Check confidence
        passes, reason = self._check_confidence(alert)
        if not passes:
            return False, reason
        
        # Check symbol
        passes, reason = self._check_symbol(alert)
        if not passes:
            return False, reason
        
        # Check timeframe
        passes, reason = self._check_timeframe(alert)
        if not passes:
            return False, reason
        
        return True, None
    
    def _process_alert(self, alert: Alert):
        """
        Process a single alert through risk gates and execution.
        Phase 2.1: Integrated with circuit breaker and dynamic execution flag.
        
        Args:
            alert: Alert to process
        """
        logger.info(
            f"Processing alert {alert.id}: {alert.symbol} {alert.side} "
            f"confidence={alert.confidence}"
        )
        
        # Apply risk gates
        passes, fail_reason = self._apply_risk_gates(alert)
        
        if not passes:
            # Update status to failed
            self.storage.update_status(
                alert_id=alert.id,
                status=AlertStatus.FAILED,
                fail_reason=fail_reason
            )
            logger.info(f"Alert {alert.id} rejected: {fail_reason}")
            
            audit_logger.log_status_transition(
                alert_id=alert.id,
                old_status="queued",
                new_status="failed",
                symbol=alert.symbol,
                side=alert.side,
                setup_id=alert.setup_id,
                reason=fail_reason
            )
            return
        
        # Check if execution is enabled (use dynamic func if provided)
        current_execution_enabled = (
            self.get_execution_enabled() if self.get_execution_enabled
            else self.execution_enabled
        )
        
        if not current_execution_enabled:
            logger.info(f"Alert {alert.id} passed gates but execution disabled")
            self.storage.update_status(
                alert_id=alert.id,
                status=AlertStatus.IGNORED,
                fail_reason="execution_disabled"
            )
            
            audit_logger.log_status_transition(
                alert_id=alert.id,
                old_status="queued",
                new_status="ignored",
                symbol=alert.symbol,
                side=alert.side,
                setup_id=alert.setup_id,
                reason="execution_disabled"
            )
            return
        
        # Check circuit breaker
        if self.circuit_breaker:
            allowed, circuit_reason = self.circuit_breaker.is_request_allowed()
            
            if not allowed:
                logger.warning(f"Alert {alert.id} blocked by circuit breaker: {circuit_reason}")
                self.storage.update_status(
                    alert_id=alert.id,
                    status=AlertStatus.FAILED,
                    fail_reason=circuit_reason
                )
                
                audit_logger.log_status_transition(
                    alert_id=alert.id,
                    old_status="queued",
                    new_status="failed",
                    symbol=alert.symbol,
                    side=alert.side,
                    setup_id=alert.setup_id,
                    reason=circuit_reason
                )
                return
        
        # Create signal
        signal = Signal(
            symbol=alert.symbol,
            side=alert.side,
            timeframe=alert.timeframe,
            setup_id=alert.setup_id,
            confidence=alert.confidence,
            price=alert.price
        )
        
        # Execute signal
        try:
            result = self.bot_client.execute_signal(signal)
            
            if result.status == ExecutionStatus.SUCCESS:
                # Record success in circuit breaker
                if self.circuit_breaker:
                    self.circuit_breaker.record_success()
                
                self.storage.update_status(
                    alert_id=alert.id,
                    status=AlertStatus.EXECUTED,
                    execution_ref=result.order_id
                )
                logger.info(
                    f"Alert {alert.id} executed successfully: "
                    f"order_id={result.order_id}"
                )
                
                audit_logger.log_status_transition(
                    alert_id=alert.id,
                    old_status="queued",
                    new_status="executed",
                    symbol=alert.symbol,
                    side=alert.side,
                    setup_id=alert.setup_id,
                    execution_ref=result.order_id
                )
            else:
                # Record failure in circuit breaker
                if self.circuit_breaker:
                    self.circuit_breaker.record_failure()
                
                self.storage.update_status(
                    alert_id=alert.id,
                    status=AlertStatus.FAILED,
                    fail_reason=result.message
                )
                logger.warning(
                    f"Alert {alert.id} execution failed: {result.message}"
                )
                
                audit_logger.log_status_transition(
                    alert_id=alert.id,
                    old_status="queued",
                    new_status="failed",
                    symbol=alert.symbol,
                    side=alert.side,
                    setup_id=alert.setup_id,
                    reason=result.message
                )
        
        except Exception as e:
            # Record failure in circuit breaker
            if self.circuit_breaker:
                self.circuit_breaker.record_failure()
            
            error_msg = f"Execution error: {e}"
            logger.error(f"Alert {alert.id} error: {error_msg}", exc_info=True)
            
            self.storage.update_status(
                alert_id=alert.id,
                status=AlertStatus.FAILED,
                fail_reason=error_msg
            )
            
            audit_logger.log_status_transition(
                alert_id=alert.id,
                old_status="queued",
                new_status="failed",
                symbol=alert.symbol,
                side=alert.side,
                setup_id=alert.setup_id,
                reason=error_msg
            )
    
    async def run(self):
        """Run the worker loop."""
        self._running = True
        logger.info("Execution worker started")
        
        while self._running:
            try:
                # Get queued alerts
                queued_alerts = self.storage.get_queued_alerts(limit=10)
                
                if queued_alerts:
                    logger.info(f"Processing {len(queued_alerts)} queued alerts")
                    
                    for alert in queued_alerts:
                        if not self._running:
                            break
                        
                        # Update status to queued (if accepted)
                        if alert.status == AlertStatus.ACCEPTED:
                            self.storage.update_status(
                                alert_id=alert.id,
                                status=AlertStatus.QUEUED
                            )
                        
                        # Process alert
                        self._process_alert(alert)
                
                # Wait before next poll
                await asyncio.sleep(self.poll_interval)
            
            except Exception as e:
                logger.error(f"Worker error: {e}", exc_info=True)
                await asyncio.sleep(self.poll_interval)
        
        logger.info("Execution worker stopped")
    
    def stop(self):
        """Stop the worker."""
        logger.info("Stopping execution worker...")
        self._running = False


def create_execution_worker(
    storage: AlertStorage,
    circuit_breaker: Optional[CircuitBreaker] = None,
    get_execution_enabled_func: Optional[callable] = None
) -> ExecutionWorker:
    """
    Factory function to create execution worker from environment config.
    Phase 2.1: Integrated with circuit breaker and dynamic execution flag.
    
    Args:
        storage: Alert storage instance
        circuit_breaker: Circuit breaker instance (optional)
        get_execution_enabled_func: Function to get current execution_enabled state
        
    Returns:
        ExecutionWorker instance
    """
    # Load configuration from environment
    max_alert_age = int(os.getenv("ALERT_MAX_AGE_SECONDS", "600"))
    min_confidence = float(os.getenv("MIN_CONFIDENCE", "0.9"))
    
    # Parse allowed symbols
    allowed_symbols_str = os.getenv("ALLOWED_SYMBOLS", "BTC/USDT:USDT")
    allowed_symbols = [
        s.strip() for s in allowed_symbols_str.split(',') if s.strip()
    ]
    
    # Parse allowed timeframes
    allowed_timeframes_str = os.getenv("ALLOWED_TIMEFRAMES", "5m")
    allowed_timeframes = [
        t.strip() for t in allowed_timeframes_str.split(',') if t.strip()
    ]
    
    # Execution enabled
    execution_enabled = os.getenv("EXECUTION_ENABLED", "true").lower() == "true"
    
    # Create bot client
    bot_client = create_bot_client()
    
    return ExecutionWorker(
        storage=storage,
        bot_client=bot_client,
        circuit_breaker=circuit_breaker,
        max_alert_age=max_alert_age,
        min_confidence=min_confidence,
        allowed_symbols=allowed_symbols,
        allowed_timeframes=allowed_timeframes,
        execution_enabled=execution_enabled,
        get_execution_enabled_func=get_execution_enabled_func
    )
