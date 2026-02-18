"""
Persistent nonce storage for replay protection.
Stores nonces in database to survive restarts.
"""
import sqlite3
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
        self._init_database()
    
    def _init_database(self):
        """Initialize nonce storage table."""
        conn = sqlite3.connect(self.db_path)
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
        conn = sqlite3.connect(self.db_path)
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
            conn.close()
    
    def cleanup_expired(self):
        """Remove expired nonces based on TTL."""
        conn = sqlite3.connect(self.db_path)
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
            conn.close()
    
    def count_nonces(self) -> int:
        """Count active nonces in storage."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT COUNT(*) FROM nonces")
            count = cursor.fetchone()[0]
            return count
        finally:
            conn.close()
    
    def clear_all(self):
        """Clear all nonces (for testing)."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute("DELETE FROM nonces")
            conn.commit()
            logger.info("All nonces cleared")
        finally:
            conn.close()
