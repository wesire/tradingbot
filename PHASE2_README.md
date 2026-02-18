# Phase 2: Alert Execution Pipeline

## Overview

Phase 2 extends the TradingView webhook gateway with a complete end-to-end alert execution pipeline. Alerts now flow from ingestion through validation, risk gating, and execution with full auditability and idempotency.

## Architecture

```
TradingView Alert
    │
    ├─► Webhook Gateway (POST /tv/webhook)
    │   ├─► Authentication & Validation
    │   ├─► Alert Storage (idempotent)
    │   └─► Status: accepted
    │
    ├─► Execution Worker (background)
    │   ├─► Poll queued alerts
    │   ├─► Apply risk gates:
    │   │   ├─► Freshness check
    │   │   ├─► Confidence threshold
    │   │   ├─► Allowed symbols
    │   │   └─► Allowed timeframes
    │   ├─► Execute via Bot Client
    │   └─► Update status: executed/failed
    │
    └─► Operator Dashboard (GET /)
        ├─► Real-time metrics
        ├─► Alert list (latest 20)
        └─► Auto-refresh (10s)
```

## Key Features

### 1. **Alert Lifecycle Management**
- **Accepted**: Alert passed authentication and stored
- **Queued**: Picked up by worker for processing
- **Executed**: Successfully sent to bot and executed
- **Failed**: Rejected by risk gates or execution failed
- **Ignored**: Duplicate alert (idempotent)

### 2. **Idempotency**
Duplicate detection using composite key: `nonce + symbol + event_time`
- First request: stored and processed
- Duplicate requests: ignored with clear status

### 3. **Risk Gates**
Configurable filters before execution:
- **Freshness**: Reject alerts older than max age (default 10m)
- **Confidence**: Minimum confidence threshold (default 0.9)
- **Symbols**: Whitelist of allowed trading pairs
- **Timeframes**: Whitelist of allowed timeframes

### 4. **Bot Integration**
Clean abstraction layer with multiple adapters:
- **FreqtradeAdapter**: Integrates with Freqtrade API
- **MockBotClient**: For testing
- Retry logic with exponential backoff
- Graceful error handling

### 5. **Operator Dashboard**
Real-time web UI at http://localhost:8000/:
- Service health and uptime
- Alert counts by status
- Latest 20 alerts with full details
- Auto-refresh every 10 seconds
- Status chips (color-coded)

## API Endpoints

### **POST /tv/webhook**
Receive TradingView alerts
- Validates authentication (secret, timestamp, nonce)
- Stores alert with idempotency
- Queues for execution
- Returns alert ID

### **GET /alerts**
List alerts with filtering
- `?limit=50` - Max results (default 50)
- `?status=executed` - Filter by status
- `?symbol=BTCUSDT` - Filter by symbol

### **GET /alerts/{id}**
Get single alert details
- Returns full alert record
- Includes execution status and timestamps

### **GET /stats**
System statistics
- Total alert count
- Counts by status
- Last processed time
- Recent activity (1 hour)

### **GET /health**
Health check endpoint
- Service status
- Uptime
- Version info

### **GET /**
Operator dashboard (HTML)
- Real-time metrics
- Latest alerts table
- Auto-refresh

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `TV_WEBHOOK_SECRET` | `your_webhook_secret_here` | Shared secret for authentication |
| `TV_WEBHOOK_PORT` | `8000` | Webhook server port |
| `ALERT_MAX_AGE_SECONDS` | `600` | Maximum alert age (10 minutes) |
| `MIN_CONFIDENCE` | `0.9` | Minimum confidence threshold (90%) |
| `ALLOWED_SYMBOLS` | `BTC/USDT:USDT` | Comma-separated list of allowed symbols |
| `ALLOWED_TIMEFRAMES` | `5m` | Comma-separated list of allowed timeframes |
| `EXECUTION_ENABLED` | `true` | Enable actual execution (false = dry-run only) |
| `BOT_TYPE` | `freqtrade` | Bot client type (freqtrade/mock) |
| `FREQTRADE_API_URL` | `http://bot:8080` | Freqtrade API URL |
| `FREQTRADE_API_USERNAME` | - | Freqtrade API username (if auth enabled) |
| `FREQTRADE_API_PASSWORD` | - | Freqtrade API password (if auth enabled) |

### Example .env

```bash
# Phase 2 Configuration
TV_WEBHOOK_SECRET=your_secure_secret_here
ALERT_MAX_AGE_SECONDS=600
MIN_CONFIDENCE=0.9
ALLOWED_SYMBOLS=BTC/USDT:USDT,ETH/USDT:USDT
ALLOWED_TIMEFRAMES=5m,15m
EXECUTION_ENABLED=true

# Bot Integration
BOT_TYPE=freqtrade
FREQTRADE_API_URL=http://bot:8080
```

## Usage

### Start Services

```bash
# Start all services with docker-compose
docker-compose up -d --build

# Check service health
curl http://localhost:8000/health

# View dashboard
open http://localhost:8000/
```

### Send Test Alert

```bash
curl -X POST http://localhost:8000/tv/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTCUSDT",
    "timeframe": "5m",
    "side": "long",
    "setup_id": "test_001",
    "confidence": 0.95,
    "price": 40000.0,
    "event_time": "'$(date +%s000)'",
    "secret": "your_webhook_secret_here",
    "timestamp": '$(date +%s)',
    "nonce": "test_'$(date +%s)'"
  }'
```

### Check Alert Status

