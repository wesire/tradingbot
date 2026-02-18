"""
Tests for alert storage and persistence layer.
"""
import pytest
import tempfile
import os
from datetime import datetime

from tv_gateway.alert_storage import AlertStorage, Alert, AlertStatus


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
def sample_alert():
    """Create a sample alert for testing."""
    return Alert(
        received_at=datetime.now().isoformat(),
        symbol="BTCUSDT",
        timeframe="5m",
        side="long",
        setup_id="test_setup",
        confidence=0.85,
        price=40000.0,
        event_time=str(int(datetime.now().timestamp() * 1000)),
        nonce="test_nonce_123",
        payload_json='{"test": "data"}',
        validation_result="SUCCESS",
        status=AlertStatus.ACCEPTED
    )


def test_storage_initialization(temp_db):
    """Test storage initialization creates database schema."""
    storage = AlertStorage(db_path=temp_db)
    
    # Check that database file was created
    assert os.path.exists(temp_db)
    
    # Check that we can get stats (which means schema exists)
    stats = storage.get_stats()
    assert stats['total_alerts'] == 0


def test_store_alert(storage, sample_alert):
    """Test storing a new alert."""
    is_new, alert_id, reason = storage.store_alert(sample_alert)
    
    assert is_new is True
    assert alert_id is not None
    assert reason is None
    
    # Verify we can retrieve it
    retrieved = storage.get_alert(alert_id)
    assert retrieved is not None
    assert retrieved.symbol == "BTCUSDT"
    assert retrieved.confidence == 0.85


def test_duplicate_alert_detection(storage, sample_alert):
    """Test duplicate alert detection via idempotency key."""
    # Store first time
    is_new1, alert_id1, reason1 = storage.store_alert(sample_alert)
    assert is_new1 is True
    
    # Store again with same idempotency key
    is_new2, alert_id2, reason2 = storage.store_alert(sample_alert)
    assert is_new2 is False
    assert alert_id2 == alert_id1
    assert reason2 == "duplicate"


def test_update_status(storage, sample_alert):
    """Test updating alert status."""
    # Store alert
    _, alert_id, _ = storage.store_alert(sample_alert)
    
    # Update to executed
    success = storage.update_status(
        alert_id=alert_id,
        status=AlertStatus.EXECUTED,
        execution_ref="order_123"
    )
    assert success is True
    
    # Verify update
    alert = storage.get_alert(alert_id)
    assert alert.status == AlertStatus.EXECUTED
    assert alert.execution_ref == "order_123"
    assert alert.processed_at is not None


def test_update_status_with_failure(storage, sample_alert):
    """Test updating alert status with failure reason."""
    # Store alert
    _, alert_id, _ = storage.store_alert(sample_alert)
    
    # Update to failed
    success = storage.update_status(
        alert_id=alert_id,
        status=AlertStatus.FAILED,
        fail_reason="Confidence too low"
    )
    assert success is True
    
    # Verify update
    alert = storage.get_alert(alert_id)
    assert alert.status == AlertStatus.FAILED
    assert alert.fail_reason == "Confidence too low"
    assert alert.processed_at is not None


def test_list_alerts(storage):
    """Test listing alerts with filters."""
    # Create and store multiple alerts
    for i in range(5):
        alert = Alert(
            received_at=datetime.now().isoformat(),
            symbol=f"BTC{i}",
            timeframe="5m",
            side="long",
            setup_id=f"setup_{i}",
            confidence=0.8,
            price=40000.0 + i,
            event_time=str(int(datetime.now().timestamp() * 1000) + i),
            nonce=f"nonce_{i}",
            payload_json='{}',
            validation_result="SUCCESS",
            status=AlertStatus.ACCEPTED if i < 3 else AlertStatus.EXECUTED
        )
        storage.store_alert(alert)
    
    # List all alerts
    all_alerts = storage.list_alerts(limit=10)
    assert len(all_alerts) == 5
    
    # List with status filter
    accepted = storage.list_alerts(status=AlertStatus.ACCEPTED)
    assert len(accepted) == 3
    
    executed = storage.list_alerts(status=AlertStatus.EXECUTED)
    assert len(executed) == 2


