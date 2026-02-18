# Trading Bot Operations Runbook

## Quick Reference

- **Start system**: `make up`
- **Stop system**: `make down`
- **Check health**: `make health`
- **View logs**: `make logs`
- **Run smoke tests**: `make smoke`

## Service URLs

- **Dashboard**: http://localhost:3000
- **Webhook API**: http://localhost:8000
- **Webhook Health**: http://localhost:8000/health

## Starting and Stopping

### Start All Services
```bash
docker-compose up -d
# or
make up
```

This starts:
- `bot` - Freqtrade trading bot
- `webhook` - FastAPI webhook gateway
- `dashboard` - React dashboard UI

### Stop All Services
```bash
docker-compose down
# or
make down
```

### Restart Services
```bash
make restart
```

### Start Individual Service
```bash
docker-compose up -d webhook
docker-compose up -d dashboard
```

## Monitoring

### Check Service Status
```bash
make status
# or
docker-compose ps
```

### View Logs
```bash
# All services
make logs

# Specific service
make logs-bot
make logs-webhook
make logs-dashboard

# or
docker-compose logs -f webhook
```

### Health Checks
```bash
make health
```

This checks:
- Webhook API health endpoint
- Dashboard accessibility

## Switching Between Dry-Run and Live Trading

### CRITICAL: Safety Protocol for Going Live

**⚠️ WARNING: Live trading involves real money. Follow this protocol exactly.**

1. **Ensure you're ready**
   - Backtests show positive results
   - Strategy has been validated in dry-run for at least 1 week
   - Risk parameters are properly configured
   - You understand the risks

