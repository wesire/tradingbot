# BTC/USDT Perpetual Futures Scalping Bot

A production-grade automated trading system for BTC/USDT perpetual futures with comprehensive backtesting, optimization, and risk management.

## 🎯 Overview

This trading bot implements a multi-timeframe scalping strategy with:
- **Regime filtering** using EMA crossovers and ADX
- **Dynamic entries** with pullback/bounce detection and RSI confirmation
- **Advanced risk management** with ATR-based stops, partial take-profits, and daily drawdown limits
- **TradingView integration** via secure webhook gateway
- **Automated research loop** with backtesting, hyperopt, and walk-forward validation
- **Production safety** with dry-run defaults and explicit live trading gates

## 📐 Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Trading System                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌──────────────┐      ┌──────────────┐      ┌──────────────┐  │
│  │  TradingView │──────│   Webhook    │──────│   Strategy   │  │
│  │   Alerts     │      │   Gateway    │      │    Engine    │  │
│  └──────────────┘      └──────────────┘      └──────────────┘  │
│        │                     │                       │           │
│        │                     ▼                       ▼           │
│        │              ┌─────────────┐        ┌─────────────┐   │
│        │              │    Auth     │        │   Signal    │   │
│        │              │  Validator  │        │   Filters   │   │
│        │              └─────────────┘        └─────────────┘   │
│        │                                            │           │
│        │                                            ▼           │
│        │                                     ┌─────────────┐   │
│        └─────────────────────────────────────│    Risk     │   │
│                                              │   Engine    │   │
│                                              └─────────────┘   │
│                                                     │           │
│                                                     ▼           │
│                                              ┌─────────────┐   │
│                                              │   Order     │   │
│                                              │  Manager    │   │
│                                              └─────────────┘   │
│                                                     │           │
│                                                     ▼           │
│                                              ┌─────────────┐   │
│                                              │   Broker    │   │
│                                              │  Adapter    │   │
│                                              └─────────────┘   │
│                                                     │           │
└─────────────────────────────────────────────────────┼───────────┘
                                                      │
                                                      ▼
                                               ┌─────────────┐
                                               │  Exchange   │
                                               │  (Binance)  │
                                               └─────────────┘
```

## 🚀 Quick Start

### Prerequisites

- **Docker** and **docker-compose** (recommended)
- OR **Python 3.11+** with TA-Lib installed
- Git

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/wesire/tradingbot.git
cd tradingbot
```

2. **Setup environment**
```bash
make setup
# Edit .env file with your configuration
```

3. **Build Docker images**
```bash
make build
```

4. **Download historical data**
```bash
make download-data
```

5. **Run backtests**
```bash
make backtest
```

6. **Start services (dry-run mode)**
```bash
make up
```

### Quick Test

```bash
# Run test suite
make test

# Check service health
make health

# View logs
make logs
```

## 📋 Configuration

### Environment Variables

Key settings in `.env`:

| Variable | Description | Default |
|----------|-------------|---------|
| `TRADING_MODE` | Trading mode: `dry_run` or `live` | `dry_run` |
| `LIVE_TRADING_ENABLED` | Enable live trading (requires confirmation) | `false` |
| `EXCHANGE_NAME` | Exchange name | `binance` |
| `EXCHANGE_SANDBOX` | Use testnet/sandbox | `true` |
| `TV_WEBHOOK_SECRET` | Shared secret for TradingView | - |
| `MAX_RISK_PER_TRADE` | Risk per trade (fraction) | `0.005` |
| `MAX_DAILY_DRAWDOWN` | Daily drawdown limit (fraction) | `0.025` |
| `MAX_CONSECUTIVE_LOSSES` | Cooldown trigger threshold | `3` |

### Strategy Parameters

Configure in `bot/config/default_config.py`:

- **Regime Filter**: EMA 50/200, ADX threshold
- **Entry Signals**: EMA 21, RSI 14, thresholds
- **Risk Management**: ATR multiplier, TP levels
- **Filters**: Volume multiplier, ATR minimum

## 🔧 Makefile Commands

### Development

```bash
make install          # Install dependencies locally
make test            # Run full test suite
make test-fast       # Run fast tests only
make lint            # Run code linters
make format          # Format code with black
```

### Docker Operations

```bash
make build           # Build Docker images
make up              # Start all services
make down            # Stop all services
make restart         # Restart services
make logs            # View all logs
make logs-bot        # View bot logs only
make logs-webhook    # View webhook logs only
make status          # Show service status
make health          # Check service health
```

