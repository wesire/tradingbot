# Trading Bot Roadmap

## Current Status: v2.0 - Multi-Pair AI-Assisted Platform

The bot has been upgraded from a single-pair dry-run system to a multi-pair, AI-assisted trading platform with GUI, sentiment analysis, and enhanced safety controls.

---

## Next 3 Milestones

### Milestone 1: Live Sentiment Integration (Q1 2026)

**Goal**: Replace mock sentiment provider with real news/social media data sources

**Deliverables**:
- [x] Integrate CryptoPanic API for crypto news sentiment
- [x] Add Twitter/X sentiment analysis (`TwitterSentimentProvider`)
- [x] Implement Reddit sentiment scraper (r/CryptoCurrency, r/Bitcoin)
- [x] Add weighted sentiment combining multiple sources
- [x] Fear & Greed Index integration (`FearGreedProvider`)
- [x] Economic Calendar filter (`EconomicCalendarFilter`)
- [ ] Add sentiment alerts (e.g., "BTC sentiment spike detected")

**Technical Tasks**:
- [x] Create `CryptoPanicSentimentProvider` class
- [x] Create `TwitterSentimentProvider` class
- [x] Create `RedditSentimentProvider` class
- [x] Add API credentials to .env
- [x] Implement rate limiting for API calls
- [x] Add caching layer to reduce API costs
- [x] Update dashboard to show sentiment sources (SentimentWidget component)

**Success Criteria**:
- All 3 sentiment sources operational
- Sentiment data updates every 15-60 minutes
- Backtests show sentiment adds value (>2% improvement in Sharpe)

---

### Milestone 2: ML Signal Enhancement (Q2 2026)

**Goal**: Add machine learning model to enhance signal quality and reduce false positives

**Deliverables**:
- [x] Feature engineering pipeline (technical indicators → ML features)
- [x] Train gradient boosting model (XGBoost/LightGBM) for signal classification
- [ ] Implement online learning for model updates
- [x] Add model explainability (SHAP values)
- [ ] Create ML model backtesting framework
- [ ] Deploy model as microservice (optional)
- [x] Add "ML confidence" to opportunities API

**Technical Tasks**:
- [x] Create `bot/ml/` module
- [x] Implement `FeatureEngineer` class
- [ ] Train initial model on 6+ months of data
- [x] Create model versioning system
- [x] Add model performance monitoring
- [x] Integrate ML predictions into `OpportunityScorer`
- [ ] Add ML explainability dashboard page

**Success Criteria**:
- ML model achieves >60% precision on signal classification
- False positive rate reduced by >30%
- Model updates automatically with new data
- Explanations available for every prediction

---

### Milestone 3: Mobile Alerts & Remote Control (Q3 2026)

**Goal**: Enable mobile notifications and remote bot control

**Deliverables**:
- [x] Telegram bot for alerts and commands
- [ ] Push notifications (iOS/Android) via Firebase (deferred to follow-up PR)
- [ ] SMS alerts for critical events (Twilio) (deferred to follow-up PR)
- [ ] Mobile-friendly dashboard (PWA) (deferred to follow-up PR)
- [ ] Remote emergency stop via mobile
- [x] Trade approval workflow (manual confirmation before live trades)

**Technical Tasks**:
- [x] Create `bot/notifications/` module
- [x] Implement `TelegramNotifier` class
- [x] Implement `NotificationManager` (multi-channel routing, throttling)
- [ ] Set up Firebase Cloud Messaging (deferred)
- [ ] Integrate Twilio SMS API (deferred)
- [ ] Convert dashboard to PWA (deferred)
- [ ] Add authentication/authorization layer
- [ ] Implement trade approval queue
- [ ] Add 2FA for critical actions

**Alert Types**:
- Trade executed (entry/exit)
- Daily P&L milestone (e.g., +5%, -2%)
- Risk engine triggered (drawdown limit, cooldown)
- Sentiment spike detected
- High-confidence opportunity detected
- System health issues

**Success Criteria**:
- Notifications delivered within 10 seconds
- Mobile dashboard fully functional
- Remote emergency stop tested and working
- 2FA implemented for sensitive actions

