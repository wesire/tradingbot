"""
FastAPI webhook gateway for TradingView alerts.
Phase 2.1: Production hardening with security, reliability, and safe operations.
"""
from typing import Optional
from fastapi import FastAPI, Request, HTTPException, status, Header, Depends, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse, Response
from contextlib import asynccontextmanager
import os

try:
    from dotenv import load_dotenv
    load_dotenv()  # loads .env from working directory if present (e.g. /app/.env in Docker)
except ImportError:
    pass  # python-dotenv not installed, rely on container env vars
from datetime import datetime, timedelta, timezone
import json
import sqlite3
from pathlib import Path
import logging
import asyncio

from tv_gateway.schemas import WebhookPayload, WebhookResponse, HealthResponse
from tv_gateway.auth import WebhookAuth
from tv_gateway.alert_storage import AlertStorage, Alert, AlertStatus
from tv_gateway.execution_worker import create_execution_worker
from tv_gateway.hmac_auth import HMACAuthenticator
from tv_gateway.nonce_storage import NonceStorage
from tv_gateway.rate_limiter import RateLimiter
from tv_gateway.ip_filter import IPFilter
from tv_gateway.circuit_breaker import CircuitBreaker, CircuitState
from tv_gateway.structured_logging import audit_logger
from tv_gateway.websocket_manager import ws_manager
from bot.config.default_config import config
from bot.sentiment import (
    MockSentimentProvider,
    SentimentAggregator,
    SentimentStorage,
    CryptoPanicSentimentProvider,
    RedditSentimentProvider,
    TwitterSentimentProvider,
    FearGreedProvider,
    SentimentSpikeDetector,
)
from bot.notifications import NotificationManager, TelegramNotifier, Severity
from bot.ai_advisor import AIAdvisor
from bot.opportunities import OpportunityScorer
from bot.strategy import registry

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Phase 2.1: Load configuration from environment
REQUIRE_HMAC = os.getenv("REQUIRE_HMAC", "false").lower() == "true"
HMAC_SKEW_SECONDS = int(os.getenv("HMAC_SKEW_SECONDS", "60"))
NONCE_TTL_SECONDS = int(os.getenv("NONCE_TTL_SECONDS", "600"))
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "30"))
MAX_PAYLOAD_SIZE = int(os.getenv("MAX_PAYLOAD_SIZE_KB", "32")) * 1024
WEBHOOK_ACCEPTING_ENABLED = os.getenv("WEBHOOK_ACCEPTING_ENABLED", "true").lower() == "true"
EXECUTION_ENABLED = os.getenv("EXECUTION_ENABLED", "true").lower() == "true"
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")
RUNMODE = os.getenv("RUNMODE", "dry-run")
CONFIRM_LIVE_TRADING = os.getenv("CONFIRM_LIVE_TRADING", "")

# Circuit breaker configuration
CIRCUIT_BREAKER_THRESHOLD = int(os.getenv("CIRCUIT_BREAKER_THRESHOLD", "5"))
CIRCUIT_BREAKER_WINDOW = int(os.getenv("CIRCUIT_BREAKER_WINDOW_SECONDS", "300"))
CIRCUIT_BREAKER_COOLDOWN = int(os.getenv("CIRCUIT_BREAKER_COOLDOWN_SECONDS", "60"))

# IP filtering configuration
IP_ALLOWLIST = os.getenv("IP_ALLOWLIST", "")
IP_DENYLIST = os.getenv("IP_DENYLIST", "")
TRUSTED_PROXY_CIDRS = os.getenv("TRUSTED_PROXY_CIDRS", "")

# WebSocket configuration
WS_HEARTBEAT_INTERVAL = int(os.getenv("WS_HEARTBEAT_INTERVAL_SECONDS", "30"))
WS_MAX_CLIENTS = int(os.getenv("WS_MAX_CLIENTS", "50"))
WS_BROADCAST_POSITIONS_INTERVAL = int(os.getenv("WS_BROADCAST_POSITIONS_INTERVAL", "5"))
WS_BROADCAST_STATUS_INTERVAL = int(os.getenv("WS_BROADCAST_STATUS_INTERVAL", "10"))
WS_BROADCAST_SENTIMENT_INTERVAL = int(os.getenv("WS_BROADCAST_SENTIMENT_INTERVAL", "60"))
WS_BROADCAST_OPPORTUNITIES_INTERVAL = int(os.getenv("WS_BROADCAST_OPPORTUNITIES_INTERVAL", "30"))

# Service state
service_start_time = datetime.now()
webhook_accepting = WEBHOOK_ACCEPTING_ENABLED
execution_enabled = EXECUTION_ENABLED

# Safety check: require explicit confirmation for live trading
if RUNMODE != "dry-run" and CONFIRM_LIVE_TRADING != "YES":
    logger.error(
        "CRITICAL: RUNMODE is not dry-run but CONFIRM_LIVE_TRADING != 'YES'. "
        "Refusing to start. Set CONFIRM_LIVE_TRADING=YES to enable live trading."
    )
    raise RuntimeError("Live trading confirmation required")

# Initialize alert storage at module level (works for both tests and production)
# Use environment variable for db path to allow test isolation
db_path = os.getenv("ALERTS_DB_PATH", "alerts.db")
alert_storage = AlertStorage(db_path=db_path)

# Initialize Phase 2.1 security components
nonce_storage = NonceStorage(db_path=db_path, ttl_seconds=NONCE_TTL_SECONDS)
hmac_authenticator = HMACAuthenticator(
    shared_secret=config.TV_WEBHOOK_SECRET,
    skew_seconds=HMAC_SKEW_SECONDS,
    require_hmac=REQUIRE_HMAC
)
rate_limiter = RateLimiter(requests_per_minute=RATE_LIMIT_PER_MINUTE)
ip_filter = IPFilter(
    allowlist=[s.strip() for s in IP_ALLOWLIST.split(',') if s.strip()],
    denylist=[s.strip() for s in IP_DENYLIST.split(',') if s.strip()],
    trusted_proxies=[s.strip() for s in TRUSTED_PROXY_CIDRS.split(',') if s.strip()]
)
circuit_breaker = CircuitBreaker(
    failure_threshold=CIRCUIT_BREAKER_THRESHOLD,
    window_seconds=CIRCUIT_BREAKER_WINDOW,
    cooldown_seconds=CIRCUIT_BREAKER_COOLDOWN
)

execution_worker = None
worker_task = None

