"""
Tests for execution worker.
"""
import pytest
import asyncio
import tempfile
import os
from datetime import datetime, timedelta

from tv_gateway.alert_storage import AlertStorage, Alert, AlertStatus
from tv_gateway.execution_worker import ExecutionWorker
from tv_gateway.bot_client import MockBotClient, Signal, ExecutionStatus


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    yield path
    os.unlink(path)


@pytest.fixture
def storage(temp_db):
    """Create alert storage with temp database."""
    return AlertStorage(db_path=temp_db)


@pytest.fixture
def mock_bot_success():
    """Create successful mock bot client."""
    return MockBotClient(success=True)


@pytest.fixture
def mock_bot_failure():
    """Create failing mock bot client."""
    return MockBotClient(success=False, fail_reason="Test failure")


def create_test_alert(
    storage,
    symbol="BTCUSDT",
    confidence=0.95,
    timeframe="5m",
    status=AlertStatus.ACCEPTED,
    age_seconds=0
):
    """Helper to create and store a test alert."""
    received_time = datetime.now() - timedelta(seconds=age_seconds)
    
    alert = Alert(
        received_at=received_time.isoformat(),
        symbol=symbol,
        timeframe=timeframe,
        side="long",
        setup_id="test_setup",
        confidence=confidence,
        price=40000.0,
        event_time=str(int(datetime.now().timestamp() * 1000)),
        nonce=f"nonce_{datetime.now().timestamp()}",
        payload_json='{}',
        validation_result="SUCCESS",
        status=status
    )
    
    _, alert_id, _ = storage.store_alert(alert)
    return alert_id


def test_worker_initialization(storage, mock_bot_success):
    """Test worker initialization."""
    worker = ExecutionWorker(
        storage=storage,
        bot_client=mock_bot_success,
        max_alert_age=600,
        min_confidence=0.9
    )
    
    assert worker.max_alert_age == 600
    assert worker.min_confidence == 0.9


def test_check_freshness_valid(storage, mock_bot_success):
    """Test freshness check with valid alert."""
    worker = ExecutionWorker(
        storage=storage,
        bot_client=mock_bot_success,
        max_alert_age=600
    )
    
    # Create fresh alert
    alert_id = create_test_alert(storage, age_seconds=10)
    alert = storage.get_alert(alert_id)
    
    is_fresh, reason = worker._check_freshness(alert)
    
    assert is_fresh is True
    assert reason is None


def test_check_freshness_stale(storage, mock_bot_success):
    """Test freshness check with stale alert."""
    worker = ExecutionWorker(
        storage=storage,
        bot_client=mock_bot_success,
        max_alert_age=60  # 1 minute max age
    )
    
    # Create stale alert (2 minutes old)
    alert_id = create_test_alert(storage, age_seconds=120)
    alert = storage.get_alert(alert_id)
    
    is_fresh, reason = worker._check_freshness(alert)
    
    assert is_fresh is False
    assert "too old" in reason.lower()


def test_check_confidence_valid(storage, mock_bot_success):
    """Test confidence check with valid alert."""
    worker = ExecutionWorker(
        storage=storage,
        bot_client=mock_bot_success,
        min_confidence=0.8
    )
    
    alert_id = create_test_alert(storage, confidence=0.95)
    alert = storage.get_alert(alert_id)
    
    passes, reason = worker._check_confidence(alert)
    
    assert passes is True
    assert reason is None


def test_check_confidence_too_low(storage, mock_bot_success):
    """Test confidence check with low confidence alert."""
    worker = ExecutionWorker(
        storage=storage,
        bot_client=mock_bot_success,
        min_confidence=0.9
    )
    
    alert_id = create_test_alert(storage, confidence=0.7)
    alert = storage.get_alert(alert_id)
    
    passes, reason = worker._check_confidence(alert)
    
    assert passes is False
    assert "too low" in reason.lower()