### Data & Backtesting

```bash
make download-data   # Download historical data
make backtest        # Run backtest matrix
make optimize        # Run hyperopt + walk-forward
make select-champion # Select best strategy
make report          # Generate full report
```

### Combined Workflows

```bash
make full-backtest   # Complete backtest workflow
make full-optimize   # Complete optimization workflow
```

### Utility

```bash
make clean           # Remove artifacts
make clean-data      # Remove data files
make reset           # Full reset
make check-live      # Verify live trading config
```

## 🧪 Testing

### Run Tests

```bash
# Full test suite with coverage
make test

# Fast tests only
make test-fast

# Specific test modules
make test-webhook
make test-strategy
```

### Test Coverage

Tests cover:
- ✅ Strategy logic and signal generation
- ✅ Risk management (position sizing, stops, kill switch)
- ✅ Signal filters (volatility, volume, mean reversion)
- ✅ Webhook authentication and validation
- ✅ Order lifecycle management
- ✅ Backtest pipeline and champion selection

Coverage report: `htmlcov/index.html`

## 📊 Backtesting Workflow

### 1. Download Data

```bash
make download-data
```

Downloads BTC/USDT data for configured timeframes (1m, 3m, 5m, 15m, 30m).

### 2. Run Backtest Matrix

```bash
make backtest
```

Tests strategy across all timeframes and saves results to `artifacts/metrics.csv`.

### 3. Select Champion

```bash
make select-champion
```

Applies composite scoring formula and rejection thresholds:

**Composite Score:**
```
score = 0.30×PF + 0.20×Exp + 0.20×Sharpe + 0.15×WR - 0.15×DD
```

**Hard Rejection Filters:**
- Win rate ≥ 54%
- Profit factor ≥ 1.25
- Expectancy > 0
- Max drawdown ≤ 12%
- Minimum trades ≥ 30

### 4. Review Results

Check `artifacts/champion/recommendation.json` for:
- GO/NO-GO verdict
- Champion timeframe and parameters
- Expected risk/return metrics
- Next steps

## 📡 TradingView Integration

### 1. Pine Script Setup

1. Copy `tv_gateway/pinescript_template.pine` to TradingView
2. Update `webhook_url` and `webhook_secret`
3. Add to BTC/USDT chart (recommended: 5m or 15m)

### 2. Create Alert

1. Click "Create Alert"
2. Condition: Select indicator → "Any alert() function call"
3. Alert actions: 
   - Enable "Webhook URL"
   - URL: `https://your-domain.com/tv/webhook`
4. Message: `{{strategy.order.alert_message}}`
5. Options: "Once Per Bar Close"
6. Save alert

### 3. Verify Webhook

```bash
# Check webhook health
curl http://localhost:8000/health

# Test webhook endpoint
make test-webhook
```

Alerts are logged to:
- SQLite database: `alerts.db`
- JSON log: `artifacts/webhook_alerts.jsonl`

## 🛡️ Risk Management

### Position Sizing

- Risk per trade: 0.5% of equity (configurable)
- Position size calculated based on ATR stop distance
- Conservative 3x leverage for futures

### Stop Loss

- ATR-based: 1.5× ATR from entry
- Hard maximum: 2% of position
- Uses tighter of the two

### Take Profit

- Partial exits at 1R, 1.5R, 2R
- Breakeven stop after first TP
- Trailing for remainder

### Safety Mechanisms

- **Daily drawdown limit**: 2.5% → stop trading
- **Consecutive loss cooldown**: 3 losses → 30 min pause
- **Circuit breakers**: API failures, stale data
- **Default dry-run mode**: Explicit opt-in for live trading

## ⚠️ Live Trading

### Safety Gates

Live trading requires ALL of:
1. `LIVE_TRADING_ENABLED=true` in .env
2. `TRADING_MODE=live` in .env
3. `LIVE_CONFIRMATION_TOKEN=I_UNDERSTAND_LIVE_TRADING_RISKS`
4. Valid API credentials

### Pre-Live Checklist

- [ ] Backtest results meet thresholds (≥54% WR, ≥1.25 PF)
- [ ] Dry-run testing for ≥1 week
- [ ] Dry-run performance matches backtest
- [ ] API keys tested on sandbox/testnet
- [ ] Risk parameters reviewed and appropriate
- [ ] Emergency stop procedures documented
- [ ] Monitoring and alerts configured