# Log startup configuration
logger.info("=" * 60)
logger.info("Phase 2.1 Production Hardening Configuration:")
logger.info(f"  REQUIRE_HMAC: {REQUIRE_HMAC}")
logger.info(f"  HMAC_SKEW_SECONDS: {HMAC_SKEW_SECONDS}")
logger.info(f"  NONCE_TTL_SECONDS: {NONCE_TTL_SECONDS}")
logger.info(f"  RATE_LIMIT_PER_MINUTE: {RATE_LIMIT_PER_MINUTE}")
logger.info(f"  MAX_PAYLOAD_SIZE: {MAX_PAYLOAD_SIZE} bytes")
logger.info(f"  WEBHOOK_ACCEPTING_ENABLED: {WEBHOOK_ACCEPTING_ENABLED}")
logger.info(f"  EXECUTION_ENABLED: {EXECUTION_ENABLED}")
logger.info(f"  RUNMODE: {RUNMODE}")
logger.info(f"  ADMIN_TOKEN: {'configured' if ADMIN_TOKEN else 'not configured'}")
logger.info(f"  IP_ALLOWLIST: {IP_ALLOWLIST if IP_ALLOWLIST else 'none'}")
logger.info(f"  IP_DENYLIST: {IP_DENYLIST if IP_DENYLIST else 'none'}")
logger.info(f"  Circuit Breaker: {CIRCUIT_BREAKER_THRESHOLD} failures in {CIRCUIT_BREAKER_WINDOW}s")
logger.info("=" * 60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for FastAPI application."""
    global execution_worker, worker_task
    
    # Startup
    logger.info("Starting TradingView webhook gateway (Phase 2.1)...")
    
    # Alert storage is already initialized at module level
    
    # Function to get current execution_enabled state
    def get_execution_enabled():
        return execution_enabled
    
    # Initialize execution worker with circuit breaker
    execution_worker = create_execution_worker(
        alert_storage,
        circuit_breaker=circuit_breaker,
        get_execution_enabled_func=get_execution_enabled
    )
    
    # Start worker in background
    worker_task = asyncio.create_task(execution_worker.run())
    
    # Start periodic nonce cleanup
    cleanup_task = None
    
    async def cleanup_nonces_periodically():
        while True:
            await asyncio.sleep(300)  # Every 5 minutes
            try:
                nonce_storage.cleanup_expired()
            except Exception as e:
                logger.error(f"Nonce cleanup error: {e}")
    
    cleanup_task = asyncio.create_task(cleanup_nonces_periodically())

    # ------------------------------------------------------------------
    # WebSocket background broadcast tasks
    # ------------------------------------------------------------------

    async def broadcast_positions():
        """Every WS_BROADCAST_POSITIONS_INTERVAL seconds push positions."""
        while True:
            try:
                if ws_manager.client_count > 0:
                    if broker_adapter is None:
                        payload: dict = {"positions": [], "exchange_configured": False}
                    else:
                        raw = broker_adapter.fetch_positions()
                        positions = []
                        for pos in raw:
                            contracts = float(pos.get("contracts") or pos.get("amount") or 0)
                            notional = float(pos.get("notional") or 0)
                            if contracts == 0 and notional == 0:
                                continue
                            side_raw = pos.get("side", "long")
                            side = "long" if side_raw in ("long", "buy") else "short"
                            entry_price = float(pos.get("entryPrice") or pos.get("entry_price") or 0)
                            current_price = float(pos.get("markPrice") or pos.get("mark_price") or entry_price)
                            unrealized_pnl = float(pos.get("unrealizedPnl") or pos.get("unrealized_pnl") or 0)
                            pnl_pct = 0.0
                            if entry_price > 0 and contracts > 0:
                                pnl_pct = (unrealized_pnl / (entry_price * contracts)) * 100
                            positions.append({
                                "symbol": pos.get("symbol", ""),
                                "side": side,
                                "size": contracts,
                                "entry_price": round(entry_price, 8),
                                "current_price": round(current_price, 8),
                                "pnl": round(unrealized_pnl, 4),
                                "pnl_percentage": round(pnl_pct, 4),
                                "leverage": int(pos.get("leverage") or 1),
                            })
                        payload = {"positions": positions, "exchange_configured": True}
                    await ws_manager.broadcast("positions", payload)
            except Exception as exc:
                logger.debug(f"WS positions broadcast error: {exc}")
            await asyncio.sleep(WS_BROADCAST_POSITIONS_INTERVAL)

    async def broadcast_status():
        """Every WS_BROADCAST_STATUS_INTERVAL seconds push bot status."""
        while True:
            try:
                if ws_manager.client_count > 0:
                    uptime = (datetime.now() - service_start_time).total_seconds()
                    payload = {
                        "status": "running" if not bot_paused else "paused",
                        "mode": RUNMODE,
                        "uptime": uptime,
                        "last_heartbeat": datetime.now(timezone.utc).isoformat(),
                        "exchange_connected": broker_adapter is not None,
                        "websocket_clients": ws_manager.client_count,
                    }
                    await ws_manager.broadcast("status", payload)
            except Exception as exc:
                logger.debug(f"WS status broadcast error: {exc}")
            await asyncio.sleep(WS_BROADCAST_STATUS_INTERVAL)

    async def broadcast_sentiment():
        """Every WS_BROADCAST_SENTIMENT_INTERVAL seconds push sentiment scores."""
        while True:
            try:
                if ws_manager.client_count > 0:
                    enabled_pairs = registry.list_enabled_pairs()
                    sentiments = sentiment_aggregator.aggregate_multi_asset(enabled_pairs)
                    overview = sentiment_aggregator.get_market_overview(enabled_pairs)
                    payload = {
                        "overview": overview,
                        "assets": {k: v.to_dict() for k, v in sentiments.items()},
                        "providers": [type(p).__name__ for p in _sentiment_providers],
                    }
                    await ws_manager.broadcast("sentiment", payload)
            except Exception as exc:
                logger.debug(f"WS sentiment broadcast error: {exc}")
            await asyncio.sleep(WS_BROADCAST_SENTIMENT_INTERVAL)

    async def broadcast_opportunities():
        """Every WS_BROADCAST_OPPORTUNITIES_INTERVAL seconds push scored opportunities."""
        while True:
            try:
                if ws_manager.client_count > 0:
                    enabled_pairs = registry.list_enabled_pairs()
                    opps = []
                    for pair in enabled_pairs:
                        base_asset = pair.split("/")[0] if "/" in pair else pair
                        sentiment = sentiment_aggregator.aggregate_sentiment(base_asset)
                        scored = opportunity_scorer.score_opportunities(
                            pair=pair,
                            timeframe="5m",
                            sentiment=sentiment,
                        )
                        opps.extend(scored)
                    opps.sort(key=lambda o: o.get("confidence", 0), reverse=True)
                    await ws_manager.broadcast("opportunities", {"opportunities": opps[:10]})
            except Exception as exc:
                logger.debug(f"WS opportunities broadcast error: {exc}")
            await asyncio.sleep(WS_BROADCAST_OPPORTUNITIES_INTERVAL)

    ws_heartbeat_task = asyncio.create_task(ws_manager.run_heartbeat())
    ws_positions_task = asyncio.create_task(broadcast_positions())
    ws_status_task = asyncio.create_task(broadcast_status())
    ws_sentiment_task = asyncio.create_task(broadcast_sentiment())
    ws_opportunities_task = asyncio.create_task(broadcast_opportunities())

    logger.info("Service started successfully with execution worker and security features")
    
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
    
    if cleanup_task:
        cleanup_task.cancel()

    for _task in (ws_heartbeat_task, ws_positions_task, ws_status_task,
                  ws_sentiment_task, ws_opportunities_task):
        _task.cancel()
    
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

# Initialize sentiment components — use real providers when API keys are available
def _build_sentiment_providers():
    """Build list of sentiment providers based on configured API keys."""
    providers = []
    weights = {}

    cryptopanic_key = os.getenv("CRYPTOPANIC_API_KEY", "")
    twitter_token = os.getenv("TWITTER_BEARER_TOKEN", "")

    if cryptopanic_key and cryptopanic_key not in ("your_key_here", ""):
        try:
            providers.append(CryptoPanicSentimentProvider(api_key=cryptopanic_key))
            weights["CryptoPanicSentimentProvider"] = 0.35
            logger.info("CryptoPanic sentiment provider enabled")
        except Exception as e:
            logger.warning(f"Failed to init CryptoPanic provider: {e}")

    try:
        providers.append(RedditSentimentProvider())
        weights["RedditSentimentProvider"] = 0.25
        logger.info("Reddit sentiment provider enabled")
    except Exception as e:
        logger.warning(f"Failed to init Reddit provider: {e}")

    if twitter_token and twitter_token not in ("your_bearer_token_here", ""):
        try:
            providers.append(TwitterSentimentProvider(bearer_token=twitter_token))
            weights["TwitterSentimentProvider"] = 0.20
            logger.info("Twitter/X sentiment provider enabled")
        except Exception as e:
            logger.warning(f"Failed to init Twitter provider: {e}")

    try:
        providers.append(FearGreedProvider())
        weights["FearGreedProvider"] = 0.20
        logger.info("Fear & Greed sentiment provider enabled")
    except Exception as e:
        logger.warning(f"Failed to init Fear & Greed provider: {e}")

    if not providers:
        logger.warning("No real sentiment providers configured — using mock provider")
        providers.append(MockSentimentProvider(base_sentiment=0.1))
        weights = {}

    return providers, weights


_sentiment_providers, _sentiment_weights = _build_sentiment_providers()
sentiment_aggregator = SentimentAggregator(_sentiment_providers, weights=_sentiment_weights)
sentiment_storage = SentimentStorage()

# Initialize sentiment spike detector from env vars
_SPIKE_THRESHOLD = float(os.getenv("SENTIMENT_SPIKE_THRESHOLD", "0.3"))
_SPIKE_WINDOW_MINUTES = int(os.getenv("SENTIMENT_SPIKE_WINDOW_MINUTES", "60"))
_SPIKE_COOLDOWN_MINUTES = int(os.getenv("SENTIMENT_SPIKE_COOLDOWN_MINUTES", "30"))
_SPIKE_ALERTS_ENABLED = os.getenv("SENTIMENT_SPIKE_ALERTS_ENABLED", "true").lower() == "true"

spike_detector = SentimentSpikeDetector(
    spike_threshold=_SPIKE_THRESHOLD,
    window_minutes=_SPIKE_WINDOW_MINUTES,
    cooldown_minutes=_SPIKE_COOLDOWN_MINUTES,
)


def _provider_display_name(provider) -> str:
    """Return a short human-readable name for a sentiment provider instance."""
    return type(provider).__name__.replace("SentimentProvider", "").replace("Provider", "")

# Initialize notification manager and wire in available notifiers
notification_manager = NotificationManager(throttle_minutes=5.0)
_telegram_notifier = TelegramNotifier()
if _telegram_notifier.is_available():
    notification_manager.add_notifier("telegram", _telegram_notifier)
    logger.info("Telegram notifier registered with NotificationManager")
else:
    logger.info("Telegram notifier not configured (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set)")
notification_manager.start()


# Initialize broker adapter lazily — only when exchange credentials are configured
_exchange_api_key = os.getenv("EXCHANGE_API_KEY", "")
_exchange_api_secret = os.getenv("EXCHANGE_API_SECRET", "")
_exchange_name = os.getenv("EXCHANGE_NAME", "binance")
_exchange_sandbox = os.getenv("EXCHANGE_SANDBOX", "true").lower() == "true"
broker_adapter = None

if (
    _exchange_api_key
    and _exchange_api_secret
    and _exchange_api_key not in ("your_api_key_here", "")
    and _exchange_api_secret not in ("your_api_secret_here", "")
):
    try:
        from bot.execution.broker_adapter import BrokerAdapter
        broker_adapter = BrokerAdapter(
            exchange_name=_exchange_name,
            api_key=_exchange_api_key,
            api_secret=_exchange_api_secret,
            sandbox=_exchange_sandbox,
        )
        logger.info(f"Exchange adapter initialized: {_exchange_name} (sandbox={_exchange_sandbox})")
    except Exception as e:
        logger.warning(f"Failed to initialize exchange adapter: {e}. Exchange data will be unavailable.")
else:
    logger.info("No exchange API credentials configured — exchange data endpoints will return empty data")

# Mutable bot control state (toggled via API)
bot_paused = False

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
                try {
                    const date = new Date(isoString);
                    const formatted = date.toLocaleString();
                    // Return only time portion (after comma), or full string if no comma
                    const parts = formatted.split(',');
                    return parts.length > 1 ? parts[1].trim() : formatted;
                } catch (e) {
                    return isoString;
                }
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
                                            <td>${formatTimestamp(alert.received_at)}</td>
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
    """
    Health check endpoint.

    Returns HTTP 200 when the service is healthy and HTTP 503 when degraded.
    Degraded conditions:
    - Circuit breaker is OPEN (too many consecutive failures to the bot)
    """
    from fastapi.responses import JSONResponse
    from tv_gateway.circuit_breaker import CircuitState

    uptime = (datetime.now() - service_start_time).total_seconds()

    # Determine degraded conditions
    cb_open = circuit_breaker.state == CircuitState.OPEN
    is_degraded = cb_open

    # Last trade time: look up most recent alert in storage
    last_trade: Optional[str] = None
    try:
        recent = alert_storage.get_recent_alerts(limit=1)
        if recent:
            last_trade = recent[0].received_at.isoformat() if hasattr(recent[0].received_at, 'isoformat') else str(recent[0].received_at)
    except Exception:
        pass

    # Active pairs from config
    active_pairs_raw = os.getenv("ENABLED_PAIRS", "BTC/USDT:USDT")
    active_pairs = [p.strip() for p in active_pairs_raw.split(",") if p.strip()]

    # ML model status
    ml_model_path = os.getenv("ML_MODEL_PATH", "")
    model_status = "loaded" if ml_model_path and os.path.exists(ml_model_path) else "not_loaded"

    # Sentiment status
    sentiment_status = "ok"
    try:
        sentiment_aggregator.get_cached_sentiment("BTC")
    except Exception:
        sentiment_status = "error"

    body = HealthResponse(
        status="degraded" if is_degraded else "healthy",
        version="1.1.0",
        uptime_seconds=uptime,
        last_trade_time=last_trade,
        active_pairs=active_pairs,
        model_status=model_status,
        sentiment_status=sentiment_status,
        webhook_accepting=webhook_accepting,
        execution_enabled=execution_enabled,
        exchange_connected=broker_adapter is not None,
    )

    http_status = 503 if is_degraded else 200
    return JSONResponse(content=body.model_dump(mode="json"), status_code=http_status)


@app.post("/tv/webhook", response_model=WebhookResponse)
async def receive_webhook(
    request: Request,
    x_tv_timestamp: Optional[str] = Header(None, alias="X-TV-Timestamp"),
    x_tv_nonce: Optional[str] = Header(None, alias="X-TV-Nonce"),
    x_tv_signature: Optional[str] = Header(None, alias="X-TV-Signature"),
    x_forwarded_for: Optional[str] = Header(None, alias="X-Forwarded-For")
):
    """
    Receive and process TradingView webhook alerts.
    Phase 2.1: Enhanced security with HMAC, rate limiting, and operational safety.
    
    Args:
        request: FastAPI request object
        x_tv_timestamp: Optional HMAC timestamp header
        x_tv_nonce: Optional HMAC nonce header
        x_tv_signature: Optional HMAC signature header
        x_forwarded_for: X-Forwarded-For header for proxy support
        
    Returns:
        WebhookResponse with processing result
    """
    global webhook_accepting
    
    # Get raw body for HMAC verification
    raw_body = await request.body()
    
    # Check payload size limit
    if len(raw_body) > MAX_PAYLOAD_SIZE:
        logger.warning(f"Payload too large: {len(raw_body)} bytes > {MAX_PAYLOAD_SIZE}")
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Payload too large: {len(raw_body)} bytes (max {MAX_PAYLOAD_SIZE})"
        )
    
    # Extract client IP (considering proxies)
    direct_ip = request.client.host if request.client else "unknown"
    client_ip = ip_filter.extract_client_ip(direct_ip, x_forwarded_for)
    
    logger.info(f"Received webhook from {client_ip} (direct: {direct_ip})")
    
    # Check if webhook is accepting requests (re-read env var for runtime config changes)
    env_accepting = os.getenv("WEBHOOK_ACCEPTING_ENABLED", "true").lower() == "true"
    if not webhook_accepting or not env_accepting:
        logger.warning(f"Webhook disabled, rejecting request from {client_ip}")
        audit_logger.log_request_rejected(
            reason="webhook_disabled",
            client_ip=client_ip
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook gateway is currently disabled"
        )

    # Check IP allowlist/denylist
    ip_allowed, ip_reason = ip_filter.is_allowed(client_ip)
    if not ip_allowed:
        audit_logger.log_ip_blocked(client_ip, ip_reason)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ip_reason
        )

    # Reconfigure rate limiter if RATE_LIMIT_PER_MINUTE env var has changed
    current_rpm = int(os.getenv("RATE_LIMIT_PER_MINUTE", "30"))
    rate_limiter.reconfigure(current_rpm)

    # Check rate limit
    rate_ok, retry_after = rate_limiter.check_rate_limit(client_ip)
    if not rate_ok:
        audit_logger.log_rate_limit(client_ip, retry_after)
        response = JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"detail": "Rate limit exceeded"},
            headers={"Retry-After": str(retry_after)}
        )
        return response
    
    # Parse JSON payload
    try:
        payload_dict = json.loads(raw_body)
        payload = WebhookPayload(**payload_dict)
    except Exception as e:
        logger.error(f"Failed to parse payload: {e}")
        audit_logger.log_request_rejected(
            reason=f"invalid_payload: {str(e)}",
            client_ip=client_ip
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid payload: {str(e)}"
        )
    
    # HMAC authentication (if headers provided or required)
    hmac_valid, hmac_msg, used_hmac = hmac_authenticator.verify_hmac_request(
        timestamp=x_tv_timestamp,
        nonce=x_tv_nonce,
        body=raw_body,
        signature=x_tv_signature
    )
    
    if not hmac_valid:
        logger.warning(f"HMAC validation failed from {client_ip}: {hmac_msg}")
        audit_logger.log_hmac_verification(
            success=False,
            nonce=x_tv_nonce or "none",
            client_ip=client_ip,
            reason=hmac_msg
        )
        audit_logger.log_request_rejected(
            reason=f"hmac_failed: {hmac_msg}",
            client_ip=client_ip,
            symbol=payload.symbol,
            nonce=x_tv_nonce
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=hmac_msg
        )
    
    # Log HMAC success if used
    if used_hmac:
        audit_logger.log_hmac_verification(
            success=True,
            nonce=x_tv_nonce,
            client_ip=client_ip
        )
    
    # Determine nonce for replay protection
    # Use HMAC nonce if provided, otherwise payload nonce
    nonce_for_replay = x_tv_nonce or payload.nonce
    timestamp_for_replay = x_tv_timestamp or str(payload.timestamp)
    
    # Check nonce replay (DB-backed)
    nonce_ok, nonce_msg = nonce_storage.check_and_store(
        nonce=nonce_for_replay,
        timestamp=timestamp_for_replay
    )
    
    if not nonce_ok:
        logger.warning(f"Replay detected from {client_ip}: {nonce_msg}")
        audit_logger.log_replay_detected(nonce_for_replay, client_ip)
        audit_logger.log_request_rejected(
            reason=nonce_msg,
            client_ip=client_ip,
            symbol=payload.symbol,
            nonce=nonce_for_replay
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=nonce_msg
        )
    
    # Legacy secret validation (backward compatibility)
    if not used_hmac:
        is_valid, validation_msg = webhook_auth.validate_all(
            secret=payload.secret,
            timestamp=payload.timestamp,
            nonce=payload.nonce,
            client_ip=client_ip
        )
        
        if not is_valid:
            logger.warning(f"Legacy validation failed from {client_ip}: {validation_msg}")
            audit_logger.log_request_rejected(
                reason=f"legacy_auth_failed: {validation_msg}",
                client_ip=client_ip,
                symbol=payload.symbol,
                nonce=payload.nonce
            )
            
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
    
    # Determine auth method for logging
    auth_method = "hmac" if used_hmac else "secret"
    
    # Log successful alert acceptance
    logger.info(
        f"Alert accepted: id={alert_id}, {payload.symbol} {payload.side} "
        f"confidence={payload.confidence} setup={payload.setup_id}"
    )
    
    audit_logger.log_request_accepted(
        alert_id=alert_id,
        symbol=payload.symbol,
        side=payload.side,
        setup_id=payload.setup_id,
        confidence=payload.confidence,
        client_ip=client_ip,
        auth_method=auth_method,
        idempotency_key=f"{payload.nonce}:{payload.symbol}:{payload.event_time}"
    )
    
    # Alert will be picked up by execution worker
    # Broadcast the new alert to WebSocket subscribers immediately
    asyncio.create_task(ws_manager.broadcast("alerts", {
        "id": str(alert_id),
        "symbol": payload.symbol,
        "side": payload.side,
        "confidence": payload.confidence,
        "setup_id": payload.setup_id,
        "received_at": datetime.now(timezone.utc).isoformat(),
    }))

    return WebhookResponse(
        success=True,
        message="Alert received and queued for execution",
        alert_id=str(alert_id),
        action_taken="accepted"
    )


# ============================================================================
# Admin Endpoints (Phase 2.1)
# ============================================================================

def verify_admin_token(authorization: Optional[str] = Header(None)):
    """Verify admin token from Authorization header."""
    if not ADMIN_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin endpoints not configured (ADMIN_TOKEN not set)"
        )
    
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required"
        )
    
    # Support both "Bearer <token>" and direct token
    token = authorization.replace("Bearer ", "").strip()
    
    if token != ADMIN_TOKEN:
        logger.warning("Invalid admin token attempt")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid admin token"
        )
    
    return True


@app.post("/admin/execution/enable")
async def admin_enable_execution(authorized: bool = Depends(verify_admin_token)):
    """Enable execution (admin endpoint)."""
    global execution_enabled
    
    old_state = execution_enabled
    execution_enabled = True
    
    logger.warning("Execution ENABLED by admin")
    audit_logger.log_kill_switch("execution_enabled", True)
    
    return {
        "success": True,
        "message": "Execution enabled",
        "previous_state": old_state,
        "current_state": execution_enabled
    }


@app.post("/admin/execution/disable")
async def admin_disable_execution(authorized: bool = Depends(verify_admin_token)):
    """Disable execution (admin endpoint)."""
    global execution_enabled
    
    old_state = execution_enabled
    execution_enabled = False
    
    logger.warning("Execution DISABLED by admin")
    audit_logger.log_kill_switch("execution_enabled", False)
    
    return {
        "success": True,
        "message": "Execution disabled",
        "previous_state": old_state,
        "current_state": execution_enabled
    }


@app.post("/admin/webhook/enable")
async def admin_enable_webhook(authorized: bool = Depends(verify_admin_token)):
    """Enable webhook accepting (admin endpoint)."""
    global webhook_accepting
    
    old_state = webhook_accepting
    webhook_accepting = True
    
    logger.warning("Webhook ENABLED by admin")
    audit_logger.log_kill_switch("webhook_accepting", True)
    
    return {
        "success": True,
        "message": "Webhook enabled",
        "previous_state": old_state,
        "current_state": webhook_accepting
    }


@app.post("/admin/webhook/disable")
async def admin_disable_webhook(authorized: bool = Depends(verify_admin_token)):
    """Disable webhook accepting (admin endpoint)."""
    global webhook_accepting
    
    old_state = webhook_accepting
    webhook_accepting = False
    
    logger.warning("Webhook DISABLED by admin")
    audit_logger.log_kill_switch("webhook_accepting", False)
    
    return {
        "success": True,
        "message": "Webhook disabled",
        "previous_state": old_state,
        "current_state": webhook_accepting
    }


@app.post("/admin/circuit/reset")
async def admin_reset_circuit(authorized: bool = Depends(verify_admin_token)):
    """Reset circuit breaker (admin endpoint)."""
    old_state = circuit_breaker.state
    circuit_breaker.force_reset()
    
    logger.warning("Circuit breaker reset by admin")
    
    return {
        "success": True,
        "message": "Circuit breaker reset",
        "previous_state": old_state,
        "current_state": circuit_breaker.state
    }


@app.get("/admin/config")
async def admin_get_config(authorized: bool = Depends(verify_admin_token)):
    """Get configuration (admin endpoint, secrets redacted)."""
    return {
        "success": True,
        "config": {
            "security": {
                "require_hmac": REQUIRE_HMAC,
                "hmac_skew_seconds": HMAC_SKEW_SECONDS,
                "nonce_ttl_seconds": NONCE_TTL_SECONDS,
                "rate_limit_per_minute": RATE_LIMIT_PER_MINUTE,
                "max_payload_size_kb": MAX_PAYLOAD_SIZE / 1024,
                "secret_configured": bool(config.TV_WEBHOOK_SECRET),
                "admin_token_configured": bool(ADMIN_TOKEN)
            },
            "operational": {
                "webhook_accepting": webhook_accepting,
                "execution_enabled": execution_enabled,
                "runmode": RUNMODE,
                "confirm_live_trading": bool(CONFIRM_LIVE_TRADING)
            },
            "circuit_breaker": circuit_breaker.get_status(),
            "ip_filtering": ip_filter.get_stats(),
            "rate_limiter": rate_limiter.get_stats(),
            "nonce_storage": {
                "active_nonces": nonce_storage.count_nonces(),
                "ttl_seconds": NONCE_TTL_SECONDS
            }
        }
    }


# ============================================================================
# End Admin Endpoints
# ============================================================================


# ============================================================================
# Dashboard API Endpoints
# ============================================================================

# ---------------------------------------------------------------------------
# Technical indicator helpers used by /api/advisor and /api/opportunities
# ---------------------------------------------------------------------------

def _compute_rsi(prices: list, period: int = 14) -> float:
    """Compute a simple RSI from a list of close prices."""
    if len(prices) < period + 1:
        return 50.0
    gains = [max(prices[i] - prices[i - 1], 0.0) for i in range(1, len(prices))]
    losses = [max(prices[i - 1] - prices[i], 0.0) for i in range(1, len(prices))]
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_gain == 0.0 and avg_loss == 0.0:
        return 50.0
    if avg_loss == 0.0:
        return 100.0
    return 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))


def _compute_ema(prices: list, period: int) -> float:
    """Compute an EMA over *prices* with the given *period*."""
    if not prices:
        return 0.0
    if len(prices) < period:
        return prices[-1]
    k = 2.0 / (period + 1)
    ema = prices[0]
    for p in prices[1:]:
        ema = p * k + ema * (1.0 - k)
    return ema


@app.get("/api/status")
async def get_bot_status():
    """Get current bot status including mode, uptime, and configuration."""
    uptime = (datetime.now() - service_start_time).total_seconds()
    mode = "live" if RUNMODE not in ("dry-run", "dry_run") else "dry-run"
    status_val = "paused" if bot_paused else "running"

    exchange_configured = broker_adapter is not None
    openai_configured = bool(os.getenv("OPENAI_API_KEY", ""))

    sentiment_sources = []
    for p in _sentiment_providers:
        sentiment_sources.append(type(p).__name__)

    return {
        "success": True,
        "status": status_val,
        "mode": mode,
        "uptime": uptime,
        "last_heartbeat": datetime.now().isoformat(),
        "exchange_connected": exchange_configured,
        "exchange_name": _exchange_name if exchange_configured else None,
        "exchange_sandbox": _exchange_sandbox,
        "openai_configured": openai_configured,
        "sentiment_sources": sentiment_sources,
    }


@app.get("/api/positions")
async def get_positions():
    """Get open positions from the exchange."""
    if broker_adapter is None:
        return {
            "success": True,
            "positions": [],
            "message": "No exchange connected. Add EXCHANGE_API_KEY and EXCHANGE_API_SECRET to .env to see real positions.",
            "exchange_configured": False,
            "source": "none",
        }
    try:
        raw_positions = broker_adapter.fetch_positions()
        positions = []
        for pos in raw_positions:
            contracts = float(pos.get("contracts") or pos.get("amount") or 0)
            notional = float(pos.get("notional") or 0)
            if contracts == 0 and notional == 0:
                continue
            side_raw = pos.get("side", "long")
            side = "long" if side_raw in ("long", "buy") else "short"
            entry_price = float(pos.get("entryPrice") or pos.get("entry_price") or 0)
            current_price = float(pos.get("markPrice") or pos.get("mark_price") or entry_price)
            unrealized_pnl = float(pos.get("unrealizedPnl") or pos.get("unrealized_pnl") or 0)
            pnl_pct = 0.0
            if entry_price > 0 and contracts > 0:
                pnl_pct = (unrealized_pnl / (entry_price * contracts)) * 100
            positions.append({
                "symbol": pos.get("symbol", ""),
                "side": side,
                "size": contracts,
                "entry_price": round(entry_price, 8),
                "current_price": round(current_price, 8),
                "pnl": round(unrealized_pnl, 4),
                "pnl_percentage": round(pnl_pct, 4),
                "leverage": int(pos.get("leverage") or 1),
                "source": "exchange",
            })
        return {"success": True, "positions": positions, "exchange_configured": True, "source": "exchange"}
    except Exception as e:
        logger.error(f"Error fetching positions from exchange: {e}")
        return {
            "success": True,
            "positions": [],
            "exchange_configured": True,
            "message": f"Could not fetch positions from exchange: {e}",
            "source": "error",
        }


@app.get("/api/trades")
async def get_trades(limit: int = 50):
    """Get recent trade history — from the exchange when available, otherwise from alert storage."""
    if broker_adapter is not None:
        try:
            raw_trades = broker_adapter.fetch_my_trades(limit=limit)
            trades = []
            for t in raw_trades:
                trades.append({
                    "id": str(t.get("id", "")),
                    "timestamp": t.get("datetime", ""),
                    "symbol": t.get("symbol", ""),
                    "side": t.get("side", "buy"),
                    "size": float(t.get("amount") or 0),
                    "price": float(t.get("price") or 0),
                    "pnl": float(t.get("info", {}).get("realizedPnl", 0) or 0) if isinstance(t.get("info"), dict) else 0.0,
                    "status": "closed",
                    "source": "exchange",
                })
            return {"success": True, "trades": trades, "count": len(trades), "source": "exchange"}
        except Exception as e:
            logger.warning(f"Could not fetch trades from exchange, falling back to alert storage: {e}")

    # Fallback: alert storage
    try:
        alerts = alert_storage.list_alerts(limit=limit, status="executed")
        trades = []
        for alert in alerts:
            alert_dict = alert.to_dict()
            trades.append({
                "id": str(alert_dict.get("id", "")),
                "timestamp": alert_dict.get("received_at", ""),
                "symbol": alert_dict.get("symbol", ""),
                "side": alert_dict.get("side", "buy"),
                "size": float(alert_dict.get("size", 0)),
                "price": float(alert_dict.get("price", 0)),
                "pnl": float(alert_dict.get("pnl", 0) or 0),
                "status": "closed" if alert_dict.get("status") == "executed" else "open",
                "source": "alerts",
            })
        return {"success": True, "trades": trades, "count": len(trades), "source": "alerts"}
    except Exception as e:
        logger.error(f"Error fetching trades: {e}")
        return JSONResponse(status_code=500, content={"success": False, "message": str(e)})


@app.get("/api/pnl-history")
async def get_pnl_history(period: str = "24h"):
    """
    Get PnL history.  Computed from real exchange trade fills when available,
    otherwise falls back to executed-alert metadata.
    Returns a time-series of realized PnL data points.
    """
    try:
        period_hours = {"1h": 1, "4h": 4, "24h": 24, "7d": 168, "30d": 720}.get(period, 24)
        pnl_by_hour: dict = {}
        cumulative = 0.0
        data_source = "alerts"

        if broker_adapter is not None:
            try:
                # Fetch enough recent trades to cover the requested period
                raw_trades = broker_adapter.fetch_my_trades(limit=500)
                data_source = "exchange"
                for trade in reversed(raw_trades):
                    ts_raw = trade.get("datetime", "")
                    try:
                        ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00")) if ts_raw else None
                    except Exception:
                        ts = None
                    if ts is None:
                        continue
                    hour_key = ts.strftime("%Y-%m-%dT%H:00:00")
                    info = trade.get("info", {}) or {}
                    realized = float(info.get("realizedPnl", 0) or 0)
                    cumulative += realized
                    if hour_key not in pnl_by_hour:
                        pnl_by_hour[hour_key] = {"realized": 0.0, "cumulative": cumulative}
                    pnl_by_hour[hour_key]["realized"] += realized
                    pnl_by_hour[hour_key]["cumulative"] = cumulative
            except Exception as e:
                logger.warning(f"Could not fetch trade history from exchange for PnL, falling back to alert storage: {e}")
                pnl_by_hour = {}
                cumulative = 0.0
                data_source = "alerts"

        if data_source == "alerts":
            alerts = alert_storage.list_alerts(limit=500, status="executed")
            for alert in reversed(alerts):
                alert_dict = alert.to_dict()
                ts_raw = alert_dict.get("received_at", "")
                try:
                    ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00")) if ts_raw else None
                except Exception:
                    ts = None
                if ts is None:
                    continue
                hour_key = ts.strftime("%Y-%m-%dT%H:00:00")
                realized = float(alert_dict.get("pnl", 0) or 0)
                cumulative += realized
                if hour_key not in pnl_by_hour:
                    pnl_by_hour[hour_key] = {"realized": 0.0, "cumulative": cumulative}
                pnl_by_hour[hour_key]["realized"] += realized
                pnl_by_hour[hour_key]["cumulative"] = cumulative

        history = [
            {
                "timestamp": k,
                "realized_pnl": round(v["realized"], 4),
                "unrealized_pnl": 0.0,
                "total_pnl": round(v["cumulative"], 4),
            }
            for k, v in sorted(pnl_by_hour.items())
        ][-period_hours:]

        return {"success": True, "period": period, "data": history, "source": data_source}
    except Exception as e:
        logger.error(f"Error fetching PnL history: {e}")
        return JSONResponse(status_code=500, content={"success": False, "message": str(e)})


@app.post("/api/toggle-mode")
async def toggle_mode(request: Request):
    """Toggle trading mode between dry-run and live."""
    global RUNMODE
    try:
        body = await request.json()
        new_mode = body.get("mode", "dry-run")
        if new_mode not in ("dry-run", "live"):
            return JSONResponse(status_code=400, content={"success": False, "message": "Invalid mode"})
        if new_mode == "live" and os.getenv("CONFIRM_LIVE_TRADING", "") != "YES":
            return JSONResponse(
                status_code=403,
                content={"success": False, "message": "Set CONFIRM_LIVE_TRADING=YES in .env to enable live mode"},
            )
        RUNMODE = new_mode
        logger.info(f"Trading mode toggled to: {new_mode}")
        return {"success": True, "mode": new_mode}
    except Exception as e:
        logger.error(f"Error toggling mode: {e}")
        return JSONResponse(status_code=500, content={"success": False, "message": str(e)})


@app.post("/api/emergency-stop")
async def emergency_stop():
    """Emergency stop — pause bot and disable execution."""
    global bot_paused, execution_enabled
    bot_paused = True
    execution_enabled = False
    logger.warning("EMERGENCY STOP executed via API")
    audit_logger.info("EMERGENCY_STOP", extra={"action": "emergency_stop"})
    return {"success": True, "message": "Emergency stop executed. Bot paused and execution disabled."}


@app.post("/api/pause")
async def pause_bot():
    """Pause the bot (stop processing new signals)."""
    global bot_paused
    bot_paused = True
    logger.info("Bot paused via API")
    return {"success": True, "status": "paused"}


@app.post("/api/resume")
async def resume_bot():
    """Resume the bot."""
    global bot_paused
    bot_paused = False
    logger.info("Bot resumed via API")
    return {"success": True, "status": "running"}


# ============================================================================
# End Dashboard API Endpoints
# ============================================================================


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

        # Run spike detection and dispatch notifications when alerts are enabled
        if _SPIKE_ALERTS_ENABLED and sentiments:
            current_scores = {asset: s.score for asset, s in sentiments.items()}
            provider_names = [_provider_display_name(p) for p in _sentiment_providers]
            spikes = spike_detector.check_for_spikes(current_scores, sources=provider_names)
            for spike in spikes:
                sev = Severity.CRITICAL if spike.severity == "extreme" else Severity.WARNING
                notification_manager.send_alert(
                    title=f"Sentiment Spike: {spike.asset}",
                    message=spike.format_alert(),
                    severity=sev,
                    metadata=spike.to_dict(),
                )
        
        return {
            "success": True,
            "overview": overview,
            "assets": {k: v.to_dict() for k, v in sentiments.items()},
            "providers": [type(p).__name__ for p in _sentiment_providers],
        }
    except Exception as e:
        logger.error(f"Error getting sentiment summary: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": str(e)}
        )


@app.get("/api/sentiment/spikes")
async def get_sentiment_spikes():
    """
    Return recent spike history, active cooldowns, and detector configuration.

    Returns:
        {
            "spikes": [...],
            "detector_config": {...},
            "active_cooldowns": [...]
        }
    """
    try:
        recent_spikes = spike_detector.get_recent_spikes(hours=24)
        return {
            "success": True,
            "spikes": [s.to_dict() for s in recent_spikes],
            "detector_config": spike_detector.get_config(),
            "active_cooldowns": spike_detector.get_active_cooldowns(),
        }
    except Exception as e:
        logger.error(f"Error getting sentiment spikes: {e}")
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


@app.get("/api/advisor/{pair:path}")
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
        
        # Fetch real OHLCV data from exchange if available, otherwise use placeholder
        exchange_available = broker_adapter is not None
        if exchange_available:
            try:
                ticker = broker_adapter.fetch_ticker(pair)
                close_price = float(ticker.get("last") or ticker.get("close") or 45000.0)
                volume = float(ticker.get("quoteVolume") or ticker.get("baseVolume") or 1000000.0)

                ohlcv_data = broker_adapter.fetch_ohlcv(pair, timeframe=timeframe, limit=50)
                closes = [c[4] for c in ohlcv_data if c[4]]
                volumes = [c[5] for c in ohlcv_data if c[5]]

                rsi = _compute_rsi(closes) if closes else 50.0
                ema21 = _compute_ema(closes, 21) if closes else close_price
                avg_volume = (sum(volumes) / len(volumes)) if volumes else volume

                ohlcv_snapshot = {"close": close_price, "volume": volume}
                technical_signals = {
                    "rsi": round(rsi, 2),
                    "price_vs_ema": close_price > ema21,
                    "volume_above_avg": volume > avg_volume,
                    "filters_passed": True,
                    "atr_status": "normal",
                    "atr": round(abs(closes[-1] - closes[-2]) if len(closes) >= 2 else 200.0, 4),
                }
                regime_data = {
                    "bullish": close_price > ema21,
                    "bearish": close_price < ema21,
                    "neutral": abs(close_price - ema21) / ema21 < 0.005 if ema21 else False,
                    "adx": 25.0,  # ADX requires more complex computation; placeholder
                }
            except Exception as ex_err:
                logger.warning(f"Exchange data fetch failed for {pair}: {ex_err} — using defaults")
                exchange_available = False

        if not exchange_available:
            ohlcv_snapshot = {"close": 45000.0, "volume": 1000000.0}
            technical_signals = {
                "rsi": 42.0,
                "price_vs_ema": True,
                "volume_above_avg": True,
                "filters_passed": True,
                "atr_status": "normal",
                "atr": 200.0,
            }
            regime_data = {"bullish": True, "bearish": False, "neutral": False, "adx": 28.0}
        
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
            "exchange_data": exchange_available,
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
        
        # Build pairs data — use real exchange data when available
        pairs_data = {}
        
        for pair in enabled_pairs:
            base_asset = pair.split('/')[0]
            
            technical = {
                'rsi': 45.0,
                'price_vs_ema': True,
                'volume_above_avg': True,
                'filters_passed': True,
                'close': 45000.0,
                'atr': 200.0,
            }
            regime = {'bullish': True, 'bearish': False, 'adx': 28.0}

            if broker_adapter is not None:
                try:
                    ticker = broker_adapter.fetch_ticker(pair)
                    close_price = float(ticker.get("last") or ticker.get("close") or 45000.0)
                    volume = float(ticker.get("quoteVolume") or ticker.get("baseVolume") or 1000000.0)

                    ohlcv_data = broker_adapter.fetch_ohlcv(pair, timeframe=timeframe, limit=50)
                    closes = [c[4] for c in ohlcv_data if c[4]]
                    volumes = [c[5] for c in ohlcv_data if c[5]]

                    rsi_val = _compute_rsi(closes) if closes else 50.0
                    ema21 = _compute_ema(closes, 21) if closes else close_price
                    avg_vol = (sum(volumes) / len(volumes)) if volumes else volume
                    atr_val = abs(closes[-1] - closes[-2]) if len(closes) >= 2 else 200.0

                    technical = {
                        'rsi': round(rsi_val, 2),
                        'price_vs_ema': close_price > ema21,
                        'volume_above_avg': volume > avg_vol,
                        'filters_passed': True,
                        'close': close_price,
                        'atr': round(atr_val, 4),
                    }
                    regime = {
                        'bullish': close_price > ema21,
                        'bearish': close_price < ema21,
                        'adx': 25.0,
                    }
                except Exception as pair_err:
                    logger.debug(f"Exchange data unavailable for {pair}: {pair_err}")

            pairs_data[pair] = {
                'timeframe': timeframe,
                'technical': technical,
                'regime': regime,
                'sentiment': None,
                'liquidity': {
                    'atr_status': 'normal',
                    'volume_consistent': True,
                },
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
        
        def _opp_to_api(opp, idx: int) -> dict:
            """Convert Opportunity dataclass to frontend-compatible dict."""
            d = opp.to_dict()
            current_price = d.get("entry_zone", "")
            # Parse entry_zone string e.g. "44800.0000-45300.0000"
            entry_price = 0.0
            try:
                parts = str(current_price).split("-")
                if len(parts) >= 2:
                    entry_price = (float(parts[0]) + float(parts[1])) / 2
                elif len(parts) == 1 and parts[0]:
                    entry_price = float(parts[0])
            except (ValueError, IndexError):
                pass

            # Parse invalidation as stop_loss
            stop_loss = 0.0
            try:
                stop_loss = float(d.get("invalidation", 0) or 0)
            except (ValueError, TypeError):
                pass

            # Derive take_profit from entry and risk_reward
            rr = float(d.get("risk_reward", 2.0) or 2.0)
            take_profit = 0.0
            if entry_price > 0 and stop_loss > 0:
                risk = abs(entry_price - stop_loss)
                if opp.side == "long":
                    take_profit = entry_price + risk * rr
                else:
                    take_profit = entry_price - risk * rr

            rationale_list = d.get("rationale", [])
            ai_rationale = ". ".join(rationale_list) if rationale_list else None

            return {
                "id": f"{d.get('pair', '')}-{idx}",
                "symbol": d.get("pair", ""),
                "side": d.get("side", "long"),
                "confidence": d.get("confidence", 0.0),
                "entry_price": round(entry_price, 4),
                "stop_loss": round(stop_loss, 4),
                "take_profit": round(take_profit, 4),
                "risk_reward": d.get("risk_reward", 2.0),
                "ai_rationale": ai_rationale,
                "timeframe": d.get("timeframe", timeframe),
                "technical_score": d.get("technical_score", 0.0),
                "regime_score": d.get("regime_score", 0.0),
                "sentiment_score": d.get("sentiment_score", 0.0),
            }

        return {
            "success": True,
            "count": len(opportunities),
            "exchange_data": broker_adapter is not None,
            "opportunities": [_opp_to_api(o, i) for i, o in enumerate(opportunities)],
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
    Phase 2.1: Includes circuit breaker status and operational flags.
    
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
            "operational": {
                "webhook_accepting": webhook_accepting,
                "execution_enabled": execution_enabled,
                "runmode": RUNMODE,
                "admin_enabled": bool(ADMIN_TOKEN)
            },
            "circuit_breaker": circuit_breaker.get_status(),
            "security": {
                "require_hmac": REQUIRE_HMAC,
                "rate_limit_per_minute": RATE_LIMIT_PER_MINUTE,
                "active_nonces": nonce_storage.count_nonces()
            },
            "alerts": stats
        }
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": str(e)}
        )

# ---------------------------------------------------------------------------
# ML endpoints
# ---------------------------------------------------------------------------

# Lazy singleton so we don't import heavy ML deps at module load time
_ml_backtester = None


def _get_backtester():
    global _ml_backtester
    if _ml_backtester is None:
        try:
            from bot.ml.backtester import MLBacktester
            _ml_backtester = MLBacktester()
        except Exception as exc:  # pragma: no cover
            logger.warning("Could not initialise MLBacktester: %s", exc)
            _ml_backtester = None
    return _ml_backtester


@app.get("/api/ml/status")
async def get_ml_status():
    """
    Return the current ML model status.

    When no model is loaded, all fields use sensible defaults/null values.
    """
    ml_model_path = os.getenv("ML_MODEL_PATH", "")
    model_loaded = bool(ml_model_path and os.path.exists(ml_model_path))

    backtester = _get_backtester()
    features_count = 0
    model_version = None

    if model_loaded and backtester is not None and backtester.model_loaded:
        clf = getattr(backtester, "_classifier", None)
        if clf is not None:
            features_count = len(getattr(clf, "feature_names", []))
            model_version = getattr(clf, "active_version", None)
    else:
        # Demo defaults
        from bot.ml.feature_engineer import FeatureEngineer
        features_count = len(FeatureEngineer.FEATURE_NAMES)

    return {
        "model_loaded": model_loaded,
        "model_path": ml_model_path or None,
        "model_version": model_version,
        "last_trained": None,
        "features_count": features_count,
        "training_samples": None,
        "is_demo": not model_loaded,
    }


@app.get("/api/ml/feature-importance")
async def get_ml_feature_importance():
    """
    Return feature importance rankings.

    Uses SHAP values when available, falls back to built-in importances,
    then to demo data when no model is loaded.
    """
    backtester = _get_backtester()

    if backtester is None:
        from bot.ml.backtester import _make_demo_feature_importance
        return {
            "features": _make_demo_feature_importance(),
            "method": "demo",
            "model_version": None,
        }

    features, method = backtester.get_feature_importance()
    model_version = None
    if backtester.model_loaded:
        clf = getattr(backtester, "_classifier", None)
        if clf is not None:
            model_version = getattr(clf, "active_version", None)

    return {
        "features": features,
        "method": method,
        "model_version": model_version,
    }


@app.post("/api/ml/backtest")
async def run_ml_backtest(request: Request):
    """
    Run an ML backtest over a date range.

    Request body (all fields optional)::

        {
            "start_date": "2025-01-01",
            "end_date":   "2025-12-31",
            "pair":       "BTC/USDT:USDT",
            "timeframe":  "5m"
        }

    Returns comprehensive metrics.  When no model is loaded the response
    contains realistic demo data (``is_demo: true``).
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    start_date = body.get("start_date")
    end_date = body.get("end_date")
    pair = body.get("pair", "BTC/USDT:USDT")
    timeframe = body.get("timeframe", "5m")

    backtester = _get_backtester()

    if backtester is None:
        from bot.ml.backtester import _build_demo_result
        result = _build_demo_result(pair, timeframe, start_date, end_date)
        return {"success": True, "metrics": result.to_dict()}

    result = backtester.run(
        ohlcv_df=None,
        start_date=start_date,
        end_date=end_date,
        pair=pair,
        timeframe=timeframe,
    )
    return {"success": True, "metrics": result.to_dict()}


@app.get("/api/ml/predictions/recent")
async def get_recent_ml_predictions(limit: int = 50):
    """
    Return the most recent ML predictions (demo data when no model is loaded).
    """
    ml_model_path = os.getenv("ML_MODEL_PATH", "")
    model_loaded = bool(ml_model_path and os.path.exists(ml_model_path))

    if not model_loaded:
        import random
        rng = random.Random(42)
        signals = ["buy", "sell", "hold"]
        outcomes = ["win", "loss", "pending"]
        demo_predictions = []
        now = datetime.now(timezone.utc)
        from bot.ml.feature_engineer import FeatureEngineer
        feat_count = len(FeatureEngineer.FEATURE_NAMES)
        for i in range(min(limit, 20)):
            ts = (now - timedelta(minutes=5 * (i + 1))).strftime("%Y-%m-%dT%H:%M:%SZ")
            demo_predictions.append({
                "timestamp": ts,
                "pair": "BTC/USDT:USDT",
                "signal": rng.choice(signals),
                "confidence": round(rng.uniform(0.50, 0.95), 3),
                "actual_outcome": rng.choice(outcomes),
                "features_used": feat_count,
            })
        return {"predictions": demo_predictions, "total": len(demo_predictions), "is_demo": True}

    # Real model: placeholder – extend with a live prediction log if available
    return {"predictions": [], "total": 0, "is_demo": False}


# ---------------------------------------------------------------------------
# Status endpoint (machine-readable)
# ---------------------------------------------------------------------------

@app.get("/status")
async def get_status():
    """Simple machine-readable status endpoint."""
    return {"status": "running"}


# ---------------------------------------------------------------------------
# OHLCV endpoint
# ---------------------------------------------------------------------------

@app.get("/api/ohlcv/{pair:path}")
async def get_ohlcv(pair: str, timeframe: str = "5m", limit: int = 200):
    """
    Fetch OHLCV candlestick data for a trading pair.

    Args:
        pair: Trading pair symbol (e.g. BTC/USDT:USDT)
        timeframe: Candle timeframe (e.g. 1m, 5m, 1h)
        limit: Number of candles to return (max 500)

    Returns:
        OHLCV candle data
    """
    limit = min(limit, 500)
    try:
        if broker_adapter is not None:
            raw = broker_adapter.fetch_ohlcv(pair, timeframe=timeframe, limit=limit)
            candles = [
                {
                    "timestamp": c[0],
                    "open": c[1],
                    "high": c[2],
                    "low": c[3],
                    "close": c[4],
                    "volume": c[5],
                }
                for c in raw
            ]
        else:
            # Demo data when no exchange is connected
            import random as _random
            rng = _random.Random(42)
            now_ts = int(datetime.now(timezone.utc).timestamp() * 1000)
            interval_ms = _timeframe_to_ms(timeframe)
            base = 45000.0
            candles = []
            for i in range(limit):
                ts = now_ts - (limit - i) * interval_ms
                o = base + rng.uniform(-200, 200)
                h = o + rng.uniform(0, 300)
                lo = o - rng.uniform(0, 300)
                c = lo + rng.uniform(0, h - lo)
                candles.append({
                    "timestamp": ts,
                    "open": round(o, 2),
                    "high": round(h, 2),
                    "low": round(lo, 2),
                    "close": round(c, 2),
                    "volume": round(rng.uniform(100, 1000), 2),
                })
                base = c

        return {
            "pair": pair,
            "timeframe": timeframe,
            "count": len(candles),
            "candles": candles,
            "is_demo": broker_adapter is None,
        }
    except Exception as e:
        logger.error(f"Error fetching OHLCV for {pair}: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": str(e)}
        )


