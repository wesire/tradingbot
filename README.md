# Multi-Pair AI-Assisted Trading Platform

A production-grade automated trading system with multi-pair support, AI advisory capabilities, sentiment analysis, and comprehensive risk management. Built for BTC, ETH, and SOL perpetual futures trading.

## 🎯 Overview

This trading platform combines advanced technical analysis with AI-powered insights to identify and execute trading opportunities across multiple cryptocurrency pairs:

### Core Features

- **Multi-Pair Support**: Trade BTC/USDT, ETH/USDT, and SOL/USDT simultaneously with independent configurations
- **AI Advisory Layer**: GPT-powered market analysis and trade recommendations (⚠️ **ADVISORY ONLY** - not for automated execution)
- **Sentiment Analysis**: Real-time sentiment aggregation from multiple data sources
- **React Dashboard**: Modern web interface for monitoring, control, and AI insights
- **Regime Filtering**: EMA crossovers and ADX-based market state detection
- **Dynamic Entry System**: Pullback/bounce detection with RSI confirmation
- **Advanced Risk Management**: ATR-based stops, partial take-profits, daily drawdown limits
- **TradingView Integration**: Secure webhook gateway for external signal processing
- **Comprehensive Backtesting**: Matrix testing, hyperopt, and walk-forward validation
- **Production Safety**: Dry-run defaults, circuit breakers, and explicit live trading gates