def test_check_symbol_allowed(storage, mock_bot_success):
    """Test symbol check with allowed symbol."""
    worker = ExecutionWorker(
        storage=storage,
        bot_client=mock_bot_success,
        allowed_symbols=["BTC/USDT:USDT", "ETH/USDT:USDT"]
    )
    
    alert_id = create_test_alert(storage, symbol="BTCUSDT")
    alert = storage.get_alert(alert_id)
    
    allowed, reason = worker._check_symbol(alert)
    
    assert allowed is True
    assert reason is None


def test_check_symbol_not_allowed(storage, mock_bot_success):
    """Test symbol check with disallowed symbol."""
    worker = ExecutionWorker(
        storage=storage,
        bot_client=mock_bot_success,
        allowed_symbols=["BTC/USDT:USDT"]
    )
    
    alert_id = create_test_alert(storage, symbol="ETHUSDT")
    alert = storage.get_alert(alert_id)
    
    allowed, reason = worker._check_symbol(alert)
    
    assert allowed is False
    assert "not allowed" in reason.lower()


def test_check_timeframe_allowed(storage, mock_bot_success):
    """Test timeframe check with allowed timeframe."""
    worker = ExecutionWorker(
        storage=storage,
        bot_client=mock_bot_success,
        allowed_timeframes=["5m", "15m"]
    )
    
    alert_id = create_test_alert(storage, timeframe="5m")
    alert = storage.get_alert(alert_id)
    
    allowed, reason = worker._check_timeframe(alert)
    
    assert allowed is True
    assert reason is None


def test_check_timeframe_not_allowed(storage, mock_bot_success):
    """Test timeframe check with disallowed timeframe."""
    worker = ExecutionWorker(
        storage=storage,
        bot_client=mock_bot_success,
        allowed_timeframes=["5m"]
    )
    
    alert_id = create_test_alert(storage, timeframe="1h")
    alert = storage.get_alert(alert_id)
    
    allowed, reason = worker._check_timeframe(alert)
    
    assert allowed is False
    assert "not allowed" in reason.lower()


def test_apply_risk_gates_all_pass(storage, mock_bot_success):
    """Test risk gates when all checks pass."""
    worker = ExecutionWorker(
        storage=storage,
        bot_client=mock_bot_success,
        max_alert_age=600,
        min_confidence=0.8,
        allowed_symbols=["BTC/USDT:USDT"],
        allowed_timeframes=["5m"]
    )
    
    alert_id = create_test_alert(
        storage,
        symbol="BTCUSDT",
        confidence=0.95,
        timeframe="5m",
        age_seconds=10
    )
    alert = storage.get_alert(alert_id)
    
    passes, reason = worker._apply_risk_gates(alert)
    
    assert passes is True
    assert reason is None


def test_apply_risk_gates_fail_freshness(storage, mock_bot_success):
    """Test risk gates when freshness check fails."""
    worker = ExecutionWorker(
        storage=storage,
        bot_client=mock_bot_success,
        max_alert_age=60
    )
    
    alert_id = create_test_alert(storage, age_seconds=120)
    alert = storage.get_alert(alert_id)
    
    passes, reason = worker._apply_risk_gates(alert)
    
    assert passes is False
    assert "too old" in reason.lower()


def test_process_alert_success(storage, mock_bot_success):
    """Test processing alert successfully."""
    worker = ExecutionWorker(
        storage=storage,
        bot_client=mock_bot_success,
        max_alert_age=600,
        min_confidence=0.8,
        allowed_symbols=["BTC/USDT:USDT"],
        allowed_timeframes=["5m"],
        execution_enabled=True
    )
    
    # Create valid alert
    alert_id = create_test_alert(
        storage,
        symbol="BTCUSDT",
        confidence=0.95,
        timeframe="5m"
    )
    alert = storage.get_alert(alert_id)
    
    # Process alert
    worker._process_alert(alert)
    
    # Verify status updated to executed
    updated_alert = storage.get_alert(alert_id)
    assert updated_alert.status == AlertStatus.EXECUTED
    assert updated_alert.execution_ref is not None
    assert updated_alert.processed_at is not None