def _timeframe_to_ms(tf: str) -> int:
    """Convert a timeframe string to milliseconds."""
    _map = {
        "1m": 60_000, "3m": 180_000, "5m": 300_000,
        "15m": 900_000, "30m": 1_800_000,
        "1h": 3_600_000, "2h": 7_200_000, "4h": 14_400_000,
        "6h": 21_600_000, "12h": 43_200_000,
        "1d": 86_400_000, "1w": 604_800_000, "1M": 2_592_000_000,
    }
    return _map.get(tf, 300_000)


# ---------------------------------------------------------------------------
# Performance report endpoint
# ---------------------------------------------------------------------------

# Lazy singleton for PerformanceTracker
_performance_tracker = None


def _get_performance_tracker():
    global _performance_tracker
    if _performance_tracker is None:
        try:
            from bot.portfolio.performance_tracker import PerformanceTracker
            db_path = os.getenv("PERFORMANCE_DB_PATH", "/app/data/performance.db")
            _performance_tracker = PerformanceTracker(db_path=db_path)
        except Exception as exc:
            logger.warning("Could not initialise PerformanceTracker: %s", exc)
    return _performance_tracker


@app.get("/api/performance/report")
async def get_performance_report(period: str = "30d"):
    """
    Return a comprehensive performance report including equity curve.

    Args:
        period: Period string e.g. 7d, 30d, 90d, all

    Returns:
        Metrics, equity curve, and per-pair breakdown
    """
    try:
        tracker = _get_performance_tracker()
        if tracker is None:
            # Return demo data when tracker unavailable
            import random as _random
            rng = _random.Random(42)
            now = datetime.now(timezone.utc)
            equity = 10000.0
            equity_curve = []
            for i in range(30):
                ts = (now - timedelta(days=29 - i)).isoformat()
                equity = equity * (1 + rng.uniform(-0.02, 0.025))
                equity_curve.append({"equity": round(equity, 2), "ts": ts})
            return {
                "period": period,
                "generated_at": now.isoformat(),
                "is_demo": True,
                "metrics": {
                    "total_trades": 0,
                    "win_rate": 0.0,
                    "profit_factor": 0.0,
                    "total_pnl": 0.0,
                    "max_drawdown": 0.0,
                    "sharpe_ratio": 0.0,
                },
                "per_pair": {},
                "equity_curve": equity_curve,
            }
        report = tracker.get_performance_report(period=period)
        report["is_demo"] = False
        return report
    except Exception as e:
        logger.error(f"Error getting performance report: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": str(e)}
        )


