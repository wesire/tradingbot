# Phase 2.1: Production Hardening - Security & Reliability

## Overview

Phase 2.1 adds enterprise-grade production hardening to the TradingView webhook gateway, making it safe to expose to the internet with strong security, reliability, and operational controls.

---

## 🔒 Security Features

### 1. HMAC Signature Authentication

Optional cryptographic request signing for tamper-proof authentication.

#### How It Works

1. Client generates signature: `HMAC-SHA256(secret, "{timestamp}.{nonce}.{raw_body}")`
2. Client sends headers:
   - `X-TV-Timestamp`: Unix timestamp (seconds)
   - `X-TV-Nonce`: Unique request identifier
   - `X-TV-Signature`: Hex-encoded HMAC signature
3. Server verifies signature and enforces timestamp freshness

#### Configuration

```bash
# .env
REQUIRE_HMAC=false              # Set true to require HMAC on all requests
HMAC_SKEW_SECONDS=60            # Maximum timestamp age (default 60s)
NONCE_TTL_SECONDS=600           # Nonce replay protection window (default 10min)
```

#### Example: Generate HMAC Signature (Python)

```python
import hmac
import hashlib
import time
import json
import requests

# Configuration
SECRET = "your_webhook_secret_here"
URL = "http://localhost:8000/tv/webhook"

# Prepare payload
payload = {
    "symbol": "BTCUSDT",
    "timeframe": "5m",
    "side": "long",
    "setup_id": "example_001",
    "confidence": 0.95,
    "price": 40000.0,
    "event_time": str(int(time.time() * 1000)),
    "secret": SECRET,
    "timestamp": int(time.time()),
    "nonce": f"unique_{int(time.time() * 1000000)}"
}

# Generate HMAC signature
timestamp = str(payload["timestamp"])
nonce = payload["nonce"]
body = json.dumps(payload).encode('utf-8')

message = f"{timestamp}.{nonce}.".encode('utf-8') + body
signature = hmac.new(SECRET.encode('utf-8'), message, hashlib.sha256).hexdigest()

# Send request with HMAC headers
headers = {
    "Content-Type": "application/json",
    "X-TV-Timestamp": timestamp,
    "X-TV-Nonce": nonce,
    "X-TV-Signature": signature
}

response = requests.post(URL, data=body, headers=headers)
print(f"Status: {response.status_code}")
print(f"Response: {response.json()}")
```

#### Example: Generate HMAC Signature (cURL)

```bash
#!/bin/bash

SECRET="your_webhook_secret_here"
URL="http://localhost:8000/tv/webhook"

# Generate timestamp and nonce
TIMESTAMP=$(date +%s)
NONCE="nonce_$(date +%s%N)"

# Create payload
PAYLOAD=$(cat <<EOF
{
  "symbol": "BTCUSDT",
  "timeframe": "5m",
  "side": "long",
  "setup_id": "curl_example",
  "confidence": 0.95,
  "price": 40000.0,
  "event_time": "$(date +%s000)",
  "secret": "$SECRET",
  "timestamp": $TIMESTAMP,
  "nonce": "$NONCE"
}
EOF
)

# Generate HMAC signature
MESSAGE="${TIMESTAMP}.${NONCE}.${PAYLOAD}"
SIGNATURE=$(echo -n "$MESSAGE" | openssl dgst -sha256 -hmac "$SECRET" | awk '{print $2}')

# Send request
curl -X POST "$URL" \
  -H "Content-Type: application/json" \
  -H "X-TV-Timestamp: $TIMESTAMP" \
  -H "X-TV-Nonce: $NONCE" \
  -H "X-TV-Signature: $SIGNATURE" \
  -d "$PAYLOAD"
```

### 2. Replay Protection

Database-backed nonce storage prevents replay attacks across restarts.

- **Nonce Uniqueness**: Each nonce can only be used once within TTL window
- **Persistent Storage**: Nonces stored in SQLite database
- **Automatic Cleanup**: Expired nonces cleaned up every 5 minutes
- **Works with or without HMAC**: Legacy secret-only mode still protected

### 3. Rate Limiting

Token bucket algorithm for smooth rate limiting with burst allowance.

```bash
# .env
RATE_LIMIT_PER_MINUTE=30        # Base rate limit per IP
```

- **Per-IP Limiting**: Each IP gets independent rate limit
- **Burst Capacity**: 1.5x base rate (configurable)
- **Smooth Refill**: Tokens refill continuously, not in batches
- **429 Response**: Returns `Retry-After` header with wait time

