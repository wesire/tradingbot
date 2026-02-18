"""
Sentiment storage - SQLite storage for sentiment records.
"""
import sqlite3
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from pathlib import Path
import logging
import json

from .aggregator import AggregatedSentiment

logger = logging.getLogger(__name__)


class SentimentStorage:
    """
    SQLite storage for sentiment records.
    """
    
    def __init__(self, db_path: str = "sentiment.db"):
        """
        Initialize storage.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._init_database()
        logger.info(f"Initialized SentimentStorage at {db_path}")
    
    def _init_database(self):
        """Initialize database schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sentiment_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset TEXT NOT NULL,
                score REAL NOT NULL,
                confidence REAL NOT NULL,
                sample_size INTEGER NOT NULL,
                trend TEXT NOT NULL,
                metadata TEXT,
                created_at TEXT NOT NULL,
                INDEX idx_asset_created (asset, created_at)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def store(self, sentiment: AggregatedSentiment, metadata: Optional[Dict[str, Any]] = None):
        """
        Store sentiment record.
        
        Args:
            sentiment: AggregatedSentiment object to store
            metadata: Optional metadata dictionary
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO sentiment_records 
            (asset, score, confidence, sample_size, trend, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            sentiment.asset,
            sentiment.score,
            sentiment.confidence,
            sentiment.sample_size,
            sentiment.trend,
            json.dumps(metadata) if metadata else None,
            sentiment.updated_at.isoformat()
        ))
        
        conn.commit()
        conn.close()
        
        logger.debug(f"Stored sentiment for {sentiment.asset}: score={sentiment.score:.3f}")
    
    def get_latest(self, asset: str) -> Optional[Dict[str, Any]]:
        """
        Get latest sentiment record for an asset.
        
        Args:
            asset: Asset symbol
            
        Returns:
            Dictionary with sentiment data or None
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT asset, score, confidence, sample_size, trend, metadata, created_at
            FROM sentiment_records
            WHERE asset = ?
            ORDER BY created_at DESC
            LIMIT 1
        ''', (asset,))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        return {
            'asset': row[0],
            'score': row[1],
            'confidence': row[2],
            'sample_size': row[3],
            'trend': row[4],
            'metadata': json.loads(row[5]) if row[5] else None,
            'created_at': row[6]
        }
    
    def get_history(
        self,
        asset: str,
        hours: int = 24,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get sentiment history for an asset.
        
        Args:
            asset: Asset symbol
            hours: Number of hours to look back
            limit: Maximum number of records to return
            
        Returns:
            List of sentiment records
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cutoff_time = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        
        cursor.execute('''
            SELECT asset, score, confidence, sample_size, trend, metadata, created_at
            FROM sentiment_records
            WHERE asset = ? AND created_at >= ?
            ORDER BY created_at DESC
            LIMIT ?
        ''', (asset, cutoff_time, limit))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [
            {
                'asset': row[0],
                'score': row[1],
                'confidence': row[2],
                'sample_size': row[3],
                'trend': row[4],
                'metadata': json.loads(row[5]) if row[5] else None,
                'created_at': row[6]
            }
            for row in rows
        ]
    
    def get_all_latest(self) -> Dict[str, Dict[str, Any]]:
        """
        Get latest sentiment for all assets.
        
        Returns:
            Dictionary mapping asset symbols to their latest sentiment
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT DISTINCT asset FROM sentiment_records
        ''')
        
        assets = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        result = {}
        for asset in assets:
            latest = self.get_latest(asset)
            if latest:
                result[asset] = latest
        
        return result
    
    def cleanup_old_records(self, days: int = 30):
        """
        Remove records older than specified days.
        
        Args:
            days: Number of days to keep
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cutoff_time = (datetime.utcnow() - timedelta(days=days)).isoformat()
        
        cursor.execute('''
            DELETE FROM sentiment_records
            WHERE created_at < ?
        ''', (cutoff_time,))
        
        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()
        
        logger.info(f"Cleaned up {deleted_count} old sentiment records")
