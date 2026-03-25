"""
Alert storage and persistence layer with full lifecycle management.
Provides idempotent storage, dedupe, and status tracking for TradingView alerts.
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
import sqlite3
import threading
import json
import logging
from pathlib import Path
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


class AlertStatus(str, Enum):
    """Alert lifecycle status."""
    ACCEPTED = "accepted"
    QUEUED = "queued"
    EXECUTED = "executed"
    FAILED = "failed"
    IGNORED = "ignored"


@dataclass
class Alert:
    """Alert data model with full lifecycle fields."""
    
    # Core alert data
    symbol: str
    timeframe: str
    side: str
    setup_id: str
    confidence: float
    price: float
    event_time: str
    nonce: str
    
    # Metadata
    received_at: str
    payload_json: str
    validation_result: str
    
    # Lifecycle tracking
    status: str = AlertStatus.ACCEPTED
    fail_reason: Optional[str] = None
    execution_ref: Optional[str] = None
    processed_at: Optional[str] = None
    
    # Database ID
    id: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert alert to dictionary."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Alert":
        """Create alert from dictionary."""
        return cls(**data)
    
    def get_idempotency_key(self) -> str:
        """Generate idempotency key for duplicate detection."""
        return f"{self.nonce}:{self.symbol}:{self.event_time}"


class AlertStorage:
    """Alert storage with idempotency and lifecycle management."""
    
    def __init__(self, db_path: str = "alerts.db"):
        """
        Initialize alert storage.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        # For in-memory databases, keep a persistent connection so the schema
        # created in _init_database remains accessible to subsequent operations.
        # A lock guards all operations on the shared connection.
        self._lock = threading.Lock()
        if db_path == ":memory:":
            self._persistent_conn: Optional[sqlite3.Connection] = sqlite3.connect(
                ":memory:", check_same_thread=False
            )
        else:
            self._persistent_conn = None
        self._init_database()

    def _connect(self):
        """Return (connection, should_close) pair.

        For file-based databases a new connection is opened on each call (and
        the caller is responsible for closing it).  For in-memory databases the
        single persistent connection is returned and must *not* be closed.
        """
        if self._persistent_conn is not None:
            return self._persistent_conn, False
        return sqlite3.connect(self.db_path), True

    def _init_database(self):
        """Initialize database schema with migration support."""
        conn, should_close = self._connect()
        cursor = conn.cursor()
        
        # Check if old schema exists
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='alerts'
        """)
        table_exists = cursor.fetchone() is not None
        
        if table_exists:
            # Check if new columns exist
            cursor.execute("PRAGMA table_info(alerts)")
            columns = {row[1] for row in cursor.fetchall()}
            
            # Migrate if needed
            if 'status' not in columns:
                logger.info("Migrating alerts table to Phase 2 schema...")
                self._migrate_schema(conn)
        else:
            # Create new schema
            self._create_schema(conn)
        
        conn.commit()
        if should_close:
            conn.close()
        logger.info(f"Alert storage initialized: {self.db_path}")
    
    def _create_schema(self, conn: sqlite3.Connection):
        """Create Phase 2 schema from scratch."""
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                
                -- Core alert data
                received_at TEXT NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                side TEXT NOT NULL,
                setup_id TEXT,
                confidence REAL,
                price REAL,
                event_time TEXT NOT NULL,
                nonce TEXT NOT NULL,
                
                -- Payload and validation
                payload_json TEXT NOT NULL,
                validation_result TEXT NOT NULL,
                
                -- Lifecycle tracking
                status TEXT NOT NULL DEFAULT 'accepted',
                fail_reason TEXT,
                execution_ref TEXT,
                processed_at TEXT,
                
                -- Indexes for idempotency
                UNIQUE(nonce, symbol, event_time)
            )
        ''')
        
        # Create indexes for common queries
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_status 
            ON alerts(status)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_received_at 
            ON alerts(received_at DESC)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_symbol 
            ON alerts(symbol)
        ''')
        
        logger.info("Created Phase 2 alerts schema")
    
    def _migrate_schema(self, conn: sqlite3.Connection):
        """Migrate existing Phase 1 schema to Phase 2."""
        cursor = conn.cursor()
        
        # Rename old table
        cursor.execute("ALTER TABLE alerts RENAME TO alerts_old")
        
        # Create new schema
        self._create_schema(conn)
        
        # Migrate data from old schema
        cursor.execute("""
            INSERT INTO alerts (
                received_at, symbol, timeframe, side, setup_id,
                confidence, price, event_time, nonce, payload_json,
                validation_result, status
            )
            SELECT 
                timestamp,
                symbol,
                timeframe,
                side,
                setup_id,
                confidence,
                price,
                COALESCE(
                    json_extract(payload, '$.event_time'),
                    timestamp
                ),
                COALESCE(
                    json_extract(payload, '$.nonce'),
                    'migrated_' || id || '_' || timestamp
                ),
                payload,
                validation_result,
                CASE 
                    WHEN validation_result = 'SUCCESS' THEN 'accepted'
                    ELSE 'failed'
                END
            FROM alerts_old
        """)
        
        migrated_count = cursor.rowcount
        
        # Drop old table
        cursor.execute("DROP TABLE alerts_old")
        
        logger.info(f"Migrated {migrated_count} alerts to Phase 2 schema")
    
    def store_alert(self, alert: Alert) -> tuple[bool, Optional[int], Optional[str]]:
        """
        Store alert with idempotency checking.
        
        Args:
            alert: Alert to store
            
        Returns:
            Tuple of (is_new, alert_id, reason)
            - is_new: True if new alert, False if duplicate
            - alert_id: Database ID of alert (existing or new)
            - reason: None if new, "duplicate" if duplicate
        """
        with self._lock:
            conn, should_close = self._connect()
            cursor = conn.cursor()
            
            try:
                # Check for duplicate using idempotency key
                cursor.execute("""
                    SELECT id, status FROM alerts 
                    WHERE nonce = ? AND symbol = ? AND event_time = ?
                """, (alert.nonce, alert.symbol, alert.event_time))
                
                existing = cursor.fetchone()
                
                if existing:
                    alert_id, status = existing
                    logger.info(
                        f"Duplicate alert detected: id={alert_id}, "
                        f"nonce={alert.nonce}, status={status}"
                    )
                    return False, alert_id, "duplicate"
                
                # Insert new alert
                cursor.execute("""
                    INSERT INTO alerts (
                        received_at, symbol, timeframe, side, setup_id,
                        confidence, price, event_time, nonce,
                        payload_json, validation_result, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    alert.received_at,
                    alert.symbol,
                    alert.timeframe,
                    alert.side,
                    alert.setup_id,
                    alert.confidence,
                    alert.price,
                    alert.event_time,
                    alert.nonce,
                    alert.payload_json,
                    alert.validation_result,
                    alert.status
                ))
                
                alert_id = cursor.lastrowid
                conn.commit()
                
                logger.info(
                    f"Stored new alert: id={alert_id}, symbol={alert.symbol}, "
                    f"side={alert.side}, confidence={alert.confidence}"
                )
                
                return True, alert_id, None
                
            except sqlite3.IntegrityError as e:
                # Race condition - another request stored the same alert
                logger.warning(f"Concurrent duplicate detected: {e}")
                
                # Fetch the existing alert
                cursor.execute("""
                    SELECT id FROM alerts 
                    WHERE nonce = ? AND symbol = ? AND event_time = ?
                """, (alert.nonce, alert.symbol, alert.event_time))
                
                existing = cursor.fetchone()
                alert_id = existing[0] if existing else None
                
                return False, alert_id, "duplicate"
            
            finally:
                if should_close:
                    conn.close()
    
    def update_status(
        self,
        alert_id: int,
        status: AlertStatus,
        fail_reason: Optional[str] = None,
        execution_ref: Optional[str] = None
    ) -> bool:
        """
        Update alert status and related fields.
        
        Args:
            alert_id: Alert database ID
            status: New status
            fail_reason: Reason for failure (if applicable)
            execution_ref: Execution reference (if applicable)
            
        Returns:
            True if updated successfully
        """
        with self._lock:
            conn, should_close = self._connect()
            cursor = conn.cursor()
            
            try:
                processed_at = datetime.now().isoformat() if status in [
                    AlertStatus.EXECUTED, AlertStatus.FAILED
                ] else None
                
                cursor.execute("""
                    UPDATE alerts 
                    SET status = ?, fail_reason = ?, execution_ref = ?, processed_at = ?
                    WHERE id = ?
                """, (status, fail_reason, execution_ref, processed_at, alert_id))
                
                conn.commit()
                
                if cursor.rowcount > 0:
                    logger.info(
                        f"Updated alert {alert_id}: status={status}, "
                        f"reason={fail_reason}, ref={execution_ref}"
                    )
                    return True
                else:
                    logger.warning(f"Alert {alert_id} not found for update")
                    return False
            
            finally:
                if should_close:
                    conn.close()
    
    def get_alert(self, alert_id: int) -> Optional[Alert]:
        """Get alert by ID."""
        with self._lock:
            conn, should_close = self._connect()
            cursor = conn.cursor()
            
            try:
                cursor.execute("""
                    SELECT 
                        id, received_at, symbol, timeframe, side, setup_id,
                        confidence, price, event_time, nonce, payload_json,
                        validation_result, status, fail_reason, execution_ref,
                        processed_at
                    FROM alerts WHERE id = ?
                """, (alert_id,))
                
                row = cursor.fetchone()
                
                if row:
                    return Alert(
                        id=row[0],
                        received_at=row[1],
                        symbol=row[2],
                        timeframe=row[3],
                        side=row[4],
                        setup_id=row[5],
                        confidence=row[6],
                        price=row[7],
                        event_time=row[8],
                        nonce=row[9],
                        payload_json=row[10],
                        validation_result=row[11],
                        status=row[12],
                        fail_reason=row[13],
                        execution_ref=row[14],
                        processed_at=row[15]
                    )
                
                return None
            
            finally:
                if should_close:
                    conn.close()
    
    def list_alerts(
        self,
        limit: int = 50,
        status: Optional[str] = None,
        symbol: Optional[str] = None
    ) -> List[Alert]:
        """
        List alerts with optional filtering.
        
        Args:
            limit: Maximum number of alerts to return
            status: Filter by status
            symbol: Filter by symbol
            
        Returns:
            List of alerts (newest first)
        """
        with self._lock:
            conn, should_close = self._connect()
            cursor = conn.cursor()
            
            try:
                query = """
                    SELECT 
                        id, received_at, symbol, timeframe, side, setup_id,
                        confidence, price, event_time, nonce, payload_json,
                        validation_result, status, fail_reason, execution_ref,
                        processed_at
                    FROM alerts
                    WHERE 1=1
                """
                params = []
                
                if status:
                    query += " AND status = ?"
                    params.append(status)
                
                if symbol:
                    query += " AND symbol = ?"
                    params.append(symbol)
                
                query += " ORDER BY received_at DESC LIMIT ?"
                params.append(limit)
                
                cursor.execute(query, params)
                
                alerts = []
                for row in cursor.fetchall():
                    alerts.append(Alert(
                        id=row[0],
                        received_at=row[1],
                        symbol=row[2],
                        timeframe=row[3],
                        side=row[4],
                        setup_id=row[5],
                        confidence=row[6],
                        price=row[7],
                        event_time=row[8],
                        nonce=row[9],
                        payload_json=row[10],
                        validation_result=row[11],
                        status=row[12],
                        fail_reason=row[13],
                        execution_ref=row[14],
                        processed_at=row[15]
                    ))
                
                return alerts
            
            finally:
                if should_close:
                    conn.close()
    
    def get_queued_alerts(self, limit: int = 10) -> List[Alert]:
        """Get alerts that need processing (accepted or queued status)."""
        with self._lock:
            conn, should_close = self._connect()
            cursor = conn.cursor()
            
            try:
                cursor.execute("""
                    SELECT 
                        id, received_at, symbol, timeframe, side, setup_id,
                        confidence, price, event_time, nonce, payload_json,
                        validation_result, status, fail_reason, execution_ref,
                        processed_at
                    FROM alerts
                    WHERE status IN ('accepted', 'queued')
                    ORDER BY received_at ASC
                    LIMIT ?
                """, (limit,))
                
                alerts = []
                for row in cursor.fetchall():
                    alerts.append(Alert(
                        id=row[0],
                        received_at=row[1],
                        symbol=row[2],
                        timeframe=row[3],
                        side=row[4],
                        setup_id=row[5],
                        confidence=row[6],
                        price=row[7],
                        event_time=row[8],
                        nonce=row[9],
                        payload_json=row[10],
                        validation_result=row[11],
                        status=row[12],
                        fail_reason=row[13],
                        execution_ref=row[14],
                        processed_at=row[15]
                    ))
                
                return alerts
            
            finally:
                if should_close:
                    conn.close()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get alert statistics."""
        with self._lock:
            conn, should_close = self._connect()
            cursor = conn.cursor()
            
            try:
                # Count by status
                cursor.execute("""
                    SELECT status, COUNT(*) 
                    FROM alerts 
                    GROUP BY status
                """)
                status_counts = {row[0]: row[1] for row in cursor.fetchall()}
                
                # Total count
                cursor.execute("SELECT COUNT(*) FROM alerts")
                total_count = cursor.fetchone()[0]
                
                # Last processed time
                cursor.execute("""
                    SELECT MAX(processed_at) 
                    FROM alerts 
                    WHERE processed_at IS NOT NULL
                """)
                last_processed = cursor.fetchone()[0]
                
                # Recent activity (last hour)
                cursor.execute("""
                    SELECT COUNT(*) 
                    FROM alerts 
                    WHERE datetime(received_at) > datetime('now', '-1 hour')
                """)
                recent_count = cursor.fetchone()[0]
                
                return {
                    "total_alerts": total_count,
                    "by_status": status_counts,
                    "last_processed_at": last_processed,
                    "recent_count_1h": recent_count
                }
            
            finally:
                if should_close:
                    conn.close()