### 4. IP Filtering

CIDR-based allowlist/denylist with reverse proxy support.

```bash
# .env
IP_ALLOWLIST=                   # Comma-separated CIDR ranges (empty = allow all)
IP_DENYLIST=                    # Comma-separated CIDR ranges to block
TRUSTED_PROXY_CIDRS=            # Trust X-Forwarded-For from these proxies only
```

#### Example IP Configuration

```bash
# Only allow from specific networks
IP_ALLOWLIST=192.168.0.0/16,10.0.0.0/8

# Block specific bad actors
IP_DENYLIST=1.2.3.4/32,5.6.7.0/24

# Trust X-Forwarded-For from Cloudflare proxies
TRUSTED_PROXY_CIDRS=173.245.48.0/20,103.21.244.0/22
```

### 5. Payload Size Limit

Prevent resource exhaustion from oversized payloads.

```bash
# .env
MAX_PAYLOAD_SIZE_KB=32          # Maximum payload size (default 32KB)
```

Returns `413 Request Entity Too Large` if exceeded.

---

## 🛡️ Operational Safety

### Kill Switches

Multiple layers of operational safety controls.

#### 1. Webhook Accepting Switch

Control whether webhook accepts new requests.

```bash
# .env
WEBHOOK_ACCEPTING_ENABLED=true  # Set false to reject all webhook requests
```

**Admin API**:
```bash
# Disable webhook
curl -X POST http://localhost:8000/admin/webhook/disable \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"

# Enable webhook
curl -X POST http://localhost:8000/admin/webhook/enable \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

When disabled:
- Returns `503 Service Unavailable`
- No alerts stored
- Existing queued alerts continue processing

#### 2. Execution Switch

Control whether alerts are executed (sent to bot).

```bash
# .env
EXECUTION_ENABLED=true          # Set false to disable execution
```

**Admin API**:
```bash
# Disable execution
curl -X POST http://localhost:8000/admin/execution/disable \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"

# Enable execution
curl -X POST http://localhost:8000/admin/execution/enable \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

When disabled:
- Alerts are accepted and stored
- Status set to `ignored` with reason `execution_disabled`
- No bot requests made

#### 3. Live Trading Confirmation

Prevent accidental live trading.

```bash
# .env
RUNMODE=dry-run                 # Trading mode
CONFIRM_LIVE_TRADING=           # MUST be "YES" for live trading
```

**Safety Rules**:
- If `RUNMODE != "dry-run"` and `CONFIRM_LIVE_TRADING != "YES"`, service refuses to start
- Forces explicit confirmation for live trading mode
- Prevents configuration errors from causing unintended live trades

### Circuit Breaker

Automatic protection when bot integration fails repeatedly.

```bash
# .env
CIRCUIT_BREAKER_THRESHOLD=5     # Failures to open circuit
CIRCUIT_BREAKER_WINDOW_SECONDS=300  # Time window for counting failures
CIRCUIT_BREAKER_COOLDOWN_SECONDS=60 # Cooldown before retry
```

#### Circuit States

1. **CLOSED** (Normal): All requests proceed
2. **OPEN** (Bot Down): Requests blocked, alerts marked as failed
3. **HALF-OPEN** (Testing): Limited requests allowed to test recovery

#### Admin API

```bash
# Force reset circuit breaker
curl -X POST http://localhost:8000/admin/circuit/reset \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

#### Monitoring

Circuit breaker status included in `/stats` endpoint:

```json
{
  "circuit_breaker": {
    "state": "closed",
    "failure_count": 0,
    "failure_threshold": 5,
    "window_seconds": 300
  }
}
```

---

## 📊 Structured Logging

All security and operational events logged in JSON format for easy parsing.

### Log Events

1. **request_accepted**: Successful request with auth method
2. **request_rejected**: Failed authentication with reason
3. **hmac_verification**: HMAC check result
4. **replay_detected**: Nonce replay attempt
5. **rate_limit_exceeded**: Rate limit triggered
6. **ip_blocked**: IP filter rejection
7. **status_transition**: Alert lifecycle changes
8. **circuit_state_change**: Circuit breaker state changes
9. **kill_switch**: Operational switch toggled

### Example Log Entry

```json
{
  "timestamp": "2026-02-18T01:30:45.123456",
  "event_type": "request_accepted",
  "alert_id": 42,
  "symbol": "BTCUSDT",
  "side": "long",
  "setup_id": "scalp_001",
  "confidence": 0.95,
  "client_ip": "192.168.1.100",
  "auth_method": "hmac",
  "idempotency_key": "nonce_123:BTCUSDT:1708221045000"
}
```

---

## 🔧 Admin Endpoints

Protected endpoints for operational control.

### Setup

```bash
# .env
ADMIN_TOKEN=your_secure_random_token_here
```

### Endpoints

#### GET /admin/config

Get current configuration (secrets redacted).

```bash
curl http://localhost:8000/admin/config \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

