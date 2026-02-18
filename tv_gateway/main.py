"""
FastAPI webhook gateway for TradingView alerts.
Phase 2: Full alert execution pipeline with lifecycle management.
"""
from typing import Optional
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from contextlib import asynccontextmanager
import os
from datetime import datetime
import json
import sqlite3
from pathlib import Path
import logging
import asyncio

from tv_gateway.schemas import WebhookPayload, WebhookResponse, HealthResponse
from tv_gateway.auth import WebhookAuth
from tv_gateway.alert_storage import AlertStorage, Alert, AlertStatus
from tv_gateway.execution_worker import create_execution_worker
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
alert_storage = None
execution_worker = None
worker_task = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for FastAPI application."""
    global alert_storage, execution_worker, worker_task
    
    # Startup
    logger.info("Starting TradingView webhook gateway (Phase 2)...")
    
    # Initialize alert storage (migrates old database if needed)
    alert_storage = AlertStorage(db_path="alerts.db")
    
    # Initialize execution worker
    execution_worker = create_execution_worker(alert_storage)
    
    # Start worker in background
    worker_task = asyncio.create_task(execution_worker.run())
    
    logger.info("Service started successfully with execution worker")
    
    yield
    
    # Shutdown
    logger.info("Shutting down webhook gateway...")
    
    if execution_worker:
        execution_worker.stop()
    
    if worker_task:
        try:
            await asyncio.wait_for(worker_task, timeout=5.0)
        except asyncio.TimeoutError:
            logger.warning("Worker task did not stop gracefully")
            worker_task.cancel()
    
    logger.info("Shutdown complete")


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


@app.get("/", response_class=HTMLResponse)
async def root():
    """Root endpoint - Operator Dashboard."""
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>TradingView Alert Execution Dashboard</title>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                background: #0f172a;
                color: #e2e8f0;
                padding: 20px;
            }
            
            .container {
                max-width: 1400px;
                margin: 0 auto;
            }
            
            header {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                padding: 30px;
                border-radius: 12px;
                margin-bottom: 30px;
                box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
            }
            
            h1 {
                font-size: 32px;
                font-weight: 700;
                margin-bottom: 8px;
            }
            
            .subtitle {
                font-size: 16px;
                opacity: 0.9;
            }
            
            .stats-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 20px;
                margin-bottom: 30px;
            }
            
            .stat-card {
                background: #1e293b;
                padding: 24px;
                border-radius: 12px;
                border: 1px solid #334155;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
            }
            
            .stat-label {
                font-size: 14px;
                color: #94a3b8;
                text-transform: uppercase;
                letter-spacing: 0.5px;
                margin-bottom: 8px;
            }
            
            .stat-value {
                font-size: 36px;
                font-weight: 700;
                margin-bottom: 4px;
            }
            
            .stat-subtext {
                font-size: 13px;
                color: #64748b;
            }
            
            .alerts-section {
                background: #1e293b;
                padding: 24px;
                border-radius: 12px;
                border: 1px solid #334155;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
            }
            
            .section-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 20px;
            }
            
            h2 {
                font-size: 24px;
                font-weight: 600;
            }
            
            .refresh-indicator {
                font-size: 13px;
                color: #64748b;
            }
            
            .alerts-table {
                width: 100%;
                border-collapse: collapse;
                overflow: hidden;
            }
            
            .alerts-table thead {
                background: #0f172a;
            }
            
            .alerts-table th {
                padding: 12px;
                text-align: left;
                font-size: 13px;
                font-weight: 600;
                color: #94a3b8;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            
            .alerts-table td {
                padding: 12px;
                border-top: 1px solid #334155;
                font-size: 14px;
            }
            
            .alerts-table tbody tr:hover {
                background: #0f172a;
            }
            
            .status-chip {
                display: inline-block;
                padding: 4px 12px;
                border-radius: 20px;
                font-size: 12px;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            
            .status-accepted {
                background: #3b82f6;
                color: #dbeafe;
            }
            
            .status-queued {
                background: #f59e0b;
                color: #fef3c7;
            }
            
            .status-executed {
                background: #10b981;
                color: #d1fae5;
            }
            
            .status-failed {
                background: #ef4444;
                color: #fee2e2;
            }
            
            .status-ignored {
                background: #6b7280;
                color: #e5e7eb;
            }
            
            .side-long {
                color: #10b981;
                font-weight: 600;
            }
            
            .side-short {
                color: #ef4444;
                font-weight: 600;
            }
            
            .confidence-high {
                color: #10b981;
            }
            
            .confidence-medium {
                color: #f59e0b;
            }
            
            .confidence-low {
                color: #ef4444;
            }
            
            .loading {
                text-align: center;
                padding: 40px;
                color: #64748b;
            }
            
            .error {
                background: #7f1d1d;
                border: 1px solid #991b1b;
                color: #fecaca;
                padding: 16px;
                border-radius: 8px;
                margin: 20px 0;
            }
            
            @keyframes pulse {
                0%, 100% { opacity: 1; }
                50% { opacity: 0.5; }
            }
            
            .pulsing {
                animation: pulse 2s ease-in-out infinite;
            }
            
            .mono {
                font-family: 'Courier New', monospace;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <header>
                <h1>🚀 TradingView Alert Execution Dashboard</h1>
                <p class="subtitle">Phase 2: Real-time alert monitoring and execution pipeline</p>
            </header>
            
            <div class="stats-grid" id="stats-grid">
                <div class="stat-card">
                    <div class="stat-label">Service Status</div>
                    <div class="stat-value pulsing" id="service-status">●</div>
                    <div class="stat-subtext" id="uptime">Loading...</div>
                </div>
                
                <div class="stat-card">
                    <div class="stat-label">Total Alerts</div>
                    <div class="stat-value" id="total-alerts">-</div>
                    <div class="stat-subtext" id="recent-count">Last hour: -</div>
                </div>
                
                <div class="stat-card">
                    <div class="stat-label">Executed</div>
                    <div class="stat-value" style="color: #10b981;" id="executed-count">-</div>
                    <div class="stat-subtext">Successfully processed</div>
                </div>
                
                <div class="stat-card">
                    <div class="stat-label">Failed</div>
                    <div class="stat-value" style="color: #ef4444;" id="failed-count">-</div>
                    <div class="stat-subtext">Rejected or errored</div>
                </div>
            </div>
            
            <div class="alerts-section">
                <div class="section-header">
                    <h2>Latest Alerts</h2>
                    <div class="refresh-indicator">
                        Auto-refresh: <span id="refresh-timer">10s</span>
                    </div>
                </div>
                
                <div id="alerts-container">
                    <div class="loading">Loading alerts...</div>
                </div>
            </div>
        </div>
        
        <script>
            let refreshCounter = 10;
            let refreshInterval;
            let countdownInterval;
            
            function formatTimestamp(isoString) {
                if (!isoString) return '-';
                const date = new Date(isoString);
                return date.toLocaleString();
            }
            
            function formatUptime(seconds) {
                const hours = Math.floor(seconds / 3600);
                const minutes = Math.floor((seconds % 3600) / 60);
                return `Uptime: ${hours}h ${minutes}m`;
            }
            
            function getConfidenceClass(confidence) {
                if (confidence >= 0.8) return 'confidence-high';
                if (confidence >= 0.5) return 'confidence-medium';
                return 'confidence-low';
            }
            
            async function fetchStats() {
                try {
                    const response = await fetch('/stats');
                    const data = await response.json();
                    
                    if (data.success) {
                        // Service status
                        document.getElementById('service-status').textContent = 
                            data.service.status === 'running' ? '● RUNNING' : '○ STOPPED';
                        document.getElementById('service-status').style.color = 
                            data.service.status === 'running' ? '#10b981' : '#ef4444';
                        
                        // Uptime
                        document.getElementById('uptime').textContent = 
                            formatUptime(data.service.uptime_seconds);
                        
                        // Alert counts
                        document.getElementById('total-alerts').textContent = 
                            data.alerts.total_alerts || 0;
                        document.getElementById('recent-count').textContent = 
                            `Last hour: ${data.alerts.recent_count_1h || 0}`;
                        document.getElementById('executed-count').textContent = 
                            data.alerts.by_status?.executed || 0;
                        document.getElementById('failed-count').textContent = 
                            data.alerts.by_status?.failed || 0;
                    }
                } catch (error) {
                    console.error('Error fetching stats:', error);
                }
            }
            
            async function fetchAlerts() {
                try {
                    const response = await fetch('/alerts?limit=20');
                    const data = await response.json();
                    
                    if (data.success && data.alerts.length > 0) {
                        const table = `
                            <table class="alerts-table">
                                <thead>
                                    <tr>
                                        <th>ID</th>
                                        <th>Time</th>
                                        <th>Symbol</th>
                                        <th>Side</th>
                                        <th>Confidence</th>
                                        <th>Price</th>
                                        <th>Status</th>
                                        <th>Setup</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${data.alerts.map(alert => `
                                        <tr>
                                            <td class="mono">${alert.id}</td>
                                            <td>${formatTimestamp(alert.received_at).split(',')[1]}</td>
                                            <td><strong>${alert.symbol}</strong></td>
                                            <td class="side-${alert.side.toLowerCase()}">${alert.side.toUpperCase()}</td>
                                            <td class="${getConfidenceClass(alert.confidence)}">
                                                ${(alert.confidence * 100).toFixed(0)}%
                                            </td>
                                            <td class="mono">$${alert.price.toFixed(2)}</td>
                                            <td>
                                                <span class="status-chip status-${alert.status}">
                                                    ${alert.status}
                                                </span>
                                            </td>
                                            <td class="mono">${alert.setup_id || '-'}</td>
                                        </tr>
                                    `).join('')}
                                </tbody>
                            </table>
                        `;
                        document.getElementById('alerts-container').innerHTML = table;
                    } else if (data.success && data.alerts.length === 0) {
                        document.getElementById('alerts-container').innerHTML = 
                            '<div class="loading">No alerts yet. Send a test alert to see it here.</div>';
                    }
                } catch (error) {
                    console.error('Error fetching alerts:', error);
                    document.getElementById('alerts-container').innerHTML = 
                        '<div class="error">Failed to load alerts. Please refresh the page.</div>';
                }
            }
            
            function updateRefreshTimer() {
                document.getElementById('refresh-timer').textContent = `${refreshCounter}s`;
                refreshCounter--;
                
                if (refreshCounter < 0) {
                    refreshCounter = 10;
                    fetchStats();
                    fetchAlerts();
                }
            }
            
            // Initial load
            fetchStats();
            fetchAlerts();
            
            // Set up refresh intervals
            refreshInterval = setInterval(() => {
                fetchStats();
                fetchAlerts();
            }, 10000);
            
            countdownInterval = setInterval(updateRefreshTimer, 1000);
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


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
    Phase 2: Stores alerts with idempotency and queues for execution.
    
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
        
        # Store rejected alert
        alert = Alert(
            received_at=datetime.now().isoformat(),
            symbol=payload.symbol,
            timeframe=payload.timeframe,
            side=payload.side,
            setup_id=payload.setup_id,
            confidence=payload.confidence,
            price=payload.price,
            event_time=payload.event_time,
            nonce=payload.nonce,
            payload_json=json.dumps(payload.model_dump()),
            validation_result=f"FAILED: {validation_msg}",
            status=AlertStatus.FAILED,
            fail_reason=validation_msg
        )
        
        alert_storage.store_alert(alert)
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=validation_msg
        )
    
    # Create alert object
    alert = Alert(
        received_at=datetime.now().isoformat(),
        symbol=payload.symbol,
        timeframe=payload.timeframe,
        side=payload.side,
        setup_id=payload.setup_id,
        confidence=payload.confidence,
        price=payload.price,
        event_time=payload.event_time,
        nonce=payload.nonce,
        payload_json=json.dumps(payload.model_dump()),
        validation_result="SUCCESS",
        status=AlertStatus.ACCEPTED
    )
    
    # Store with idempotency check
    is_new, alert_id, reason = alert_storage.store_alert(alert)
    
    if not is_new:
        # Duplicate alert
        logger.info(f"Duplicate alert ignored: id={alert_id}, nonce={payload.nonce}")
        
        # Update status to ignored
        alert_storage.update_status(
            alert_id=alert_id,
            status=AlertStatus.IGNORED,
            fail_reason="duplicate"
        )
        
        return WebhookResponse(
            success=True,
            message="Duplicate alert ignored (idempotent)",
            alert_id=str(alert_id),
            action_taken="ignored_duplicate"
        )
    
    # Log successful alert acceptance
    logger.info(
        f"Alert accepted: id={alert_id}, {payload.symbol} {payload.side} "
        f"confidence={payload.confidence} setup={payload.setup_id}"
    )
    
    # Alert will be picked up by execution worker
    return WebhookResponse(
        success=True,
        message="Alert received and queued for execution",
        alert_id=str(alert_id),
        action_taken="accepted"
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


@app.get("/alerts")
async def list_alerts(
    limit: int = 50,
    status: Optional[str] = None,
    symbol: Optional[str] = None
):
    """
    List alerts with optional filtering.
    
    Args:
        limit: Maximum number of alerts to return (default 50)
        status: Filter by status (accepted/queued/executed/failed/ignored)
        symbol: Filter by symbol
        
    Returns:
        List of alerts (newest first)
    """
    try:
        alerts = alert_storage.list_alerts(limit=limit, status=status, symbol=symbol)
        
        return {
            "success": True,
            "count": len(alerts),
            "alerts": [alert.to_dict() for alert in alerts],
            "filters": {
                "limit": limit,
                "status": status,
                "symbol": symbol
            }
        }
    except Exception as e:
        logger.error(f"Error listing alerts: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": str(e)}
        )


@app.get("/alerts/{alert_id}")
async def get_alert(alert_id: int):
    """
    Get details of a specific alert.
    
    Args:
        alert_id: Alert database ID
        
    Returns:
        Alert details
    """
    try:
        alert = alert_storage.get_alert(alert_id)
        
        if not alert:
            raise HTTPException(
                status_code=404,
                detail=f"Alert {alert_id} not found"
            )
        
        return {
            "success": True,
            "alert": alert.to_dict()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting alert {alert_id}: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": str(e)}
        )


@app.get("/stats")
async def get_stats():
    """
    Get alert statistics and system status.
    
    Returns:
        Statistics including counts by status and last processed time
    """
    try:
        stats = alert_storage.get_stats()
        
        uptime = (datetime.now() - service_start_time).total_seconds()
        
        return {
            "success": True,
            "service": {
                "status": "running",
                "uptime_seconds": uptime,
                "worker_enabled": execution_worker is not None
            },
            "alerts": stats
        }
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
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