---

### Backtesting Improvements (completed)
- [x] Walk-forward analysis (`bot/backtesting/walk_forward.py`)
- [x] Monte Carlo simulation (`bot/backtesting/monte_carlo.py`)
- [x] Sentiment backtesting framework (`bot/sentiment/backtester.py`)

### Future Enhancements (Post-Q3 2026)

### Portfolio Optimization
- [x] Implement correlation analysis between pairs (`CorrelationManager`)
- [x] Risk parity allocation strategy (`RiskParityAllocator`)
- [x] Portfolio performance tracker with Sharpe, Sortino, Calmar ratios (`PerformanceTracker`)
- [ ] Modern portfolio theory (mean-variance optimisation) position sizing
- [ ] Dynamic allocation based on pair performance

### Advanced Order Types
- [x] Limit orders with market-order fallback (`SmartOrderRouter`)
- [x] Iceberg / scaled entries across a price range
- [x] TWAP (Time-Weighted Average Price) execution
- [x] Execution analytics (slippage, fill time, maker/taker ratio) (`ExecutionAnalytics`)
- [ ] Flash loan arbitrage detection
- [ ] Smart order routing across multiple exchanges (live)

### Multi-Exchange Support
- [x] `ExchangeManager` groundwork — register, route, aggregate balances
- [x] Binance production support; Bybit and OKX stubs ready
- [ ] Cross-exchange arbitrage detection
- [ ] Live Bybit / OKX integration

### Session-Aware Trading
- [x] `SessionManager` — Asian, London, New York, weekend sessions
- [x] Per-session position-size multipliers
- [x] Preferred strategy style per session (mean reversion / breakout / momentum)

### Sentiment Enhancements
- [x] Fear & Greed Index integration (`FearGreedProvider`) — Alternative.me API
- [x] Economic Calendar filter (`EconomicCalendarFilter`) — pause trading around high-impact events
- [ ] Sentiment spike alerts

### Compliance & Reporting
- [x] Trade journal with full context (`TradeJournal`) — SQLite backed
- [x] Koinly-compatible CSV export (`TaxExporter`)
- [x] CoinTracker-compatible CSV export
- [x] Daily / weekly / monthly performance reports (`PerformanceReportGenerator`)
- [ ] Performance attribution analysis
- [ ] Regulatory compliance checks (pattern day trading, wash sales)

### AI/ML Enhancements
- [ ] Reinforcement learning for dynamic exits
- [ ] LSTM/Transformer for price prediction
- [ ] Anomaly detection (flash crashes, pump & dumps)
- [ ] Natural language processing for news analysis
- [ ] Online learning for automatic model updates

### Infrastructure
- [ ] Kubernetes deployment for production
- [ ] Multi-region failover
- [ ] Database sharding for high-frequency data
- [ ] Real-time streaming dashboard (WebSocket)

---

## Version History

### v2.0.0 (February 2026) - Multi-Pair AI Platform
- ✅ Multi-pair support with strategy registry
- ✅ React dashboard with real-time monitoring
- ✅ AI advisor (advisory only, no autonomous trading)
- ✅ Sentiment analysis pipeline
- ✅ Opportunities scorer
- ✅ Enhanced logging with secret redaction
- ✅ Modular YAML configuration
- ✅ Config validation at startup
- ✅ Smoke test suite

### v1.0.0 (January 2026) - BTC Scalping Bot
- Single-pair BTC/USDT perpetual futures
- Regime filtering (EMA + ADX)
- RSI pullback/bounce entries
- ATR-based dynamic stops
- TradingView webhook integration
- Comprehensive backtesting framework
- Walk-forward optimization
- Docker deployment

---

## Contributing to Roadmap

Have ideas for new features? Please:
1. Check existing GitHub issues
2. Create a new issue with:
   - Clear description of the feature
   - Use case and benefits
   - Technical considerations
   - Example implementation (optional)
3. Tag with "enhancement" label

Priority is given to features that:
- Improve risk management
- Reduce false signals
- Enhance operational safety
- Add measurable value in backtests
