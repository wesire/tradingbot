"""
FastAPI webhook gateway for TradingView alerts.
"""
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import os
from datetime import datetime
import json
import sqlite3
from pathlib import Path
import logging

from tv_gateway.schemas import WebhookPayload, WebhookResponse, HealthResponse
from tv_gateway.auth import WebhookAuth
from bot.config.default_config import config

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Service state
service_start_time = datetime.now()


def init_database():
    """Initialize SQLite database for alert logging."""
    db_path = "alerts.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            source_ip TEXT,
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            side TEXT NOT NULL,
            confidence REAL,
            price REAL,
            setup_id TEXT,
            validation_result TEXT NOT NULL,
            action_taken TEXT,
            payload TEXT NOT NULL
        )
    ''')
    
    conn.commit()
    conn.close()
    logger.info(f"Database initialized: {db_path}")


def log_alert(
    payload: dict,
    source_ip: str,
    validation_result: str,
    action_taken: str = "none"
):
    """
    Log alert to database and JSON file.
    
    Args:
        payload: Alert payload dictionary
        source_ip: Source IP address
        validation_result: Validation result (success/failure reason)
        action_taken: Action taken by bot
    """
    # Log to database
    try:
        conn = sqlite3.connect("alerts.db")
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO alerts (
                timestamp, source_ip, symbol, timeframe, side,
                confidence, price, setup_id, validation_result,
                action_taken, payload
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            datetime.now().isoformat(),
            source_ip,
            payload.get('symbol', ''),
            payload.get('timeframe', ''),
            payload.get('side', ''),
            payload.get('confidence', 0.0),
            payload.get('price', 0.0),
            payload.get('setup_id', ''),
            validation_result,
            action_taken,
            json.dumps(payload)
        ))
        
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Failed to log to database: {e}")
    
    # Log to JSON file
    try:
        log_dir = Path("artifacts")
        log_dir.mkdir(exist_ok=True)
        log_file = log_dir / "webhook_alerts.jsonl"
        
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "source_ip": source_ip,
            "validation_result": validation_result,
            "action_taken": action_taken,
            "payload": payload
        }
        
        with open(log_file, 'a') as f:
            f.write(json.dumps(log_entry) + '\n')
    except Exception as e:
        logger.error(f"Failed to log to file: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for FastAPI application."""
    # Startup
    logger.info("Starting TradingView webhook gateway...")
    init_database()
    logger.info("Service started successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down webhook gateway...")


# Initialize FastAPI app
app = FastAPI(
    title="TradingView Webhook Gateway",
    description="Secure webhook receiver for TradingView alerts",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize auth
webhook_auth = WebhookAuth(
    shared_secret=config.TV_WEBHOOK_SECRET,
    max_age_seconds=config.TV_MAX_ALERT_AGE_SECONDS
)


@app.get("/", response_model=HealthResponse)
async def root():
    """Root endpoint."""
    return HealthResponse(
        status="running",
        version="1.0.0"
    )


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    uptime = (datetime.now() - service_start_time).total_seconds()
    
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        uptime_seconds=uptime
    )


@app.post("/tv/webhook", response_model=WebhookResponse)
async def receive_webhook(payload: WebhookPayload, request: Request):
    """
    Receive and process TradingView webhook alerts.
    
    Args:
        payload: Validated webhook payload
        request: FastAPI request object
        
    Returns:
        WebhookResponse with processing result
    """
    client_ip = request.client.host if request.client else "unknown"
    
    logger.info(f"Received webhook from {client_ip}: {payload.symbol} {payload.side} @ {payload.price}")
    
    # Validate authentication and security
    is_valid, validation_msg = webhook_auth.validate_all(
        secret=payload.secret,
        timestamp=payload.timestamp,
        nonce=payload.nonce,
        client_ip=client_ip
    )
    
    if not is_valid:
        logger.warning(f"Validation failed from {client_ip}: {validation_msg}")
        log_alert(
            payload=payload.model_dump(),
            source_ip=client_ip,
            validation_result=f"FAILED: {validation_msg}",
            action_taken="rejected"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=validation_msg
        )
    
    # Check confidence threshold
    if payload.confidence < config.TV_CONFIDENCE_THRESHOLD:
        logger.info(f"Alert confidence too low: {payload.confidence} < {config.TV_CONFIDENCE_THRESHOLD}")
        log_alert(
            payload=payload.model_dump(),
            source_ip=client_ip,
            validation_result="SUCCESS",
            action_taken=f"ignored_low_confidence_{payload.confidence}"
        )
        return WebhookResponse(
            success=True,
            message=f"Alert received but confidence too low ({payload.confidence})",
            action_taken="ignored_low_confidence"
        )
    
    # Validate symbol matches our trading pair
    expected_symbol = config.TRADING_PAIR.replace('/', '').replace(':', '')
    received_symbol = payload.symbol.replace('/', '').replace(':', '')
    
    if expected_symbol.upper() != received_symbol.upper():
        logger.info(f"Symbol mismatch: expected {expected_symbol}, got {received_symbol}")
        log_alert(
            payload=payload.model_dump(),
            source_ip=client_ip,
            validation_result="SUCCESS",
            action_taken="ignored_symbol_mismatch"
        )
        return WebhookResponse(
            success=True,
            message=f"Symbol mismatch: {received_symbol} not tracked",
            action_taken="ignored_symbol_mismatch"
        )
    
    # Log successful alert
    log_alert(
        payload=payload.model_dump(),
        source_ip=client_ip,
        validation_result="SUCCESS",
        action_taken="logged_for_review"
    )
    
    # In production, this would route to the bot's decision layer
    # For now, we just log and acknowledge
    logger.info(
        f"Alert accepted: {payload.symbol} {payload.side} "
        f"confidence={payload.confidence} setup={payload.setup_id}"
    )
    
    return WebhookResponse(
        success=True,
        message="Alert received and logged successfully",
        action_taken="logged_for_review"
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "message": "Internal server error",
            "detail": str(exc) if os.getenv("DEBUG") else "An error occurred"
        }
    )


if __name__ == "__main__":
    import uvicorn
    
    port = config.TV_WEBHOOK_PORT
    logger.info(f"Starting webhook server on port {port}")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info"
    )