**Response**:
```json
{
  "success": true,
  "config": {
    "security": {
      "require_hmac": false,
      "hmac_skew_seconds": 60,
      "rate_limit_per_minute": 30,
      "secret_configured": true
    },
    "operational": {
      "webhook_accepting": true,
      "execution_enabled": true,
      "runmode": "dry-run"
    },
    "circuit_breaker": {
      "state": "closed",
      "failure_count": 0
    }
  }
}
```

#### POST /admin/execution/enable|disable

Enable/disable alert execution.

#### POST /admin/webhook/enable|disable

Enable/disable webhook accepting.

#### POST /admin/circuit/reset

Force reset circuit breaker to closed state.

---

## 🚀 Deployment Guide

### Recommended Architecture

```
Internet
    │
    ▼
┌─────────────────┐
│   Cloudflare    │  ← DDoS protection, SSL termination
│   or Nginx      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Webhook Gateway│  ← This application (port 8000)
│  (Docker)       │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Trading Bot    │  ← Freqtrade or other bot
│  (Docker)       │
└─────────────────┘
```

### Production Checklist

#### Before Launch

- [ ] Set `REQUIRE_HMAC=true` for production
- [ ] Configure strong `TV_WEBHOOK_SECRET` (32+ characters)
- [ ] Set `ADMIN_TOKEN` (random, secure)
- [ ] Configure `IP_ALLOWLIST` or `IP_DENYLIST`
- [ ] Set `TRUSTED_PROXY_CIDRS` for reverse proxy
- [ ] Verify `CONFIRM_LIVE_TRADING=YES` if live trading
- [ ] Review rate limits for your traffic
- [ ] Test circuit breaker behavior
- [ ] Set up structured log collection

#### SSL/TLS Setup

**CRITICAL**: Always use HTTPS in production.

**Option 1: Cloudflare** (Recommended)
- Free SSL/TLS
- Built-in DDoS protection
- Add webhook server as origin
- Configure in Cloudflare dashboard

**Option 2: Nginx Reverse Proxy**
```nginx
server {
    listen 443 ssl http2;
    server_name webhook.yourdomain.com;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Then configure:
```bash
# .env
TRUSTED_PROXY_CIDRS=127.0.0.1/32  # Trust localhost
```

### Docker Compose Production Example

```yaml
version: '3.8'

services:
  webhook:
    build: .
    container_name: webhook_gateway
    restart: unless-stopped
    ports:
      - "127.0.0.1:8000:8000"  # Bind to localhost only
    volumes:
      - ./alerts.db:/app/alerts.db
      - ./logs:/app/logs
    environment:
      # Security
      - TV_WEBHOOK_SECRET=${TV_WEBHOOK_SECRET}
      - REQUIRE_HMAC=true
      - HMAC_SKEW_SECONDS=60
      - RATE_LIMIT_PER_MINUTE=30
      - IP_ALLOWLIST=${IP_ALLOWLIST}
      - TRUSTED_PROXY_CIDRS=${TRUSTED_PROXY_CIDRS}
      
      # Operational
      - WEBHOOK_ACCEPTING_ENABLED=true
      - EXECUTION_ENABLED=true
      - RUNMODE=dry-run
      - CONFIRM_LIVE_TRADING=${CONFIRM_LIVE_TRADING}
      
      # Circuit Breaker
      - CIRCUIT_BREAKER_THRESHOLD=5
      - CIRCUIT_BREAKER_WINDOW_SECONDS=300
      
      # Admin
      - ADMIN_TOKEN=${ADMIN_TOKEN}
    
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

### Monitoring

#### Health Check

```bash
curl http://localhost:8000/health
```

#### Stats Endpoint

```bash
curl http://localhost:8000/stats | jq
```

**Response includes**:
- Service uptime
- Alert counts by status
- Circuit breaker state
- Operational flags
- Security configuration
- Active nonce count

