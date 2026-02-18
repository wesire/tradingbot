"""
FastAPI webhook gateway for TradingView alerts.
"""
from typing import Optional
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
from bot.sentiment import MockSentimentProvider, SentimentAggregator, SentimentStorage
from bot.ai_advisor import AIAdvisor
from bot.opportunities import OpportunityScorer
from bot.strategy import registry

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

# Initialize sentiment components
sentiment_provider = MockSentimentProvider(base_sentiment=0.1)
sentiment_aggregator = SentimentAggregator([sentiment_provider])
sentiment_storage = SentimentStorage()

# Initialize AI advisor (advisory only)
ai_advisor = AIAdvisor()

# Initialize opportunity scorer
opportunity_scorer = OpportunityScorer()


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


@app.get("/api/sentiment/summary")
async def get_sentiment_summary():
    """
    Get sentiment summary for all tracked assets.
    
    Returns:
        Dictionary with sentiment data for all assets
    """
    try:
        # Get enabled pairs from registry
        enabled_pairs = registry.list_enabled_pairs()
        
        # Aggregate sentiment for all pairs
        sentiments = sentiment_aggregator.aggregate_multi_asset(enabled_pairs)
        
        # Get market overview
        overview = sentiment_aggregator.get_market_overview(enabled_pairs)
        
        # Store sentiments
        for asset, sentiment in sentiments.items():
            sentiment_storage.store(sentiment)
        
        return {
            "success": True,
            "overview": overview,
            "assets": {k: v.to_dict() for k, v in sentiments.items()}
        }
    except Exception as e:
        logger.error(f"Error getting sentiment summary: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": str(e)}
        )


@app.get("/api/sentiment/{asset}")
async def get_sentiment_for_asset(asset: str, hours: int = 24):
    """
    Get sentiment details for a specific asset.
    
    Args:
        asset: Asset symbol (e.g., BTC, ETH, SOL)
        hours: Hours of history to retrieve
        
    Returns:
        Sentiment data for the asset
    """
    try:
        # Get current sentiment
        current = sentiment_aggregator.aggregate_sentiment(asset, lookback_hours=hours)
        
        # Get historical sentiment
        history = sentiment_storage.get_history(asset, hours=hours)
        
        if current:
            # Store current sentiment
            sentiment_storage.store(current)
            
            return {
                "success": True,
                "asset": asset,
                "current": current.to_dict(),
                "history": history
            }
        else:
            return {
                "success": True,
                "asset": asset,
                "current": None,
                "history": history,
                "message": "No current sentiment data available"
            }
    except Exception as e:
        logger.error(f"Error getting sentiment for {asset}: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": str(e)}
        )


@app.get("/api/advisor/{pair}")
async def get_advisor_for_pair(pair: str, timeframe: str = "5m"):
    """
    Get AI advisor guidance for a specific pair.
    
    ADVISORY ONLY: This endpoint provides guidance but NEVER places orders.
    
    Args:
        pair: Trading pair (e.g., BTC/USDT:USDT)
        timeframe: Timeframe for analysis
        
    Returns:
        AI advisory output
    """
    try:
        # Verify advisory-only mode
        ai_advisor.verify_advisory_only()
        
        # Extract base asset
        base_asset = pair.split('/')[0] if '/' in pair else pair
        
        # Mock OHLCV and technical data (in production, fetch from exchange/strategy)
        ohlcv_snapshot = {
            "close": 45000.0,
            "volume": 1000000.0
        }
        
        technical_signals = {
            "rsi": 42.0,
            "price_vs_ema": True,
            "volume_above_avg": True,
            "filters_passed": True,
            "atr_status": "normal",
            "atr": 200.0
        }
        
        regime_data = {
            "bullish": True,
            "bearish": False,
            "neutral": False,
            "adx": 28.0
        }
        
        # Get sentiment
        sentiment = sentiment_aggregator.aggregate_sentiment(base_asset)
        sentiment_data = sentiment.to_dict() if sentiment else None
        
        # Generate advisory
        advisory = ai_advisor.generate_advisory(
            pair=pair,
            timeframe=timeframe,
            ohlcv_snapshot=ohlcv_snapshot,
            technical_signals=technical_signals,
            regime_data=regime_data,
            sentiment_data=sentiment_data
        )
        
        return {
            "success": True,
            "advisory": advisory.to_dict(),
            "warning": "ADVISORY ONLY - No orders will be placed based on this guidance"
        }
    except Exception as e:
        logger.error(f"Error generating advisor for {pair}: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": str(e)}
        )


@app.get("/api/opportunities")
async def get_opportunities(
    min_confidence: float = 0.3,
    max_results: int = 10,
    side: Optional[str] = None,
    timeframe: str = "5m"
):
    """
    Get ranked list of trading opportunities.
    
    Args:
        min_confidence: Minimum confidence threshold (0-1)
        max_results: Maximum number of results to return
        side: Optional filter for "long" or "short"
        timeframe: Timeframe for analysis
        
    Returns:
        List of trading opportunities
    """
    try:
        # Get enabled pairs from registry
        enabled_pairs = registry.list_enabled_pairs()
        
        # Build pairs data (mock data for now)
        pairs_data = {}
        
        for pair in enabled_pairs:
            base_asset = pair.split('/')[0]
            
            # Mock technical and regime data
            pairs_data[pair] = {
                'timeframe': timeframe,
                'technical': {
                    'rsi': 45.0,
                    'price_vs_ema': True,
                    'volume_above_avg': True,
                    'filters_passed': True,
                    'close': 45000.0,
                    'atr': 200.0
                },
                'regime': {
                    'bullish': True,
                    'bearish': False,
                    'adx': 28.0
                },
                'sentiment': None,
                'liquidity': {
                    'atr_status': 'normal',
                    'volume_consistent': True
                }
            }
            
            # Get sentiment if available
            sentiment = sentiment_aggregator.aggregate_sentiment(base_asset)
            if sentiment:
                pairs_data[pair]['sentiment'] = sentiment.to_dict()
        
        # Score opportunities
        opportunities = opportunity_scorer.score_multiple(pairs_data)
        
        # Filter by confidence
        opportunities = [o for o in opportunities if o.confidence >= min_confidence]
        
        # Filter by side if specified
        if side:
            opportunities = [o for o in opportunities if o.side == side.lower()]
        
        # Limit results
        opportunities = opportunities[:max_results]
        
        return {
            "success": True,
            "count": len(opportunities),
            "opportunities": [o.to_dict() for o in opportunities],
            "filters": {
                "min_confidence": min_confidence,
                "side": side,
                "timeframe": timeframe
            }
        }
    except Exception as e:
        logger.error(f"Error getting opportunities: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": str(e)}
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