### Verify Configuration

```bash
make check-live
```

## 📁 Project Structure

```
tradingbot/
├── bot/
│   ├── strategy/
│   │   ├── btc_scalp_strategy.py    # Main Freqtrade strategy
│   │   ├── signal_filters.py        # Volatility, volume filters
│   │   └── risk_engine.py           # Position sizing, stops
│   ├── execution/
│   │   ├── broker_adapter.py        # CCXT exchange wrapper
│   │   └── order_manager.py         # Order lifecycle
│   ├── config/
│   │   ├── default_config.py        # Configuration parameters
│   │   └── freqtrade_config.json    # Freqtrade config
│   └── data/                        # Historical data
├── tv_gateway/
│   ├── main.py                      # FastAPI webhook app
│   ├── auth.py                      # Authentication
│   ├── schemas.py                   # Pydantic models
│   └── pinescript_template.pine     # TradingView script
├── scripts/
│   ├── download_data.py             # Data downloader
│   ├── run_backtest_matrix.py       # Backtest runner
│   ├── run_hyperopt.py              # Hyperopt runner
│   ├── run_walkforward.py           # Walk-forward validation
│   └── select_champion.py           # Champion selector
├── tests/                           # Comprehensive test suite
├── artifacts/                       # Backtest results
├── docker-compose.yml               # Service orchestration
├── Dockerfile                       # Container definition
├── Makefile                         # Command shortcuts
├── requirements.txt                 # Python dependencies
└── README.md                        # This file
```

## 🐛 Troubleshooting

### Docker Issues

**Services won't start:**
```bash
# Check logs
make logs

# Rebuild images
make down
make build
make up
```

**Port conflicts:**
```bash
# Change TV_WEBHOOK_PORT in .env
# Default: 8000
```

### Data Issues

**Missing data:**
```bash
# Re-download
make clean-data
make download-data
```

**Data gaps detected:**
- Review validation output
- Gaps < 2× timeframe are usually acceptable
- Major gaps may require different date range

### Backtest Issues

**No strategies pass filters:**
- Review rejection thresholds in .env
- Adjust MIN_WIN_RATE, MIN_PROFIT_FACTOR, etc.
- Consider longer backtest period
- Review strategy parameters

**Low trade count:**
- Check MIN_TRADES_PER_PERIOD setting
- Verify data quality and date range
- Review entry signal thresholds (RSI, EMA)

### Webhook Issues

**Alerts not received:**
```bash
# Check webhook health
make health

# Review logs
make logs-webhook

# Verify TradingView alert configuration
```

**Authentication failures:**
- Verify TV_WEBHOOK_SECRET matches Pine Script
- Check timestamp (alerts must be < 30s old)
- Ensure unique nonce for each alert

## 🔒 Security

### Best Practices

- **Never commit** API keys or secrets to git
- Use `.env` for all sensitive data
- Rotate API keys regularly
- Use read-only keys for backtesting
- Enable IP whitelisting on exchange
- Monitor for unusual activity

### API Key Permissions

Required permissions:
- ✅ Read account data
- ✅ Read market data
- ✅ Create orders (for live trading)
- ❌ Withdraw funds (NOT required)

## 📈 Performance Expectations

### Backtest Targets

- **Win Rate**: ≥ 54%
- **Profit Factor**: ≥ 1.25
- **Max Drawdown**: ≤ 12%
- **Sharpe Ratio**: ≥ 1.0

### Real Trading Considerations

- Slippage: ~0.02-0.05% per trade
- Fees: ~0.02-0.04% per trade (maker/taker)
- Funding rates: Variable, monitor 8h rate
- Market impact: Minimal for small position sizes

## 🤝 Contributing

This is a production trading system. Exercise extreme caution when making changes.

## ⚖️ License

See LICENSE file.

## ⚠️ Disclaimer

**IMPORTANT: Trading cryptocurrencies involves substantial risk of loss.**

This software is provided for educational and research purposes. The authors and contributors:
- Make NO guarantees of profitability
- Are NOT responsible for any financial losses
- Do NOT provide financial advice
- Recommend thorough testing before any live deployment

**You are solely responsible for your trading decisions and their consequences.**

## 📞 Support

For issues and questions:
1. Check this README and troubleshooting section
2. Review test suite for examples
3. Check existing GitHub issues
4. Open a new issue with detailed information

---

**Remember**: Start with paper trading (dry-run), validate extensively, and never risk more than you can afford to lose.