# ---------------------------------------------------------------------------
# Correlation matrix endpoint
# ---------------------------------------------------------------------------

# Lazy singleton for CorrelationManager
_correlation_manager = None


def _get_correlation_manager():
    global _correlation_manager
    if _correlation_manager is None:
        try:
            from bot.portfolio.correlation_manager import CorrelationManager
            _correlation_manager = CorrelationManager()
        except Exception as exc:
            logger.warning("Could not initialise CorrelationManager: %s", exc)
    return _correlation_manager


@app.get("/api/portfolio/correlations")
async def get_portfolio_correlations(lookback_days: int = 30):
    """
    Return the pairwise correlation matrix for tracked pairs.

    Args:
        lookback_days: Number of days of data to use

    Returns:
        Correlation matrix as a nested dict and list of pairs
    """
    try:
        manager = _get_correlation_manager()
        pairs = registry.list_enabled_pairs()

        if manager is not None and broker_adapter is not None:
            # Feed recent close prices into the correlation manager
            for pair in pairs:
                try:
                    raw = broker_adapter.fetch_ohlcv(pair, timeframe="1d", limit=lookback_days + 5)
                    if raw:
                        import pandas as _pd
                        closes = _pd.Series(
                            [c[4] for c in raw],
                            index=_pd.to_datetime([c[0] for c in raw], unit="ms", utc=True),
                        )
                        manager.update_prices(pair, closes)
                except Exception as pe:
                    logger.debug(f"Correlation: could not fetch prices for {pair}: {pe}")

            corr_df = manager.get_correlation_matrix(lookback_days=lookback_days)
            if not corr_df.empty:
                matrix = corr_df.to_dict()
                return {
                    "pairs": list(corr_df.columns),
                    "matrix": matrix,
                    "lookback_days": lookback_days,
                    "is_demo": False,
                }

        # Demo / fallback: synthetic correlation data
        import random as _random
        rng = _random.Random(42)
        demo_pairs = pairs[:4] if len(pairs) >= 2 else ["BTC/USDT:USDT", "ETH/USDT:USDT"]
        matrix: dict = {}
        for p1 in demo_pairs:
            matrix[p1] = {}
            for p2 in demo_pairs:
                if p1 == p2:
                    matrix[p1][p2] = 1.0
                else:
                    matrix[p1][p2] = round(rng.uniform(0.4, 0.9), 3)
        return {
            "pairs": demo_pairs,
            "matrix": matrix,
            "lookback_days": lookback_days,
            "is_demo": True,
        }
    except Exception as e:
        logger.error(f"Error getting correlations: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "message": str(e)}
        )