#### Log Monitoring

Use tools like:
- **Loki + Grafana**: Log aggregation and visualization
- **ELK Stack**: Elasticsearch, Logstash, Kibana
- **CloudWatch Logs**: AWS native solution

Example Loki query:
```logql
{job="webhook_gateway"} | json | event_type="rate_limit_exceeded"
```

---

## 🧪 Testing

### Unit Tests

```bash
# Run all security feature tests
pytest tests/test_security_features.py -v

# Test specific module
pytest tests/test_security_features.py::TestHMACAuthenticator -v
```

### Integration Tests

```bash
# Run webhook integration tests
pytest tests/test_webhook_integration.py -v
```

### Manual Testing

#### Test HMAC Authentication

```bash
# Use the Python example above or:
python scripts/test_hmac_webhook.py
```

#### Test Rate Limiting

```bash
# Rapid fire requests
for i in {1..40}; do
  curl -X POST http://localhost:8000/tv/webhook \
    -H "Content-Type: application/json" \
    -d "{\"symbol\":\"BTCUSDT\",\"timeframe\":\"5m\",\"side\":\"long\",\"setup_id\":\"rate_test\",\"confidence\":0.95,\"price\":40000,\"event_time\":\"$(date +%s000)\",\"secret\":\"your_webhook_secret_here\",\"timestamp\":$(date +%s),\"nonce\":\"test_$i\"}"
done
```

#### Test Circuit Breaker

1. Stop bot service: `docker-compose stop bot`
2. Send alerts (circuit opens after 5 failures in 5 minutes)
3. Verify alerts fail with circuit reason
4. Start bot: `docker-compose start bot`
5. Wait for cooldown, verify circuit closes

---

## 📈 Performance Considerations

### Resource Usage

- **CPU**: Minimal (<5% on modern hardware)
- **Memory**: ~100MB baseline + ~1KB per active nonce
- **Storage**: Database grows ~1KB per alert
- **Network**: <10KB per webhook request

### Scaling

- **Vertical**: Single instance handles 100+ req/s
- **Horizontal**: Multiple instances with shared database
- **Rate Limits**: Adjust per traffic patterns

### Database Maintenance

```bash
# Vacuum database monthly
sqlite3 alerts.db "VACUUM;"

# Check database size
ls -lh alerts.db
```

---

## 🐛 Troubleshooting

### HMAC Signature Mismatch

**Symptom**: `401 Unauthorized: Invalid HMAC signature`

**Causes**:
1. Clock skew between client and server
2. Incorrect secret
3. Body encoding issues (UTF-8 required)
4. Header/body mismatch

**Solution**:
```bash
# Check time sync
date +%s

# Verify secret
echo $TV_WEBHOOK_SECRET

# Test with simple payload
python scripts/test_hmac_webhook.py
```

### Rate Limiting Too Strict

**Symptom**: Legitimate requests get `429 Too Many Requests`

**Solution**:
```bash
# Increase rate limit
RATE_LIMIT_PER_MINUTE=60  # or higher
```

### Circuit Breaker Stuck Open

**Symptom**: All alerts fail with "circuit breaker open"

**Solution**:
```bash
# Check bot connectivity
curl http://bot:8080/api/v1/ping

# Force reset circuit
curl -X POST http://localhost:8000/admin/circuit/reset \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

### Replay Protection False Positives

**Symptom**: Unique requests rejected as replays

**Cause**: Nonce collision (very unlikely with good nonce generation)

**Solution**:
```bash
# Ensure nonces are truly unique
# Bad:  nonce = "test_1"
# Good: nonce = f"unique_{uuid.uuid4()}_{time.time_ns()}"
```

---

## 🔐 Security Best Practices

1. **Always use HTTPS** in production
2. **Set REQUIRE_HMAC=true** for production
3. **Use strong secrets** (32+ random characters)
4. **Rotate secrets periodically** (every 90 days)
5. **Monitor structured logs** for suspicious activity
6. **Configure IP allowlist** if possible
7. **Keep ADMIN_TOKEN secure** (never commit to git)
8. **Review circuit breaker alerts** regularly
9. **Test disaster recovery** procedures
10. **Keep dependencies updated** for security patches

---

## 📞 Support

For issues or questions:
- Review logs: `docker-compose logs webhook`
- Check `/stats` endpoint for system state
- Verify configuration with `/admin/config`
- Test with minimal setup first
- Use structured logs for debugging