def test_process_alert_failure_low_confidence(storage, mock_bot_success):
    """Test processing alert that fails confidence check."""
    worker = ExecutionWorker(
        storage=storage,
        bot_client=mock_bot_success,
        min_confidence=0.9
    )
    
    # Create alert with low confidence
    alert_id = create_test_alert(storage, confidence=0.7)
    alert = storage.get_alert(alert_id)
    
    # Process alert
    worker._process_alert(alert)
    
    # Verify status updated to failed
    updated_alert = storage.get_alert(alert_id)
    assert updated_alert.status == AlertStatus.FAILED
    assert "too low" in updated_alert.fail_reason.lower()


def test_process_alert_execution_disabled(storage, mock_bot_success):
    """Test processing alert when execution is disabled."""
    worker = ExecutionWorker(
        storage=storage,
        bot_client=mock_bot_success,
        max_alert_age=600,
        min_confidence=0.8,
        execution_enabled=False
    )
    
    # Create valid alert
    alert_id = create_test_alert(storage, confidence=0.95)
    alert = storage.get_alert(alert_id)
    
    # Process alert
    worker._process_alert(alert)
    
    # Verify status updated to failed with reason
    updated_alert = storage.get_alert(alert_id)
    assert updated_alert.status == AlertStatus.FAILED
    assert "disabled" in updated_alert.fail_reason.lower()


def test_process_alert_bot_failure(storage, mock_bot_failure):
    """Test processing alert when bot execution fails."""
    worker = ExecutionWorker(
        storage=storage,
        bot_client=mock_bot_failure,
        max_alert_age=600,
        min_confidence=0.8,
        execution_enabled=True
    )
    
    # Create valid alert
    alert_id = create_test_alert(storage, confidence=0.95)
    alert = storage.get_alert(alert_id)
    
    # Process alert
    worker._process_alert(alert)
    
    # Verify status updated to failed
    updated_alert = storage.get_alert(alert_id)
    assert updated_alert.status == AlertStatus.FAILED
    assert updated_alert.fail_reason is not None


@pytest.mark.asyncio
async def test_worker_run_and_stop(storage, mock_bot_success):
    """Test worker run and stop."""
    worker = ExecutionWorker(
        storage=storage,
        bot_client=mock_bot_success,
        poll_interval=0.1,
        execution_enabled=True
    )
    
    # Create an accepted alert
    create_test_alert(storage, confidence=0.95)
    
    # Start worker
    worker_task = asyncio.create_task(worker.run())
    
    # Let it run for a bit
    await asyncio.sleep(0.3)
    
    # Stop worker
    worker.stop()
    
    # Wait for worker to finish
    try:
        await asyncio.wait_for(worker_task, timeout=2.0)
    except asyncio.TimeoutError:
        pytest.fail("Worker did not stop in time")
    
    # Verify alert was processed
    alerts = storage.list_alerts(limit=10)
    processed = [a for a in alerts if a.status in [AlertStatus.EXECUTED, AlertStatus.FAILED]]
    assert len(processed) > 0


def test_empty_allowed_lists(storage, mock_bot_success):
    """Test that empty allowed lists allow everything."""
    worker = ExecutionWorker(
        storage=storage,
        bot_client=mock_bot_success,
        allowed_symbols=[],  # Empty = all allowed
        allowed_timeframes=[]  # Empty = all allowed
    )
    
    # Create alert with any symbol/timeframe
    alert_id = create_test_alert(
        storage,
        symbol="ANYUSDT",
        timeframe="1h"
    )
    alert = storage.get_alert(alert_id)
    
    # Should pass checks
    symbol_ok, _ = worker._check_symbol(alert)
    timeframe_ok, _ = worker._check_timeframe(alert)
    
    assert symbol_ok is True
    assert timeframe_ok is True