# ---------------------------------------------------------------------------
# Sentiment history endpoint
# ---------------------------------------------------------------------------

@app.get("/api/sentiment/history")
async def get_sentiment_history(asset: str = "BTC", hours: int = 24):
    """
    Return historical sentiment scores for an asset.

    Args:
        asset: Asset symbol (e.g. BTC, ETH)
        hours: Number of hours of history

    Returns:
        List of {timestamp, score} data points
    """
    try:
        # Try to load from SentimentStorage if available
        history = []
        try:
            db_path = os.getenv("SENTIMENT_DB_PATH", "/app/data/sentiment.db")
            storage = SentimentStorage(db_path=db_path)
            raw = storage.get_history(asset.upper(), hours=hours)
            history = [{"timestamp": r["timestamp"], "score": r["score"]} for r in raw]
        except Exception:
            pass

        if not history:
            # Demo data
            import random as _random
            rng = _random.Random(ord(asset[0]) if asset else 42)
            now = datetime.now(timezone.utc)
            score = rng.uniform(-0.3, 0.3)
            for i in range(hours):
                ts = (now - timedelta(hours=hours - i)).isoformat()
                score = max(-1.0, min(1.0, score + rng.uniform(-0.1, 0.1)))
                history.append({"timestamp": ts, "score": round(score, 3)})
            return {"asset": asset.upper(), "hours": hours, "data": history, "is_demo": True}

        return {"asset": asset.upper(), "hours": hours, "data": history, "is_demo": False}
    except Exception as e:
        logger.error(f"Error getting sentiment history: {e}")
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


# ============================================================================
# WebSocket endpoint
# ============================================================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    Real-time streaming WebSocket endpoint.

    Clients subscribe to channels and receive push updates:
      positions, trades, sentiment, status, alerts, opportunities
    """
    if ws_manager.client_count >= WS_MAX_CLIENTS:
        await websocket.close(code=1008, reason="Max clients reached")
        return

    await ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await ws_manager.handle_message(websocket, data)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.debug(f"WebSocket error: {exc}")
    finally:
        await ws_manager.disconnect(websocket)


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