def test_get_queued_alerts(storage):
    """Test retrieving queued alerts for processing."""
    # Create alerts with different statuses
    statuses = [
        AlertStatus.ACCEPTED,
        AlertStatus.QUEUED,
        AlertStatus.EXECUTED,
        AlertStatus.FAILED
    ]
    
    for i, status in enumerate(statuses):
        alert = Alert(
            received_at=datetime.now().isoformat(),
            symbol=f"BTC{i}",
            timeframe="5m",
            side="long",
            setup_id=f"setup_{i}",
            confidence=0.8,
            price=40000.0,
            event_time=str(int(datetime.now().timestamp() * 1000) + i),
            nonce=f"nonce_{i}",
            payload_json='{}',
            validation_result="SUCCESS",
            status=status
        )
        storage.store_alert(alert)
    
    # Get queued alerts (should include accepted and queued)
    queued = storage.get_queued_alerts()
    assert len(queued) == 2
    
    # Verify they are the right ones
    statuses_found = {alert.status for alert in queued}
    assert AlertStatus.ACCEPTED in statuses_found
    assert AlertStatus.QUEUED in statuses_found


def test_get_stats(storage):
    """Test statistics retrieval."""
    # Create alerts with different statuses
    for i in range(10):
        status = [
            AlertStatus.ACCEPTED,
            AlertStatus.EXECUTED,
            AlertStatus.FAILED
        ][i % 3]
        
        alert = Alert(
            received_at=datetime.now().isoformat(),
            symbol="BTCUSDT",
            timeframe="5m",
            side="long",
            setup_id=f"setup_{i}",
            confidence=0.8,
            price=40000.0,
            event_time=str(int(datetime.now().timestamp() * 1000) + i),
            nonce=f"nonce_{i}",
            payload_json='{}',
            validation_result="SUCCESS",
            status=status
        )
        storage.store_alert(alert)
    
    # Get stats
    stats = storage.get_stats()
    
    assert stats['total_alerts'] == 10
    assert 'by_status' in stats
    assert stats['by_status'][AlertStatus.ACCEPTED] > 0
    assert stats['by_status'][AlertStatus.EXECUTED] > 0
    assert stats['by_status'][AlertStatus.FAILED] > 0


def test_idempotency_key_generation(sample_alert):
    """Test idempotency key generation."""
    key = sample_alert.get_idempotency_key()
    
    expected = f"{sample_alert.nonce}:{sample_alert.symbol}:{sample_alert.event_time}"
    assert key == expected


def test_alert_to_dict(sample_alert):
    """Test alert serialization to dictionary."""
    alert_dict = sample_alert.to_dict()
    
    assert alert_dict['symbol'] == "BTCUSDT"
    assert alert_dict['confidence'] == 0.85
    assert alert_dict['status'] == AlertStatus.ACCEPTED


def test_migration_from_phase1_schema(temp_db):
    """Test migration from Phase 1 schema to Phase 2."""
    import sqlite3
    
    # Create Phase 1 schema manually
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            source_ip TEXT,
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            side TEXT NOT NULL,
            confidence REAL,
            price REAL,
            setup_id TEXT,
            validation_result TEXT NOT NULL,
            action_taken TEXT,
            payload TEXT NOT NULL
        )
    ''')
    
    # Insert some Phase 1 data
    cursor.execute('''
        INSERT INTO alerts (
            timestamp, source_ip, symbol, timeframe, side,
            confidence, price, setup_id, validation_result,
            action_taken, payload
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        datetime.now().isoformat(),
        '192.168.1.1',
        'BTCUSDT',
        '5m',
        'long',
        0.8,
        40000.0,
        'test_setup',
        'SUCCESS',
        'logged',
        '{"event_time": "1234567890", "nonce": "old_nonce"}'
    ))
    
    conn.commit()
    conn.close()
    
    # Initialize storage (should trigger migration)
    storage = AlertStorage(db_path=temp_db)
    
    # Verify migration worked
    stats = storage.get_stats()
    assert stats['total_alerts'] == 1
    
    # Verify migrated alert has new fields
    alerts = storage.list_alerts(limit=1)
    assert len(alerts) == 1
    assert alerts[0].status in [AlertStatus.ACCEPTED, AlertStatus.FAILED]
    assert alerts[0].event_time is not None
    assert alerts[0].nonce is not None
