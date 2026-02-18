"""
Structured logging configuration with secret redaction and correlation IDs.
"""
import logging
import json
import re
from typing import Any, Dict
from datetime import datetime, timezone
import uuid
from contextvars import ContextVar

# Context variable for correlation ID
correlation_id_var: ContextVar[str] = ContextVar('correlation_id', default='')

# Patterns to redact in logs
SECRET_PATTERNS = [
    (re.compile(r'TV_WEBHOOK_SECRET["\']?\s*[:=]\s*["\']?([^"\'\s,}]+)', re.IGNORECASE), '***REDACTED***'),
    (re.compile(r'EXCHANGE_API_KEY["\']?\s*[:=]\s*["\']?([^"\'\s,}]+)', re.IGNORECASE), '***REDACTED***'),
    (re.compile(r'EXCHANGE_API_SECRET["\']?\s*[:=]\s*["\']?([^"\'\s,}]+)', re.IGNORECASE), '***REDACTED***'),
    (re.compile(r'OPENAI_API_KEY["\']?\s*[:=]\s*["\']?([^"\'\s,}]+)', re.IGNORECASE), '***REDACTED***'),
    (re.compile(r'api[_-]?key["\']?\s*[:=]\s*["\']?([^"\'\s,}]+)', re.IGNORECASE), '***REDACTED***'),
    (re.compile(r'api[_-]?secret["\']?\s*[:=]\s*["\']?([^"\'\s,}]+)', re.IGNORECASE), '***REDACTED***'),
    (re.compile(r'token["\']?\s*[:=]\s*["\']?([^"\'\s,}]+)', re.IGNORECASE), '***REDACTED***'),
    (re.compile(r'password["\']?\s*[:=]\s*["\']?([^"\'\s,}]+)', re.IGNORECASE), '***REDACTED***'),
]


class SecretRedactionFilter(logging.Filter):
    """Filter that redacts sensitive information from log messages."""
    
    def filter(self, record: logging.LogRecord) -> bool:
        """
        Redact secrets from log message.
        
        Args:
            record: Log record to filter
            
        Returns:
            True to allow the record to be logged
        """
        if isinstance(record.msg, str):
            for pattern, replacement in SECRET_PATTERNS:
                record.msg = pattern.sub(replacement, record.msg)
        
        # Also redact from args if present
        if record.args:
            redacted_args = []
            for arg in record.args if isinstance(record.args, (list, tuple)) else [record.args]:
                if isinstance(arg, str):
                    for pattern, replacement in SECRET_PATTERNS:
                        arg = pattern.sub(replacement, arg)
                redacted_args.append(arg)
            record.args = tuple(redacted_args) if isinstance(record.args, tuple) else redacted_args
        
        return True


class JSONFormatter(logging.Formatter):
    """
    Formatter that outputs logs as structured JSON.
    """
    
    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record as JSON.
        
        Args:
            record: Log record to format
            
        Returns:
            JSON-formatted log string
        """
        log_data: Dict[str, Any] = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }
        
        # Add correlation ID if available
        correlation_id = correlation_id_var.get('')
        if correlation_id:
            log_data['correlation_id'] = correlation_id
        
        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        # Add extra fields from record
        for key, value in record.__dict__.items():
            if key not in ['name', 'msg', 'args', 'created', 'filename', 'funcName',
                          'levelname', 'lineno', 'module', 'msecs', 'message',
                          'pathname', 'process', 'processName', 'relativeCreated',
                          'thread', 'threadName', 'exc_info', 'exc_text', 'stack_info']:
                log_data[key] = value
        
        return json.dumps(log_data)


def setup_logging(
    level: str = "INFO",
    json_format: bool = False,
    enable_redaction: bool = True
) -> None:
    """
    Configure application logging.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_format: If True, use JSON formatter; otherwise use standard format
        enable_redaction: If True, apply secret redaction filter
    """
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))
    
    # Remove existing handlers
    root_logger.handlers.clear()
    
    # Create console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, level.upper()))
    
    # Set formatter
    if json_format:
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    console_handler.setFormatter(formatter)
    
    # Add secret redaction filter
    if enable_redaction:
        redaction_filter = SecretRedactionFilter()
        console_handler.addFilter(redaction_filter)
    
    # Add handler to root logger
    root_logger.addHandler(console_handler)


def get_correlation_id() -> str:
    """
    Get current correlation ID.
    
    Returns:
        Current correlation ID or empty string if not set
    """
    return correlation_id_var.get('')


def set_correlation_id(correlation_id: str = None) -> str:
    """
    Set correlation ID for request tracing.
    
    Args:
        correlation_id: Correlation ID to set. If None, generates a new UUID.
        
    Returns:
        The correlation ID that was set
    """
    if correlation_id is None:
        correlation_id = str(uuid.uuid4())
    correlation_id_var.set(correlation_id)
    return correlation_id


def clear_correlation_id() -> None:
    """Clear correlation ID."""
    correlation_id_var.set('')
