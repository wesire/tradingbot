"""
Trade journal: persistent SQLite log of every completed trade with full context.
"""
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DEFAULT_DB = "trade_journal.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    pair            TEXT    NOT NULL,
    side            TEXT    NOT NULL,
    entry_price     REAL    NOT NULL,
    exit_price      REAL    NOT NULL,
    amount          REAL    NOT NULL,
    fees            REAL    NOT NULL DEFAULT 0,
    pnl             REAL    NOT NULL,
    strategy        TEXT,
    session         TEXT,
    sentiment       REAL,
    ml_confidence   REAL,
    opened_at       TEXT    NOT NULL,
    closed_at       TEXT    NOT NULL,
    trade_id        TEXT,
    notes           TEXT
);
"""


class TradeJournal:
    """
    Persistent trade journal backed by SQLite.

    Logs every trade with full context including strategy name, session,
    sentiment score at trade time, and ML model confidence.
    """

    def __init__(self, db_path: str = _DEFAULT_DB) -> None:
        """
        Initialise the journal.

        Args:
            db_path: Path to the SQLite file.  Use ``":memory:"`` for tests.
        """
        self._db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(_SCHEMA)
        self._conn.commit()
        logger.info("TradeJournal initialised (db=%s)", db_path)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def log_trade(self, trade_data: Dict[str, Any]) -> int:
        """
        Persist a completed trade record.

        Args:
            trade_data: Dict with required keys ``pair``, ``side``,
                ``entry_price``, ``exit_price``, ``amount``, ``pnl``.
                Optional: ``fees``, ``strategy``, ``session``,
                ``sentiment``, ``ml_confidence``, ``opened_at``,
                ``closed_at``, ``trade_id``, ``notes``.

        Returns:
            Inserted row ID.
        """
        now = datetime.now(timezone.utc).isoformat()
        row = {
            "pair": trade_data["pair"],
            "side": trade_data["side"],
            "entry_price": float(trade_data["entry_price"]),
            "exit_price": float(trade_data["exit_price"]),
            "amount": float(trade_data["amount"]),
            "fees": float(trade_data.get("fees", 0.0)),
            "pnl": float(trade_data["pnl"]),
            "strategy": trade_data.get("strategy"),
            "session": trade_data.get("session"),
            "sentiment": trade_data.get("sentiment"),
            "ml_confidence": trade_data.get("ml_confidence"),
            "opened_at": trade_data.get("opened_at", now),
            "closed_at": trade_data.get("closed_at", now),
            "trade_id": trade_data.get("trade_id"),
            "notes": trade_data.get("notes"),
        }
        cur = self._conn.execute(
            """INSERT INTO trades
               (pair, side, entry_price, exit_price, amount, fees, pnl,
                strategy, session, sentiment, ml_confidence,
                opened_at, closed_at, trade_id, notes)
               VALUES
               (:pair, :side, :entry_price, :exit_price, :amount, :fees, :pnl,
                :strategy, :session, :sentiment, :ml_confidence,
                :opened_at, :closed_at, :trade_id, :notes)""",
            row,
        )
        self._conn.commit()
        logger.debug("TradeJournal: logged trade id=%d pnl=%.4f", cur.lastrowid, row["pnl"])
        return cur.lastrowid

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_trades(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        pair: Optional[str] = None,
    ) -> List[Dict]:
        """
        Retrieve trades matching the given filters.

        Args:
            start_date: Include trades closed on or after this UTC datetime.
            end_date: Include trades closed on or before this UTC datetime.
            pair: Optional pair filter.

        Returns:
            List of trade dicts ordered by ``closed_at`` ascending.
        """
        conditions: List[str] = []
        params: List[Any] = []
        if start_date:
            conditions.append("closed_at >= ?")
            params.append(start_date.isoformat())
        if end_date:
            conditions.append("closed_at <= ?")
            params.append(end_date.isoformat())
        if pair:
            conditions.append("pair = ?")
            params.append(pair)
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        rows = self._conn.execute(
            f"SELECT * FROM trades {where} ORDER BY closed_at ASC", params
        ).fetchall()
        return [dict(r) for r in rows]

    def get_trade_detail(self, trade_id: int) -> Optional[Dict]:
        """
        Return the full record for a single trade.

        Args:
            trade_id: Row ID (integer primary key).

        Returns:
            Trade dict or None if not found.
        """
        row = self._conn.execute(
            "SELECT * FROM trades WHERE id = ?", (trade_id,)
        ).fetchone()
        return dict(row) if row else None

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