## 📐 Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Multi-Pair AI Trading Platform                        │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│  ┌─────────────────┐                                                     │
│  │  React Dashboard│◄──────────────────────────┐                        │
│  │  (Port 3000)    │                            │                        │
│  │  • Dashboard    │                            │                        │
│  │  • Controls     │                            │                        │
│  │  • AI Overview  │                            │                        │
│  │  • Opportunities│                            │                        │
│  └─────────────────┘                            │                        │
│          │                                      │                        │
│          │ HTTP/REST                            │                        │
│          ▼                                      │                        │
│  ┌─────────────────────────────────────────────┴─────┐                  │
│  │      Webhook Gateway (FastAPI - Port 8000)        │                  │
│  │  • /tv/webhook        - TradingView alerts        │                  │
│  │  • /api/sentiment/*   - Sentiment data            │                  │
│  │  • /api/advisor/*     - AI recommendations        │                  │
│  │  • /api/opportunities - Scored opportunities      │                  │
│  └───────────────────────┬───────────────────────────┘                  │
│                          │                                               │
│          ┌───────────────┼───────────────────────┐                      │
│          │               │                       │                      │
│          ▼               ▼                       ▼                      │
│  ┌──────────────┐ ┌─────────────┐     ┌────────────────┐              │
│  │  Sentiment   │ │ AI Advisor  │     │ Opportunities  │              │
│  │  Aggregator  │ │ (GPT-4)     │     │    Scorer      │              │
│  │              │ │             │     │                │              │
│  │ • CoinGecko  │ │ ⚠️ ADVISORY  │     │ • Multi-pair   │              │
│  │ • News API   │ │    ONLY     │     │ • Risk-scored  │              │
│  │ • Twitter    │ │ • Analysis  │     │ • Filtered     │              │
│  └──────────────┘ │ • Context   │     └────────────────┘              │
│                   │ • Signals   │                                       │
│                   └─────────────┘                                       │
│                          │                                               │
│                          ▼                                               │
│               ┌────────────────────┐                                    │
│               │ Strategy Registry   │                                    │
│               │  (Multi-Pair)       │                                    │
│               │ • BTC Scalp         │                                    │
│               │ • ETH Scalp         │                                    │
│               │ • SOL Momentum      │                                    │
│               └──────────┬──────────┘                                    │
│                          │                                               │
│                          ▼                                               │
│               ┌────────────────────┐                                    │
│               │   Risk Engine      │                                    │
│               │ • Position sizing  │                                    │
│               │ • Portfolio limits │                                    │
│               │ • Kill switch      │                                    │
│               └──────────┬──────────┘                                    │
│                          │                                               │
│                          ▼                                               │
│               ┌────────────────────┐                                    │
│               │  Order Manager     │                                    │
│               │ • Entry/Exit logic │                                    │
│               │ • Order lifecycle  │                                    │
│               └──────────┬──────────┘                                    │
│                          │                                               │
└──────────────────────────┼─────────────────────────────────────────────┘
                           │
                           ▼
                   ┌───────────────┐
                   │   Exchange    │
                   │   (Binance)   │
                   └───────────────┘
```

## 🚀 Quick Start

### Prerequisites

- **Docker** and **docker-compose** (recommended)
- OR **Python 3.11+** with TA-Lib installed
- Git
- Node.js 18+ (for dashboard development)

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

5. **Run backtests** (optional but recommended)
```bash
make backtest
```

6. **Start all services** (dry-run mode by default)
```bash
make up
```

### Access the Platform

Once services are running:

- **Dashboard**: http://localhost:3000
  - Real-time monitoring and control
  - AI-powered insights and recommendations
  - Trading opportunities browser
  
- **Webhook API**: http://localhost:8000
  - REST API for integrations
  - TradingView webhook endpoint
  - Health monitoring

### Quick Health Check

```bash
# Check all services
make health

# Run smoke tests
make smoke

# View logs
make logs
```

## 🆕 New Features (v2.0)

### Multi-Pair Configuration

Configure multiple trading pairs with independent settings in `config/pairs.yaml`:

```yaml
pairs:
  - symbol: "BTC/USDT:USDT"
    enabled: true
    timeframe: "5m"
    stake_allocation: 0.4    # 40% of capital
    leverage_cap: 10
    strategy: "btc_scalp"
    
  - symbol: "ETH/USDT:USDT"
    enabled: true
    timeframe: "5m"
    stake_allocation: 0.3    # 30% of capital
    strategy: "eth_scalp"
```

### AI Advisor API

Get AI-powered market analysis and trade recommendations:

```bash
# Get advisor insights for a specific pair
curl http://localhost:8000/api/advisor/BTC-USDT?timeframe=5m
```

**⚠️ IMPORTANT**: AI recommendations are **ADVISORY ONLY** and should not be used for automated execution. Always verify with your own analysis.

### Sentiment Analysis

Real-time sentiment aggregation from multiple sources:

```bash
# Get overall sentiment summary
curl http://localhost:8000/api/sentiment/summary

# Get sentiment for specific asset
curl http://localhost:8000/api/sentiment/BTC?hours=24
```

### Opportunities Scorer

Browse and filter potential trading setups:

```bash
# Get all opportunities
curl http://localhost:8000/api/opportunities

# Filter by pair and minimum score
curl http://localhost:8000/api/opportunities?pair=BTC-USDT&min_score=70
```

### React Dashboard

Modern web interface with four main pages:

1. **Dashboard**: Real-time monitoring of positions, P&L, and system status
2. **Controls**: Operator controls for trading modes and emergency stops
3. **AI Overview**: AI-powered market analysis and recommendations
4. **Opportunities**: Browse and filter potential trading setups

### Smoke Tests

Automated health checks for all services:

```bash
make smoke
```

Tests verify:
- Docker services are running
- API endpoints are responsive
- Database connectivity
- Configuration validity

## 📋 Multi-Pair Configuration Guide

### Enabling/Disabling Pairs

Edit `config/pairs.yaml`:

```yaml
pairs:
  - symbol: "SOL/USDT:USDT"
    enabled: true   # Change to false to disable
```

### Per-Pair Configuration

Each pair supports:

- `timeframe`: Trading timeframe (1m, 3m, 5m, 15m, etc.)
- `leverage_cap`: Maximum leverage (default: 10)
- `stake_allocation`: Percentage of capital (0.0-1.0)
- `stoploss_profile`: Risk profile (standard, aggressive, conservative)
- `strategy`: Strategy name from registry
- `allowed_session_hours`: Optional trading hour restrictions

### Strategy Registry

Strategies are defined in `config/strategies/`:

- `btc_scalp.yaml`: High-frequency BTC scalping
- `eth_scalp.yaml`: ETH-optimized scalping
- `sol_momentum.yaml`: SOL momentum trading

### Configuration Validation

Validate configuration before starting:

```bash
# Check pair configuration
python scripts/validate_config.py

# Start with validation enabled (default)
make up
```

The system validates:
- Total stake allocation ≤ 100%
- Strategy files exist
- Timeframes are valid
- Risk profiles are defined

## 📡 API Documentation

### Sentiment Endpoints

#### GET /api/sentiment/summary

Get aggregated sentiment summary for all tracked assets.

**Response:**
```json
{
  "BTC": {
    "score": 72.5,
    "label": "bullish",
    "sources": ["coingecko", "news", "twitter"],
    "last_updated": "2024-02-18T10:30:00Z"
  },
  "ETH": { ... }
}
```

#### GET /api/sentiment/{asset}

Get detailed sentiment data for a specific asset.

**Parameters:**
- `asset`: Asset symbol (BTC, ETH, SOL)
- `hours`: Lookback period in hours (default: 24)

**Response:**
```json
{
  "asset": "BTC",
  "score": 72.5,
  "label": "bullish",
  "history": [...],
  "breakdown": {
    "coingecko": 75,
    "news": 70,
    "twitter": 73
  }
}
```

### AI Advisor Endpoints

#### GET /api/advisor/{pair}

Get AI-powered analysis and recommendations for a trading pair.

**Parameters:**
- `pair`: Trading pair (format: BTC-USDT)
- `timeframe`: Timeframe for analysis (default: 5m)

**Response:**
```json
{
  "pair": "BTC-USDT",
  "timeframe": "5m",
  "analysis": "Market shows bullish momentum with...",
  "recommendation": "NEUTRAL",
  "confidence": 0.75,
  "key_levels": {
    "support": [42000, 41500],
    "resistance": [43000, 43500]
  },
  "disclaimer": "Advisory only - not financial advice"
}
```

**⚠️ IMPORTANT**: AI recommendations should only be used as **guidance** and must not be used for automated trading decisions.

### Opportunities Endpoints

#### GET /api/opportunities

Get scored trading opportunities across all enabled pairs.

**Parameters:**
- `pair`: Filter by pair (optional)
- `min_score`: Minimum opportunity score 0-100 (default: 50)
- `limit`: Maximum results (default: 20)

**Response:**
```json
{
  "opportunities": [
    {
      "pair": "BTC-USDT",
      "score": 85,
      "direction": "long",
      "entry_price": 42500,
      "stop_loss": 42000,
      "take_profit": [43000, 43500],
      "risk_reward": 2.5,
      "confidence": "high",
      "reason": "Bullish divergence with volume confirmation"
    }
  ],
  "total": 1,
  "generated_at": "2024-02-18T10:30:00Z"
}
```

## 🎛️ Dashboard Usage

### Dashboard Page

The main monitoring interface shows:

- **System Status**: Trading mode, connected pairs, uptime
- **Active Positions**: Real-time P&L, entry prices, current status
- **Recent Trades**: Trade history with outcomes
- **Performance Metrics**: Win rate, profit factor, drawdown
- **Risk Gauges**: Portfolio exposure, daily drawdown, leverage usage

### Controls Page

Operator controls for managing the system:

- **Trading Mode Toggle**: Switch between dry-run and live modes
- **Pair Controls**: Enable/disable individual pairs
- **Emergency Stop**: Immediately halt all trading and close positions
- **Risk Limits**: Adjust daily drawdown limits and max positions
- **System Actions**: Restart services, reload configuration

**⚠️ All critical actions require confirmation dialogs**

### AI Overview Page

AI-powered market insights:

- **Market Analysis**: GPT-4 powered analysis of current market conditions
- **Pair-Specific Guidance**: Recommendations for each enabled pair
- **Sentiment Dashboard**: Visual sentiment indicators
- **Signal Strength**: Confidence metrics for AI suggestions

**⚠️ DISCLAIMER**: AI recommendations are advisory only and not financial advice. Always verify with your own analysis.

### Opportunities Page

Browse potential trading setups:

- **Opportunity List**: Scored trading opportunities across all pairs
- **Filtering**: Filter by pair, direction, minimum score
- **Detailed View**: Entry levels, risk/reward ratios, reasoning
- **Refresh Control**: Manual or auto-refresh options

## 🔧 Make Commands

### Service Management

```bash
make up              # Start all services (dashboard, webhook, bot)
make down            # Stop all services
make restart         # Restart all services
make logs            # View all logs (follow mode)
make logs-bot        # View bot logs only
make logs-webhook    # View webhook logs only
make logs-dashboard  # View dashboard logs only
make status          # Show service status
make health          # Check service health endpoints
make smoke           # Run smoke tests
```

### Data & Backtesting

```bash
make download-data                # Download historical data for all pairs
make backtest                     # Run backtest matrix (all pairs)
make backtest PAIR="BTC/USDT:USDT"  # Backtest specific pair
make optimize                     # Run hyperopt + walk-forward validation
make select-champion              # Select best strategy configuration
make report                       # Generate complete backtest report
make full-backtest               # Complete workflow: data + backtest + select
make full-optimize               # Complete workflow: data + optimize + select
```

### Testing & Development

```bash
make test            # Run full test suite with coverage
make test-fast       # Run fast tests only (skip slow tests)
make test-webhook    # Test webhook endpoints
make test-strategy   # Test strategy logic
make lint            # Run code linters (black, flake8, mypy)
make format          # Format code with black
make install         # Install dependencies locally
```

### Utility Commands

```bash
make setup           # Initial setup (copy .env.example to .env)
make clean           # Remove artifacts and temporary files
make clean-data      # Remove downloaded data files
make reset           # Full reset (clean + remove data)
make check-live      # Verify live trading configuration
make shell-bot       # Open shell in bot container
make shell-webhook   # Open shell in webhook container
```

## 🧪 Testing

### Run Tests

```bash
# Full test suite with coverage
make test

# Fast tests only (skip slow backtest simulations)
make test-fast

# Specific test modules
make test-webhook
make test-strategy
```

### Test Coverage

Comprehensive test coverage for:
- ✅ Multi-pair strategy logic and signal generation
- ✅ Risk management (position sizing, portfolio limits, kill switch)
- ✅ Signal filters (volatility, volume, mean reversion)
- ✅ Webhook authentication and payload validation
- ✅ Order lifecycle management
- ✅ AI advisor response formatting
- ✅ Sentiment aggregation
- ✅ Opportunity scoring

Coverage report: `htmlcov/index.html`

## 📊 Backtesting Workflow

### 1. Download Data

```bash
make download-data
```

Downloads historical data for all enabled pairs and configured timeframes.

### 2. Run Backtest Matrix

```bash
# Test all pairs
make backtest

# Test specific pair
make backtest PAIR="BTC/USDT:USDT"
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
- GO/NO-GO verdict per pair
- Champion timeframe and parameters
- Expected risk/return metrics
- Next steps and recommendations

### 5. Optimization (Optional)

```bash
make optimize
```

Runs hyperparameter optimization and walk-forward validation to find optimal parameters for each strategy.

## 📡 TradingView Integration

### 1. Pine Script Setup

1. Copy `tv_gateway/pinescript_template.pine` to TradingView
2. Update `webhook_url` and `webhook_secret`
3. Add to chart for desired pair (BTC/USDT, ETH/USDT, or SOL/USDT)
4. Set appropriate timeframe (recommended: 5m or 15m)

### 2. Create Alert

1. Click "Create Alert" on the chart
2. **Condition**: Select indicator → "Any alert() function call"
3. **Alert actions**: 
   - Enable "Webhook URL"
   - URL: `https://your-domain.com/tv/webhook`
4. **Message**: `{{strategy.order.alert_message}}`
5. **Options**: "Once Per Bar Close"
6. **Expiration**: Set appropriate expiration
7. Save alert

### 3. Verify Webhook

```bash
# Check webhook health
make health

# View webhook logs
make logs-webhook

# Test webhook endpoint
make test-webhook
```

Webhook alerts are logged to:
- SQLite database: `alerts.db`
- JSON log: `artifacts/webhook_alerts.jsonl`

## 🛡️ Risk Management

### Position Sizing

- Risk per trade: 0.5% of equity (configurable per pair)
- Position size calculated based on ATR stop distance
- Conservative leverage: 3-10x depending on pair configuration
- Portfolio-level limits: Max total exposure across all pairs

### Stop Loss Management

- ATR-based stops: 1.5× ATR from entry (pair-specific)
- Hard maximum: 2% of position
- Breakeven stop after first take-profit
- Trailing stops for remainder

### Take Profit Strategy

- Partial exits at multiple levels (1R, 1.5R, 2R)
- Pair-specific TP configurations
- Automated breakeven adjustment
- Trailing remainder for extended moves

### Portfolio Risk Controls

- **Max open trades**: 3 simultaneous positions across all pairs
- **Total exposure limit**: Configurable maximum portfolio exposure
- **Correlation management**: Avoid over-concentration in correlated pairs
- **Daily drawdown limit**: 2.5% → stop all trading
- **Consecutive loss cooldown**: 3 losses → 30 min pause
- **Circuit breakers**: API failures, stale data, connectivity issues

### Safety Mechanisms

- **Default dry-run mode**: Explicit opt-in required for live trading
- **Multi-gate live trading**: Multiple safeguards before live execution
- **Emergency stop**: Immediate halt and position closure via dashboard
- **Health monitoring**: Continuous service health checks
- **Automatic failsafes**: System shuts down on critical errors

## ⚠️ Live Trading

### Safety Gates

Live trading requires **ALL** of the following:

1. `LIVE_TRADING_ENABLED=true` in .env
2. `TRADING_MODE=live` in .env
3. `LIVE_CONFIRMATION_TOKEN=I_UNDERSTAND_LIVE_TRADING_RISKS` in .env
4. Valid exchange API credentials
5. Passing pre-live checklist (see below)

### Pre-Live Checklist

Before enabling live trading:

- [ ] Backtest results meet thresholds for all enabled pairs (≥54% WR, ≥1.25 PF)
- [ ] Dry-run testing for ≥1 week with satisfactory performance
- [ ] Dry-run performance matches backtest expectations
- [ ] API keys tested on exchange testnet/sandbox
- [ ] Risk parameters reviewed and appropriate for capital
- [ ] Portfolio allocation balanced across pairs
- [ ] Emergency stop procedures documented and tested
- [ ] Monitoring and alerts configured (email, SMS, etc.)
- [ ] Position size limits appropriate for account size
- [ ] Understand all risks and potential losses

### Verify Configuration

```bash
make check-live
```

This command displays current trading configuration and warns if live trading is enabled.

### Going Live Safely

1. **Start with one pair**: Enable only BTC initially
2. **Minimum capital**: Use small position sizes for first week
3. **Monitor closely**: Watch all trades for first 24-48 hours
4. **Verify fills**: Ensure orders execute as expected
5. **Check slippage**: Compare actual fills to expected prices
6. **Scale gradually**: Add pairs and increase size slowly
7. **Review daily**: Assess performance and adjust as needed

## ⚠️ Risk Disclaimers

### AI Advisory Disclaimer

**IMPORTANT**: The AI Advisor feature provides market analysis and trade suggestions using GPT-4 language models. These recommendations are:

- **ADVISORY ONLY** - For informational and educational purposes
- **NOT FINANCIAL ADVICE** - Do not rely solely on AI recommendations
- **NOT FOR AUTOMATION** - Should not be used for automated trade execution
- **SUBJECT TO ERROR** - AI models can be wrong, hallucinate, or misinterpret data
- **NO GUARANTEE** - No guarantee of accuracy, profitability, or suitability

**Always verify AI suggestions with your own analysis and risk assessment.**

### General Trading Disclaimer

**Trading cryptocurrencies involves substantial risk of loss.**

This software is provided for educational and research purposes. The authors and contributors:

- **Make NO guarantees** of profitability or success
- **Are NOT responsible** for any financial losses incurred
- **Do NOT provide** financial, investment, or trading advice
- **Recommend thorough testing** before any live deployment
- **Advise proper risk management** and position sizing
- **Suggest starting small** and scaling gradually

**Key Risks:**
- Market volatility and rapid price changes
- Exchange failures, outages, or hacks
- Software bugs or configuration errors
- Slippage and execution delays
- Funding rate costs for perpetual futures
- Liquidation risk with leveraged positions
- Regulatory changes and restrictions

**You are solely responsible for your trading decisions and their consequences.**

### Testing Recommendation

**ALWAYS start in dry-run mode:**
1. Test with paper trading for ≥1 week
2. Verify strategy performance matches expectations
3. Ensure all features work correctly
4. Understand the system thoroughly
5. Only then consider live trading with minimal capital

**Never risk more than you can afford to lose.**

## 📁 Project Structure

```
tradingbot/
├── bot/
│   ├── strategy/
│   │   ├── btc_scalp_strategy.py    # BTC scalping strategy
│   │   ├── eth_scalp_strategy.py    # ETH scalping strategy
│   │   ├── sol_momentum_strategy.py # SOL momentum strategy
│   │   ├── signal_filters.py        # Volatility, volume filters
│   │   ├── risk_engine.py           # Position sizing, stops
│   │   └── strategy_registry.py     # Multi-pair strategy manager
│   ├── execution/
│   │   ├── broker_adapter.py        # CCXT exchange wrapper
│   │   └── order_manager.py         # Order lifecycle management
│   ├── ai/
│   │   ├── advisor.py               # GPT-4 market advisor
│   │   ├── sentiment.py             # Sentiment aggregator
│   │   └── opportunities.py         # Opportunity scorer
│   ├── config/
│   │   └── default_config.py        # Default configuration
│   └── data/                        # Historical data storage
├── config/
│   ├── pairs.yaml                   # Multi-pair configuration
│   ├── risk.yaml                    # Risk management settings
│   └── strategies/                  # Per-strategy configs
│       ├── btc_scalp.yaml
│       ├── eth_scalp.yaml
│       └── sol_momentum.yaml
├── tv_gateway/
│   ├── main.py                      # FastAPI webhook app
│   ├── auth.py                      # Authentication
│   ├── schemas.py                   # Pydantic models
│   └── pinescript_template.pine     # TradingView Pine Script
├── dashboard/
│   ├── src/
│   │   ├── pages/                   # React page components
│   │   │   ├── Dashboard.jsx
│   │   │   ├── Controls.jsx
│   │   │   ├── AIOverview.jsx
│   │   │   └── Opportunities.jsx
│   │   ├── components/              # Reusable components
│   │   └── services/                # API clients
│   ├── public/
│   └── package.json
├── scripts/
│   ├── download_data.py             # Historical data downloader
│   ├── run_backtest_matrix.py       # Multi-pair backtest runner
│   ├── run_hyperopt.py              # Hyperopt optimizer
│   ├── run_walkforward.py           # Walk-forward validation
│   ├── select_champion.py           # Champion strategy selector
│   ├── validate_config.py           # Configuration validator
│   └── smoke_test.sh                # Smoke test suite
├── tests/                           # Comprehensive test suite
│   ├── test_strategy.py
│   ├── test_risk_engine.py
│   ├── test_webhook.py
│   ├── test_ai_advisor.py
│   └── test_opportunities.py
├── docs/
│   ├── RUNBOOK.md                   # Operations guide
│   └── ROADMAP.md                   # Future enhancements
├── artifacts/                       # Backtest results and reports
├── docker-compose.yml               # Service orchestration
├── Dockerfile                       # Container definition
├── Makefile                         # Command shortcuts
├── requirements.txt                 # Python dependencies
└── README.md                        # This file
```

## 📚 Documentation

### Additional Resources

- **[RUNBOOK.md](docs/RUNBOOK.md)**: Operations guide for deployment, monitoring, and troubleshooting
- **[ROADMAP.md](docs/ROADMAP.md)**: Future enhancements and planned features
- **[dashboard/README.md](dashboard/README.md)**: Detailed dashboard documentation and development guide

### Configuration Files

- **config/pairs.yaml**: Multi-pair trading configuration
- **config/risk.yaml**: Risk management parameters
- **config/strategies/**: Per-strategy configuration files
- **.env**: Environment variables (created from .env.example)

## 🐛 Troubleshooting

### Docker Issues

**Services won't start:**
```bash
# Check logs for errors
make logs

# Rebuild images
make down
make build
make up
```

**Port conflicts:**
```bash
# Change ports in .env:
# TV_WEBHOOK_PORT (default: 8000)
# DASHBOARD_PORT (default: 3000)
```

**Container crashes:**
```bash
# Check individual service logs
make logs-bot
make logs-webhook
make logs-dashboard

# Restart specific service
docker-compose restart bot
```

### API Issues

**Webhook not receiving alerts:**
```bash
# Check webhook health
make health

# Verify TradingView alert configuration
# - Webhook URL correct
# - Secret matches TV_WEBHOOK_SECRET
# - Message template correct

# Check webhook logs
make logs-webhook
```

**AI Advisor not responding:**
```bash
# Verify OpenAI API key in .env
# Check rate limits
# Review webhook logs for errors
make logs-webhook | grep -i error
```

### Data Issues

**Missing historical data:**
```bash
# Re-download data
make clean-data
make download-data

# Check data directory
ls -lh bot/data/
```

**Data gaps detected:**
- Review validation output during download
- Gaps < 2× timeframe are usually acceptable
- Major gaps may require different date range or data source

### Backtest Issues

**No strategies pass filters:**
- Review rejection thresholds in .env
- Adjust MIN_WIN_RATE, MIN_PROFIT_FACTOR, etc.
- Consider longer backtest period
- Review and adjust strategy parameters

**Low trade count:**
- Check MIN_TRADES_PER_PERIOD setting
- Verify data quality and date range
- Review entry signal thresholds (RSI, EMA)
- Consider different timeframe

### Configuration Issues

**Invalid pair configuration:**
```bash
# Validate configuration
python scripts/validate_config.py

# Check total stake allocation
# Should not exceed 1.0 (100%)
```

**Strategy not found:**
```bash
# Verify strategy file exists
ls -l config/strategies/

# Check strategy name in pairs.yaml matches filename
```

### Dashboard Issues

**Dashboard not loading:**
```bash
# Check dashboard service
make logs-dashboard

# Verify port 3000 is not in use
netstat -ln | grep 3000

# Rebuild dashboard
docker-compose build dashboard
make restart
```

**API connection errors:**
```bash
# Verify webhook service is running
make health

# Check API endpoint in dashboard config
# Default: http://localhost:8000
```

## 🔒 Security

### Best Practices

- **Never commit** API keys or secrets to git
- Use `.env` for all sensitive data (excluded from git)
- Rotate API keys regularly (monthly recommended)
- Use **read-only keys** for backtesting and dry-run
- Enable **IP whitelisting** on exchange API settings
- Use **sub-accounts** on exchange for bot trading
- Monitor for unusual activity and unauthorized access
- Keep OpenAI API keys secure and monitor usage

### API Key Permissions

**Required exchange API permissions:**
- ✅ Read account data
- ✅ Read market data
- ✅ Create orders (for live trading only)
- ❌ Withdraw funds (NOT required - never enable)

**OpenAI API Key:**
- Store in .env as `OPENAI_API_KEY`
- Monitor usage via OpenAI dashboard
- Set spending limits
- Use separate keys for dev/prod

### Network Security

- Run webhook gateway behind reverse proxy (nginx, Caddy)
- Use HTTPS/TLS for TradingView webhooks
- Implement rate limiting on webhook endpoint
- Use strong webhook secrets (32+ character random strings)
- Consider VPN or SSH tunnel for exchange API access

## 📈 Performance Expectations

### Backtest Targets (Per Pair)

- **Win Rate**: ≥ 54%
- **Profit Factor**: ≥ 1.25
- **Max Drawdown**: ≤ 12%
- **Sharpe Ratio**: ≥ 1.0
- **Minimum Trades**: ≥ 30 per evaluation period

### Real Trading Considerations

**Trading Costs:**
- Slippage: ~0.02-0.05% per trade
- Exchange fees: ~0.02-0.04% per trade (maker/taker)
- Funding rates: Variable, monitor 8h rate (futures)
- Network fees: Minimal for CEX, higher for DEX

**Market Impact:**
- Minimal for small position sizes (< 0.1% of 24h volume)
- Consider order book depth for larger positions
- Use limit orders to minimize slippage

**Portfolio Expectations:**
- Returns vary by market conditions
- Backtest performance is historical, not predictive
- Expect lower returns in live trading vs backtest
- Account for psychological factors and discipline

## 🤝 Contributing

This is a production trading system. Exercise extreme caution when making changes.

### Development Workflow

1. Create feature branch from `main`
2. Implement changes with tests
3. Run full test suite: `make test`
4. Run linters: `make lint`
5. Test in dry-run mode extensively
6. Submit PR with detailed description

### Code Standards

- Python: PEP 8, type hints, comprehensive docstrings
- JavaScript/React: ESLint, Prettier formatting
- Tests: Minimum 80% coverage for new code
- Documentation: Update README and docs for new features

## ⚖️ License

See LICENSE file for terms and conditions.

## 📞 Support

For issues, questions, and support:

1. **Check documentation**: Review this README, RUNBOOK, and dashboard README
2. **Review test suite**: Tests provide usage examples
3. **Search existing issues**: Check GitHub issues for similar problems
4. **Create new issue**: Provide detailed information:
   - System environment (OS, Docker version, Python version)
   - Error messages and logs
   - Steps to reproduce
   - Expected vs actual behavior

### Community

- GitHub Issues: Bug reports and feature requests
- GitHub Discussions: Questions, ideas, and general discussion

---

## 🎯 Getting Started Checklist

**First Time Setup:**
- [ ] Clone repository
- [ ] Run `make setup` and configure .env
- [ ] Build images with `make build`
- [ ] Download data with `make download-data`
- [ ] Run backtests: `make backtest`
- [ ] Review results: `artifacts/champion/recommendation.json`

**Before Going Live:**
- [ ] Test in dry-run mode for ≥1 week
- [ ] Verify all safety mechanisms work
- [ ] Test emergency stop
- [ ] Set appropriate position sizes
- [ ] Configure alerts and monitoring
- [ ] Complete pre-live checklist
- [ ] Start with single pair and small size

**Daily Operations:**
- [ ] Check dashboard: http://localhost:3000
- [ ] Review open positions and P&L
- [ ] Monitor AI recommendations (advisory only)
- [ ] Check system health: `make health`
- [ ] Review logs for errors: `make logs`

---

**Remember**: 
- Start with **paper trading** (dry-run mode)
- AI recommendations are **advisory only**
- **Never risk more** than you can afford to lose
- **Test thoroughly** before going live
- **Monitor continuously** during live trading
- **Understand the risks** completely

**This is not financial advice. Trade at your own risk.**
