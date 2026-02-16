"""
Pydantic schemas for TradingView webhook payloads.
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime


class WebhookPayload(BaseModel):
    """TradingView webhook alert payload schema."""
    
    symbol: str = Field(..., description="Trading pair symbol (e.g., BTCUSDT)")
    timeframe: str = Field(..., description="Chart timeframe (e.g., 5m, 15m)")
    side: str = Field(..., description="Trade direction: long or short")
    setup_id: str = Field(..., description="Setup identifier for tracking")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Signal confidence score (0-1)")
    price: float = Field(..., gt=0, description="Current price at alert time")
    event_time: str = Field(..., description="Event timestamp from TradingView")
    secret: str = Field(..., description="Shared secret for authentication")
    timestamp: int = Field(..., description="Unix timestamp in seconds")
    nonce: str = Field(..., description="Unique nonce to prevent replay attacks")
    
    # Optional fields
    indicators: Optional[dict] = Field(default=None, description="Additional indicator values")
    notes: Optional[str] = Field(default=None, description="Optional notes")
    
    @field_validator('side')
    @classmethod
    def validate_side(cls, v: str) -> str:
        """Validate trade side."""
        if v.lower() not in ['long', 'short', 'buy', 'sell']:
            raise ValueError('side must be one of: long, short, buy, sell')
        return v.lower()
    
    @field_validator('timeframe')
    @classmethod
    def validate_timeframe(cls, v: str) -> str:
        """Validate timeframe format."""
        valid_timeframes = ['1m', '3m', '5m', '15m', '30m', '1h', '4h', '1d']
        if v not in valid_timeframes:
            raise ValueError(f'timeframe must be one of: {valid_timeframes}')
        return v
    
    @field_validator('symbol')
    @classmethod
    def validate_symbol(cls, v: str) -> str:
        """Validate and normalize symbol."""
        return v.upper().replace(' ', '')


class WebhookResponse(BaseModel):
    """Response schema for webhook endpoint."""
    
    success: bool = Field(..., description="Whether webhook was processed successfully")
    message: str = Field(..., description="Response message")
    alert_id: Optional[str] = Field(default=None, description="Alert ID if logged")
    timestamp: datetime = Field(default_factory=datetime.now, description="Server timestamp")
    action_taken: Optional[str] = Field(default=None, description="Action taken by bot")


class HealthResponse(BaseModel):
    """Health check response."""
    
    status: str = Field(..., description="Service status")
    timestamp: datetime = Field(default_factory=datetime.now)
    version: str = Field(default="1.0.0")
    uptime_seconds: Optional[float] = Field(default=None)


class ValidationError(BaseModel):
    """Validation error details."""
    
    field: str
    message: str
    received_value: Optional[str] = None