```bash
# List all alerts
curl http://localhost:8000/alerts?limit=10 | jq

# Get specific alert
curl http://localhost:8000/alerts/1 | jq

# Get statistics
curl http://localhost:8000/stats | jq
```

### Example Response

```json
{
  "success": true,
  "message": "Alert received and queued for execution",
  "alert_id": "42",
  "action_taken": "accepted"
}
```

## Verification Steps

### 1. **Service Health**
```bash
curl http://localhost:8000/health
# Expected: {"status": "healthy", "uptime_seconds": 123.45}
```

### 2. **Send Valid Alert** (high confidence)
```bash
# Alert with confidence 0.95 (above threshold)
curl -X POST http://localhost:8000/tv/webhook -H "Content-Type: application/json" \
  -d '{"symbol":"BTCUSDT","timeframe":"5m","side":"long","setup_id":"test","confidence":0.95,"price":40000,"event_time":"'$(date +%s000)'","secret":"your_webhook_secret_here","timestamp":'$(date +%s)',"nonce":"unique_'$(date +%s)'"}'

# Check status progresses: accepted → queued → executed
curl http://localhost:8000/alerts/1
```

### 3. **Send Duplicate Alert**
```bash
# Send same alert twice (same nonce)
# First: accepted
# Second: ignored (duplicate)
```

### 4. **Send Stale Alert**
```bash
# Alert with old timestamp (> 10 minutes)
# Expected: status=failed, reason="Alert too old"
```

### 5. **Send Low Confidence Alert**
```bash
# Alert with confidence 0.5 (below threshold)
# Expected: status=failed, reason="Confidence too low"
```

### 6. **Dashboard**
Open http://localhost:8000/ in browser
- Verify service shows "RUNNING"
- Verify alert counts update
- Verify alerts appear in table
- Verify status chips show correct colors

## Testing

```bash
# Run all Phase 2 tests
pytest tests/test_alert_storage.py tests/test_bot_client.py tests/test_execution_worker.py tests/test_webhook.py -v

# Expected: 53 tests passing
# - 11 alert storage tests
# - 14 bot client tests
# - 17 execution worker tests
# - 21 webhook tests
```

## Logs

Structured logs for all lifecycle events:

```
INFO - Alert accepted: id=42, BTCUSDT long confidence=0.95 setup=test_001
INFO - Processing alert 42: BTCUSDT long confidence=0.95
INFO - Signal executed successfully: order_id=mock_BTCUSDT_1234567890
INFO - Updated alert 42: status=executed, ref=mock_BTCUSDT_1234567890
```

## Database Schema

### alerts table
- `id` - Primary key
- `received_at` - Timestamp when alert received
- `symbol` - Trading pair
- `timeframe` - Chart timeframe
- `side` - Trade direction (long/short)
- `setup_id` - Setup identifier
- `confidence` - Signal confidence (0-1)
- `price` - Price at alert time
- `event_time` - Event timestamp from TradingView
- `nonce` - Unique nonce (for replay prevention)
- `payload_json` - Full alert payload
- `validation_result` - Validation outcome
- `status` - Current status (accepted/queued/executed/failed/ignored)
- `fail_reason` - Failure reason (if failed)
- `execution_ref` - Execution reference (order ID)
- `processed_at` - Processing completion timestamp

### Unique constraint
`(nonce, symbol, event_time)` - Ensures idempotency

## Troubleshooting

### Alert stuck in "accepted" status
- Check worker is running: `docker-compose logs webhook | grep "worker started"`
- Check worker is polling: Look for "Processing N queued alerts" in logs

### All alerts failing with "confidence too low"
- Check MIN_CONFIDENCE setting in .env
- Ensure test alerts have confidence >= MIN_CONFIDENCE

### Alert failing with "Symbol not allowed"
- Check ALLOWED_SYMBOLS in .env includes the symbol
- Symbol matching is case-insensitive and ignores separators

### Bot execution failing
- Check bot service is running: `docker-compose ps bot`
- Check bot API is accessible: `curl http://bot:8080/api/v1/ping`
- Review FREQTRADE_API_URL setting

### Dashboard not updating
- Check browser console for JavaScript errors
- Verify /alerts and /stats endpoints work: `curl http://localhost:8000/stats`

## Screenshot

![Phase 2 Dashboard](https://github.com/user-attachments/assets/f400d06f-a347-43a2-a2cd-e31fccd0214c)

The dashboard shows:
- **Service Status**: Real-time running indicator
- **Total Alerts**: Count of all alerts received
- **Executed**: Successfully processed alerts
- **Failed**: Rejected or errored alerts
- **Latest Alerts**: Table with ID, time, symbol, side, confidence, price, status, and setup
- **Auto-refresh**: Updates every 10 seconds

## Security

- Webhook secret validation (constant-time comparison)
- Timestamp validation (reject stale alerts)
- Nonce validation (replay attack prevention)
- Rate limiting per IP
- No secrets in logs
- SQL injection protection (parameterized queries)

## Performance

- Async execution worker (non-blocking)
- Efficient polling (2-second interval)
- Indexed database queries
- Retry logic with exponential backoff
- Connection pooling via httpx

## Next Steps (Future Phases)

- [ ] Add alert priority queue
- [ ] Support multiple bot integrations
- [ ] Add webhook notification for execution results
- [ ] Implement alert replay/reprocess
- [ ] Add advanced filtering in dashboard
- [ ] Export alerts to CSV/JSON
- [ ] Add Telegram/Discord notifications
- [ ] Metrics export (Prometheus)