2. **Pre-flight checklist**
   ```bash
   make check-live
   ```
   
   Review all settings carefully:
   - Exchange configuration
   - API key permissions (ensure they're correct)
   - Risk limits
   - Max daily drawdown
   - Position sizes

3. **Update .env file**
   ```bash
   # Edit .env
   TRADING_MODE=live
   LIVE_TRADING_ENABLED=true
   EXCHANGE_SANDBOX=false
   ```

4. **Restart bot service**
   ```bash
   docker-compose restart bot
   ```

5. **Monitor closely**
   - Watch logs: `make logs-bot`
   - Check dashboard
   - Verify trades are executing as expected
   - **Stay available to intervene if needed**

### Emergency Stop (Kill Switch)

If you need to immediately stop all trading:

1. **Via Dashboard** (recommended)
   - Navigate to Controls page
   - Click "Emergency Stop" button
   - Confirm action

2. **Via Docker**
   ```bash
   docker-compose stop bot
   ```

3. **Via Exchange**
   - Log into exchange web interface
   - Cancel all open orders
   - Close all positions manually

## Common Issues and Fixes

### Issue: Webhook service returns 401 Unauthorized

**Cause**: Webhook secret mismatch

**Fix**:
```bash
# Check .env file
cat .env | grep TV_WEBHOOK_SECRET

# Ensure TradingView alert uses same secret
# Update TradingView alert JSON with correct secret
```

### Issue: Dashboard not loading

**Cause**: Dashboard service not started or port conflict

**Fix**:
```bash
# Check if dashboard is running
docker-compose ps dashboard

# If not running
docker-compose up -d dashboard

# If port conflict, change in .env
DASHBOARD_PORT=3001
docker-compose restart dashboard
```

### Issue: Bot not placing trades in live mode

**Possible causes**:
1. Risk engine blocking trades (check daily drawdown limit)
2. Signal confidence too low
3. Filters not passing
4. Insufficient balance

**Debug**:
```bash
# Check bot logs
make logs-bot

# Look for:
# - "Risk engine: cannot trade" messages
# - "Signal confidence too low" messages
# - "Insufficient balance" errors

# Check risk engine status in dashboard
# Navigate to Dashboard > Bot Status > Risk Engine
```

### Issue: No sentiment data

**Cause**: Sentiment provider not initialized or returning errors

**Fix**:
```bash
# Check webhook logs
make logs-webhook | grep sentiment

# Sentiment uses mock provider by default
# To integrate real sentiment provider:
# 1. Implement a SentimentProvider subclass
# 2. Register it in tv_gateway/main.py
# 3. Add necessary API keys to .env
```

### Issue: High memory usage

**Cause**: Too many candles loaded, memory leak, or multiple services

**Fix**:
```bash
# Check memory usage
docker stats

# Restart services
make restart

# If persistent, check strategy startup_candle_count
# Reduce if very high (e.g., >500)
```

## Configuration Changes

### Add a New Trading Pair

1. **Update config/pairs.yaml**
   ```yaml
   - symbol: "NEW/USDT:USDT"
     enabled: true
     timeframe: "5m"
     leverage_cap: 10
     stake_allocation: 0.2
     strategy: "new_strategy"
   ```

2. **Register strategy** in `bot/strategy/registry.py`
   ```python
   STRATEGY_REGISTRY["NEW/USDT:USDT"] = "NewStrategy"
   ```

3. **Validate configuration**
   ```bash
   python -c "from bot.config.validator import validate_config_at_startup; validate_config_at_startup()"
   ```

4. **Restart services**
   ```bash
   make restart
   ```

### Update Risk Parameters

1. **Edit config/risk.yaml** or **.env**
   ```bash
   # In .env
   MAX_DAILY_DRAWDOWN=0.03
   MAX_CONSECUTIVE_LOSSES=4
   ```

2. **Restart bot**
   ```bash
   docker-compose restart bot
   ```

## Backup and Recovery

### Backup Important Data

```bash
# Create backup directory
mkdir -p backups/$(date +%Y%m%d)

# Backup databases
cp alerts.db backups/$(date +%Y%m%d)/
cp sentiment.db backups/$(date +%Y%m%d)/

# Backup configuration
cp .env backups/$(date +%Y%m%d)/
cp -r config/ backups/$(date +%Y%m%d)/

# Backup artifacts
cp -r artifacts/ backups/$(date +%Y%m%d)/
```

### Restore from Backup

```bash
# Stop services
make down

# Restore databases
cp backups/YYYYMMDD/alerts.db .
cp backups/YYYYMMDD/sentiment.db .

# Restore config
cp backups/YYYYMMDD/.env .
cp -r backups/YYYYMMDD/config/ .

# Start services
make up
```

## Performance Optimization

### Reduce Latency

1. **Use faster timeframes** (but test thoroughly first)
2. **Enable webhook rate limiting** in .env
3. **Optimize strategy indicators** (reduce calculations)
4. **Use SSD for database** storage

### Scale for Multiple Pairs

1. **Increase max_open_trades** in config/pairs.yaml
2. **Allocate resources appropriately**:
   ```yaml
   # docker-compose.yml
   services:
     bot:
       deploy:
         resources:
           limits:
             memory: 2G
   ```
3. **Monitor CPU/memory** usage with `docker stats`

## Troubleshooting Commands

```bash
# Full system health check
make smoke

# Check all services
make status

# View recent errors
docker-compose logs --tail=50 webhook | grep ERROR
docker-compose logs --tail=50 bot | grep ERROR

# Test webhook endpoint
curl http://localhost:8000/health

# Test sentiment API
curl http://localhost:8000/api/sentiment/summary | python -m json.tool

# Test opportunities API
curl http://localhost:8000/api/opportunities | python -m json.tool

# Shell into container for debugging
make shell-webhook
make shell-bot

# View resource usage
docker stats

# Clear old logs
docker-compose logs --tail=0 webhook > /dev/null
```

## Security Best Practices

1. **Never commit .env** to git
2. **Rotate API keys** regularly
3. **Use read-only** API keys when possible
4. **Enable IP whitelist** on exchange
5. **Monitor for** unauthorized access in logs
6. **Keep webhook secret** secure (32+ character random string)
7. **Review logs** for secret leaks: `make smoke` includes this check

## Contact and Support

For issues or questions:
- Check logs first: `make logs`
- Run smoke tests: `make smoke`
- Review this runbook
- Check GitHub issues: https://github.com/wesire/tradingbot/issues
