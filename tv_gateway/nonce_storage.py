"""
Persistent nonce storage for replay protection.
Stores nonces in database to survive restarts.
"""
import sqlite3
import threading
from typing import Tuple, Optional
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class NonceStorage:
    """Database-backed nonce storage for replay attack prevention."""
    
    def __init__(self, db_path: str = "alerts.db", ttl_seconds: int = 600):
        """
        Initialize nonce storage.
        
        Args:
            db_path: Path to SQLite database
            ttl_seconds: Nonce time-to-live in seconds
        """
        self.db_path = db_path
        self.ttl_seconds = ttl_seconds
        # For in-memory databases, keep a persistent connection so the tables
        # created in _init_database remain accessible to subsequent operations.
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
        """Initialize nonce storage table."""
        conn, should_close = self._connect()
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS nonces (
                nonce TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        ''')
        
        # Index for cleanup queries
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_nonces_created_at
            ON nonces(created_at)
        ''')
        
        conn.commit()
        if should_close:
            conn.close()
        
        logger.info(f"Nonce storage initialized: {self.db_path}, TTL={self.ttl_seconds}s")
    
    def check_and_store(
        self,
        nonce: str,
        timestamp: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if nonce exists and store if new.
        
        Args:
            nonce: Unique nonce string
            timestamp: Request timestamp
            
        Returns:
            Tuple of (is_new, error_message)
            - is_new: True if nonce is new, False if replay
            - error_message: Error message if replay detected
        """
        with self._lock:
            conn, should_close = self._connect()
            cursor = conn.cursor()
            
            try:
                # Check if nonce exists
                cursor.execute(
                    "SELECT created_at FROM nonces WHERE nonce = ?",
                    (nonce,)
                )
                existing = cursor.fetchone()
                
                if existing:
                    created_at = existing[0]
                    logger.warning(f"Replay detected: nonce={nonce}, first_seen={created_at}")
                    return False, f"Nonce already used (replay attack)"
                
                # Store nonce
                created_at = datetime.now().isoformat()
                cursor.execute(
                    "INSERT INTO nonces (nonce, timestamp, created_at) VALUES (?, ?, ?)",
                    (nonce, timestamp, created_at)
                )
                
                conn.commit()
                logger.debug(f"Nonce stored: {nonce}")
                
                return True, None
                
            except sqlite3.IntegrityError:
                # Race condition - nonce was stored by another request
                logger.warning(f"Concurrent replay detected: nonce={nonce}")
                return False, "Nonce already used (replay attack)"
            
            finally:
                if should_close:
                    conn.close()
    
    def cleanup_expired(self):
        """Remove expired nonces based on TTL."""
        with self._lock:
            conn, should_close = self._connect()
            cursor = conn.cursor()
            
            try:
                # Calculate expiry time
                expiry_time = datetime.now() - timedelta(seconds=self.ttl_seconds)
                expiry_str = expiry_time.isoformat()
                
                # Delete expired nonces
                cursor.execute(
                    "DELETE FROM nonces WHERE created_at < ?",
                    (expiry_str,)
                )
                
                deleted_count = cursor.rowcount
                conn.commit()
                
                if deleted_count > 0:
                    logger.info(f"Cleaned up {deleted_count} expired nonces")
                
                return deleted_count
                
            finally:
                if should_close:
                    conn.close()
    
    def count_nonces(self) -> int:
        """Count active nonces in storage."""
        with self._lock:
            conn, should_close = self._connect()
            cursor = conn.cursor()
            
            try:
                cursor.execute("SELECT COUNT(*) FROM nonces")
                count = cursor.fetchone()[0]
                return count
            finally:
                if should_close:
                    conn.close()
    
    def clear_all(self):
        """Clear all nonces (for testing)."""
        with self._lock:
            conn, should_close = self._connect()
            cursor = conn.cursor()
            
            try:
                cursor.execute("DELETE FROM nonces")
                conn.commit()
                logger.info("All nonces cleared")
            finally:
                if should_close:
                    conn.close()
