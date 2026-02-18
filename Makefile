.PHONY: help build up down restart logs clean test backtest optimize report

# Default target
.DEFAULT_GOAL := help

# Load environment variables
include .env
export

# Colors for output
BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[0;33m
RED := \033[0;31m
NC := \033[0m # No Color

help: ## Show this help message
	@echo "$(BLUE)BTC/USDT Scalping Bot - Available Commands$(NC)"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(NC) %s\n", $$1, $$2}'
	@echo ""

# Docker commands
build: ## Build Docker images
	@echo "$(BLUE)Building Docker images...$(NC)"
	docker-compose build
	@echo "$(GREEN)✓ Build complete$(NC)"

up: ## Start all services
	@echo "$(BLUE)Starting services...$(NC)"
	docker-compose up -d
	@echo "$(GREEN)✓ Services started$(NC)"
	@echo "Bot: http://localhost:8080"
	@echo "Webhook: http://localhost:${TV_WEBHOOK_PORT}"

down: ## Stop all services
	@echo "$(BLUE)Stopping services...$(NC)"
	docker-compose down
	@echo "$(GREEN)✓ Services stopped$(NC)"

restart: down up ## Restart all services

logs: ## Show logs from all services
	docker-compose logs -f

logs-bot: ## Show bot logs only
	docker-compose logs -f bot

logs-webhook: ## Show webhook logs only
	docker-compose logs -f webhook

logs-dashboard: ## Show dashboard logs only
	docker-compose logs -f dashboard

# Data and backtesting commands
download-data: ## Download historical data
	@echo "$(BLUE)Downloading historical data...$(NC)"
	python scripts/download_data.py \
		--start-date $(BACKTEST_START_DATE) \
		--end-date $(BACKTEST_END_DATE) \
		--timeframes $(shell echo $(TIMEFRAMES) | tr ',' ' ')
	@echo "$(GREEN)✓ Data download complete$(NC)"

backtest: ## Run backtest matrix across timeframes (usage: make backtest PAIR="BTC/USDT:USDT")
	@echo "$(BLUE)Running backtest matrix...$(NC)"
	@if [ -z "$(PAIR)" ]; then \
		python scripts/run_backtest_matrix.py; \
	else \
		python scripts/run_backtest_matrix.py --pair "$(PAIR)"; \
	fi
	@echo "$(GREEN)✓ Backtest complete$(NC)"
	@echo "Results saved to artifacts/metrics.csv"

optimize: ## Run hyperopt + walk-forward validation
	@echo "$(BLUE)Running hyperparameter optimization...$(NC)"
	python scripts/run_hyperopt.py --epochs $(OPTIMIZATION_EPOCHS)
	@echo ""
	@echo "$(BLUE)Running walk-forward validation...$(NC)"
	python scripts/run_walkforward.py
	@echo "$(GREEN)✓ Optimization complete$(NC)"

select-champion: ## Select champion strategy from results
	@echo "$(BLUE)Selecting champion strategy...$(NC)"
	python scripts/select_champion.py
	@echo "$(GREEN)✓ Champion selection complete$(NC)"
	@echo "See artifacts/champion/recommendation.json"

report: backtest select-champion ## Generate complete backtest report
	@echo "$(BLUE)Generating reports and artifacts...$(NC)"
	@echo "$(GREEN)✓ Report generation complete$(NC)"
	@echo ""
	@echo "Generated files:"
	@echo "  - artifacts/metrics.csv"
	@echo "  - artifacts/champion/recommendation.json"
	@echo "  - artifacts/champion/ranked_strategies.csv"

# Testing commands
test: ## Run pytest test suite
	@echo "$(BLUE)Running tests...$(NC)"
	pytest tests/ -v --cov=bot --cov=tv_gateway --cov-report=html --cov-report=term
	@echo "$(GREEN)✓ Tests complete$(NC)"
	@echo "Coverage report: htmlcov/index.html"

test-fast: ## Run fast tests only (skip slow tests)
	@echo "$(BLUE)Running fast tests...$(NC)"
	pytest tests/ -v -m "not slow"
	@echo "$(GREEN)✓ Fast tests complete$(NC)"

test-webhook: ## Test webhook endpoint
	@echo "$(BLUE)Testing webhook endpoint...$(NC)"
	pytest tests/test_webhook.py -v
	@echo "$(GREEN)✓ Webhook tests complete$(NC)"

test-strategy: ## Test strategy logic
	@echo "$(BLUE)Testing strategy...$(NC)"
	pytest tests/test_strategy.py tests/test_signal_filters.py tests/test_risk_engine.py -v
	@echo "$(GREEN)✓ Strategy tests complete$(NC)"

# Utility commands
clean: ## Remove artifacts and temporary files
	@echo "$(BLUE)Cleaning up...$(NC)"
	rm -rf artifacts/*.csv artifacts/*.json artifacts/*.png artifacts/*.md
	rm -rf artifacts/champion/*.csv artifacts/champion/*.json
	rm -rf htmlcov/ .coverage .pytest_cache/
	rm -rf **/__pycache__/ **/*.pyc
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@echo "$(GREEN)✓ Cleanup complete$(NC)"

clean-data: ## Remove downloaded data files
	@echo "$(YELLOW)⚠ This will remove all downloaded data$(NC)"
	@read -p "Are you sure? [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		rm -rf bot/data/*.json bot/data/*.csv; \
		echo "$(GREEN)✓ Data files removed$(NC)"; \
	else \
		echo "$(YELLOW)Cancelled$(NC)"; \
	fi

reset: clean clean-data ## Full reset (clean + remove data)
	@echo "$(GREEN)✓ Full reset complete$(NC)"

# Status and monitoring commands
status: ## Show service status
	@echo "$(BLUE)Service Status:$(NC)"
	@docker-compose ps

health: ## Check health of services
	@echo "$(BLUE)Checking service health...$(NC)"
	@echo ""
	@echo "Webhook Gateway:"
	@curl -s http://localhost:${TV_WEBHOOK_PORT}/health | python -m json.tool || echo "$(RED)✗ Not responding$(NC)"
	@echo ""
	@echo "Dashboard:"
	@curl -s -o /dev/null -w "%{http_code}" http://localhost:${DASHBOARD_PORT} > /dev/null && echo "$(GREEN)✓ Responding$(NC)" || echo "$(RED)✗ Not responding$(NC)"
	@echo ""

smoke: ## Run smoke tests (check docker compose health + key endpoints)
	@echo "$(BLUE)Running smoke tests...$(NC)"
	@bash scripts/smoke_test.sh || (echo "$(RED)✗ Smoke tests failed$(NC)" && exit 1)
	@echo "$(GREEN)✓ All smoke tests passed$(NC)"

shell-bot: ## Open shell in bot container
	docker-compose exec bot /bin/bash

shell-webhook: ## Open shell in webhook container
	docker-compose exec webhook /bin/bash

# Development commands
lint: ## Run code linting
	@echo "$(BLUE)Running linters...$(NC)"
	@which black > /dev/null && black --check . || echo "$(YELLOW)black not installed$(NC)"
	@which flake8 > /dev/null && flake8 . || echo "$(YELLOW)flake8 not installed$(NC)"
	@which mypy > /dev/null && mypy bot/ tv_gateway/ || echo "$(YELLOW)mypy not installed$(NC)"
	@echo "$(GREEN)✓ Linting complete$(NC)"

format: ## Format code with black
	@echo "$(BLUE)Formatting code...$(NC)"
	black .
	@echo "$(GREEN)✓ Code formatted$(NC)"

# Installation and setup
install: ## Install dependencies locally (for development)
	@echo "$(BLUE)Installing dependencies...$(NC)"
	pip install -r requirements.txt
	pip install black flake8 mypy pytest-cov
	@echo "$(GREEN)✓ Installation complete$(NC)"

setup: ## Initial setup (copy .env.example to .env)
	@if [ ! -f .env ]; then \
		echo "$(BLUE)Creating .env file from .env.example...$(NC)"; \
		cp .env.example .env; \
		echo "$(GREEN)✓ .env file created$(NC)"; \
		echo "$(YELLOW)⚠ Please edit .env and configure your settings$(NC)"; \
	else \
		echo "$(YELLOW).env file already exists$(NC)"; \
	fi

# Full workflow commands
full-backtest: download-data backtest select-champion ## Complete backtest workflow
	@echo "$(GREEN)✓ Full backtest workflow complete$(NC)"

full-optimize: download-data optimize select-champion ## Complete optimization workflow
	@echo "$(GREEN)✓ Full optimization workflow complete$(NC)"

# Production safety checks
check-live: ## Verify live trading configuration (safety check)
	@echo "$(BLUE)Checking live trading configuration...$(NC)"
	@if [ "$(LIVE_TRADING_ENABLED)" = "true" ]; then \
		echo "$(RED)⚠ WARNING: LIVE TRADING IS ENABLED$(NC)"; \
		echo ""; \
		echo "Configuration:"; \
		echo "  TRADING_MODE: $(TRADING_MODE)"; \
		echo "  EXCHANGE: $(EXCHANGE_NAME)"; \
		echo "  SANDBOX: $(EXCHANGE_SANDBOX)"; \
		echo ""; \
		echo "$(YELLOW)Please verify this is intended.$(NC)"; \
	else \
		echo "$(GREEN)✓ Live trading is disabled (dry-run mode)$(NC)"; \
	fi
