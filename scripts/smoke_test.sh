#!/usr/bin/env bash
#
# Smoke test script - verifies that the trading bot system is functioning
# Tests: docker compose health + key API endpoints
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Load env vars if .env exists
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Default ports
TV_WEBHOOK_PORT=${TV_WEBHOOK_PORT:-8000}
DASHBOARD_PORT=${DASHBOARD_PORT:-3000}

echo -e "${BLUE}Starting smoke tests...${NC}\n"

# Test 1: Check docker-compose services are running
echo -e "${BLUE}Test 1: Checking docker-compose services...${NC}"
if ! docker-compose ps | grep -q "Up"; then
    echo -e "${RED}✗ No services are running${NC}"
    echo "  Run: docker-compose up -d"
    exit 1
fi
echo -e "${GREEN}✓ Services are running${NC}\n"

# Test 2: Check webhook health endpoint
echo -e "${BLUE}Test 2: Testing webhook /health endpoint...${NC}"
WEBHOOK_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:${TV_WEBHOOK_PORT}/health || echo "000")
if [ "$WEBHOOK_RESPONSE" != "200" ]; then
    echo -e "${RED}✗ Webhook health check failed (HTTP ${WEBHOOK_RESPONSE})${NC}"
    echo "  Expected: 200"
    echo "  Endpoint: http://localhost:${TV_WEBHOOK_PORT}/health"
    exit 1
fi
echo -e "${GREEN}✓ Webhook health endpoint OK${NC}\n"

# Test 3: Check webhook root endpoint (returns HTTP 200)
echo -e "${BLUE}Test 3: Testing webhook root endpoint...${NC}"
ROOT_HTTP=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:${TV_WEBHOOK_PORT}/ || echo "000")
if [ "$ROOT_HTTP" != "200" ]; then
    echo -e "${YELLOW}⚠ Webhook root endpoint returned unexpected HTTP status${NC}"
    echo "  Expected: 200"
    echo "  Got: '${ROOT_HTTP}'"
else
    echo -e "${GREEN}✓ Webhook root endpoint OK${NC}\n"
fi

# Test 4: Check sentiment summary endpoint
echo -e "${BLUE}Test 4: Testing /api/sentiment/summary endpoint...${NC}"
SENTIMENT_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:${TV_WEBHOOK_PORT}/api/sentiment/summary || echo "000")
if [ "$SENTIMENT_RESPONSE" != "200" ]; then
    echo -e "${RED}✗ Sentiment summary endpoint failed (HTTP ${SENTIMENT_RESPONSE})${NC}"
    echo "  Expected: 200"
    echo "  Endpoint: http://localhost:${TV_WEBHOOK_PORT}/api/sentiment/summary"
    exit 1
fi
echo -e "${GREEN}✓ Sentiment summary endpoint OK${NC}\n"

# Test 5: Check opportunities endpoint
echo -e "${BLUE}Test 5: Testing /api/opportunities endpoint...${NC}"
OPP_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:${TV_WEBHOOK_PORT}/api/opportunities?min_confidence=0.3" || echo "000")
if [ "$OPP_RESPONSE" != "200" ]; then
    echo -e "${RED}✗ Opportunities endpoint failed (HTTP ${OPP_RESPONSE})${NC}"
    echo "  Expected: 200"
    echo "  Endpoint: http://localhost:${TV_WEBHOOK_PORT}/api/opportunities"
    exit 1
fi
echo -e "${GREEN}✓ Opportunities endpoint OK${NC}\n"

# Test 6: Check AI advisor endpoint
echo -e "${BLUE}Test 6: Testing /api/advisor endpoint...${NC}"
ADVISOR_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:${TV_WEBHOOK_PORT}/api/advisor/BTC/USDT:USDT" || echo "000")
if [ "$ADVISOR_RESPONSE" != "200" ]; then
    echo -e "${RED}✗ AI advisor endpoint failed (HTTP ${ADVISOR_RESPONSE})${NC}"
    echo "  Expected: 200"
    echo "  Endpoint: http://localhost:${TV_WEBHOOK_PORT}/api/advisor/BTC/USDT:USDT"
    exit 1
fi
echo -e "${GREEN}✓ AI advisor endpoint OK${NC}\n"

# Test 7: Verify opportunities endpoint returns valid JSON with expected structure
echo -e "${BLUE}Test 7: Validating opportunities response structure...${NC}"
OPP_JSON=$(curl -s "http://localhost:${TV_WEBHOOK_PORT}/api/opportunities?min_confidence=0.3")
if ! echo "$OPP_JSON" | grep -q '"success":true'; then
    echo -e "${RED}✗ Opportunities response missing 'success' field${NC}"
    exit 1
fi
if ! echo "$OPP_JSON" | grep -q '"opportunities"'; then
    echo -e "${RED}✗ Opportunities response missing 'opportunities' field${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Opportunities response structure valid${NC}\n"

# Test 8: Verify AI advisor response contains advisory warning
echo -e "${BLUE}Test 8: Validating AI advisor response structure...${NC}"
ADVISOR_JSON=$(curl -s "http://localhost:${TV_WEBHOOK_PORT}/api/advisor/BTC/USDT:USDT")
if ! echo "$ADVISOR_JSON" | grep -q '"warning"'; then
    echo -e "${YELLOW}⚠ AI advisor response missing advisory warning${NC}"
else
    echo -e "${GREEN}✓ AI advisor response contains advisory warning${NC}\n"
fi

# Test 9: Check dashboard is accessible (if running)
echo -e "${BLUE}Test 9: Testing dashboard accessibility...${NC}"
DASHBOARD_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:${DASHBOARD_PORT} || echo "000")
if [ "$DASHBOARD_RESPONSE" != "200" ]; then
    echo -e "${YELLOW}⚠ Dashboard not accessible (HTTP ${DASHBOARD_RESPONSE})${NC}"
    echo "  This is OK if dashboard is not started"
    echo "  To start dashboard: docker-compose up -d dashboard"
else
    echo -e "${GREEN}✓ Dashboard is accessible${NC}\n"
fi

# Test 10: Verify no sensitive data in logs
echo -e "${BLUE}Test 10: Checking for leaked secrets in logs...${NC}"
LOGS=$(docker-compose logs webhook 2>&1 | tail -100)
if echo "$LOGS" | grep -iE "(api_key|api_secret|webhook_secret|password|token)" | grep -v "REDACTED" | grep -v "***" | grep -q "="; then
    echo -e "${RED}✗ Potential secret leak detected in logs${NC}"
    echo "  Review docker logs for exposed secrets"
    exit 1
fi
echo -e "${GREEN}✓ No secrets leaked in recent logs${NC}\n"

# Summary
echo -e "${GREEN}═══════════════════════════════════════════${NC}"
echo -e "${GREEN}✓ All smoke tests passed!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════${NC}"
echo ""
echo "Tested endpoints:"
echo "  • Webhook health"
echo "  • Sentiment summary"
echo "  • Opportunities scorer"
echo "  • AI advisor (advisory only)"
echo "  • Dashboard (if running)"
echo "  • Log security"
echo ""
echo -e "${BLUE}System is operational${NC}"

exit 0
