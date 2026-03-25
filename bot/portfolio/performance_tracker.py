"""
Portfolio performance tracker.

Records completed trades and computes portfolio-level metrics:
Sharpe, Sortino, Calmar ratios; daily/weekly/monthly P&L;
drawdown analysis; win rate; and CSV export for tax software.
"""
import csv
import json
import logging
import math
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DEFAULT_DB = "performance.db"


class PerformanceTracker:
    """
    Real-time portfolio performance tracker backed by SQLite.

    All times are stored and compared as UTC ISO-8601 strings.

    Attributes:
        DB_SCHEMA: SQLite DDL for the trades table.
    """

    DB_SCHEMA = """
    CREATE TABLE IF NOT EXISTS trades (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        pair        TEXT    NOT NULL,
        side        TEXT    NOT NULL,
        entry_price REAL    NOT NULL,
        exit_price  REAL    NOT NULL,
        amount      REAL    NOT NULL,
        fees        REAL    NOT NULL DEFAULT 0,
        pnl         REAL    NOT NULL,
        strategy    TEXT,
        session     TEXT,
        sentiment   REAL,
        ml_confidence REAL,
        opened_at   TEXT    NOT NULL,
        closed_at   TEXT    NOT NULL,
        notes       TEXT
    );
    CREATE TABLE IF NOT EXISTS equity_snapshots (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        equity      REAL    NOT NULL,
        recorded_at TEXT    NOT NULL
    );
    """

    def __init__(self, db_path: str = _DEFAULT_DB) -> None:
        """
        Initialise the tracker.

        Args:
            db_path: Path to the SQLite database file.  Use ``":memory:"``
                for an in-process database (useful for testing).
        """
        self._db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        for stmt in self.DB_SCHEMA.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                self._conn.execute(stmt)
        self._conn.commit()
        logger.info("PerformanceTracker initialised (db=%s)", db_path)

    # ------------------------------------------------------------------
    # Trade recording
    # ------------------------------------------------------------------

    def record_trade(self, trade_data: Dict[str, Any]) -> int:
        """
        Persist a completed trade and return its row ID.

        Args:
            trade_data: Dict with keys matching the trades schema.
                Required: ``pair``, ``side``, ``entry_price``,
                ``exit_price``, ``amount``, ``pnl``.
                Optional: ``fees``, ``strategy``, ``session``,
                ``sentiment``, ``ml_confidence``, ``opened_at``,
                ``closed_at``, ``notes``.

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
            "notes": trade_data.get("notes"),
        }
        cur = self._conn.execute(
            """INSERT INTO trades
               (pair, side, entry_price, exit_price, amount, fees, pnl,
                strategy, session, sentiment, ml_confidence,
                opened_at, closed_at, notes)
               VALUES
               (:pair, :side, :entry_price, :exit_price, :amount, :fees, :pnl,
                :strategy, :session, :sentiment, :ml_confidence,
                :opened_at, :closed_at, :notes)""",
            row,
        )
        self._conn.commit()
        logger.debug("PerformanceTracker: recorded trade id=%d pnl=%.4f", cur.lastrowid, row["pnl"])
        return cur.lastrowid

    def record_equity(self, equity: float) -> None:
        """
        Record an equity snapshot for the equity curve.

        Args:
            equity: Current portfolio equity value.
        """
        self._conn.execute(
            "INSERT INTO equity_snapshots (equity, recorded_at) VALUES (?, ?)",
            (equity, datetime.now(timezone.utc).isoformat()),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def _get_trades(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        pair: Optional[str] = None,
    ) -> List[Dict]:
        """Internal: fetch trades filtered by date range and/or pair."""
        conditions = []
        params: List[Any] = []
        if start:
            conditions.append("closed_at >= ?")
            params.append(start.isoformat())
        if end:
            conditions.append("closed_at <= ?")
            params.append(end.isoformat())
        if pair:
            conditions.append("pair = ?")
            params.append(pair)
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        rows = self._conn.execute(
            f"SELECT * FROM trades {where} ORDER BY closed_at ASC", params
        ).fetchall()
        return [dict(r) for r in rows]

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
            pair: Filter by trading pair.

        Returns:
            List of trade dicts.
        """
        return self._get_trades(start=start_date, end=end_date, pair=pair)

    # ------------------------------------------------------------------
    # Metrics computation
    # ------------------------------------------------------------------

    @staticmethod
    def _sharpe(pnls: List[float], periods_per_year: float = 252.0) -> float:
        """Annualised Sharpe ratio (risk-free rate = 0)."""
        if len(pnls) < 2:
            return 0.0
        arr = [float(p) for p in pnls]
        mean = sum(arr) / len(arr)
        variance = sum((x - mean) ** 2 for x in arr) / (len(arr) - 1)
        std = math.sqrt(variance)
        if std == 0:
            return 0.0
        return (mean / std) * math.sqrt(periods_per_year)

    @staticmethod
    def _sortino(pnls: List[float], periods_per_year: float = 252.0) -> float:
        """Annualised Sortino ratio (downside deviation)."""
        if len(pnls) < 2:
            return 0.0
        arr = [float(p) for p in pnls]
        mean = sum(arr) / len(arr)
        downside = [min(x, 0.0) for x in arr]
        dvar = sum(x ** 2 for x in downside) / max(len(downside) - 1, 1)
        dstd = math.sqrt(dvar)
        if dstd == 0:
            return 0.0
        return (mean / dstd) * math.sqrt(periods_per_year)

    @staticmethod
    def _max_drawdown(equity_curve: List[float]) -> float:
        """Return maximum drawdown as a positive fraction (0 to 1)."""
        if len(equity_curve) < 2:
            return 0.0
        peak = equity_curve[0]
        max_dd = 0.0
        for eq in equity_curve:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak if peak > 0 else 0.0
            max_dd = max(max_dd, dd)
        return max_dd

    def _compute_metrics(self, trades: List[Dict]) -> Dict[str, Any]:
        """Compute key performance metrics from a trade list."""
        if not trades:
            return {
                "total_trades": 0,
                "total_pnl": 0.0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "avg_win": 0.0,
                "avg_loss": 0.0,
                "sharpe_ratio": 0.0,
                "sortino_ratio": 0.0,
                "calmar_ratio": 0.0,
                "max_drawdown": 0.0,
                "current_drawdown": 0.0,
            }

        pnls = [t["pnl"] for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]

        total_pnl = sum(pnls)
        win_rate = len(wins) / len(pnls) if pnls else 0.0
        gross_profit = sum(wins) if wins else 0.0
        gross_loss = abs(sum(losses)) if losses else 0.0
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")
        avg_win = (sum(wins) / len(wins)) if wins else 0.0
        avg_loss = (sum(losses) / len(losses)) if losses else 0.0

        sharpe = self._sharpe(pnls)
        sortino = self._sortino(pnls)

        # Equity curve from trades
        equity = [0.0]
        for p in pnls:
            equity.append(equity[-1] + p)
        max_dd = self._max_drawdown(equity)

        # Current drawdown
        peak = max(equity)
        current_dd = (peak - equity[-1]) / peak if peak > 0 else 0.0

        # Calmar: annualised return / max drawdown
        if max_dd > 0:
            # Estimate trading days span
            try:
                t0 = datetime.fromisoformat(trades[0]["closed_at"].replace("Z", "+00:00"))
                t1 = datetime.fromisoformat(trades[-1]["closed_at"].replace("Z", "+00:00"))
                days_span = max(1, (t1 - t0).days)
            except Exception:  # pylint: disable=broad-except
                days_span = len(trades)
            annual_return = total_pnl * (365 / days_span)
            calmar = annual_return / max_dd
        else:
            calmar = 0.0

        return {
            "total_trades": len(trades),
            "total_pnl": round(total_pnl, 4),
            "win_rate": round(win_rate, 4),
            "profit_factor": round(profit_factor, 4),
            "avg_win": round(avg_win, 4),
            "avg_loss": round(avg_loss, 4),
            "sharpe_ratio": round(sharpe, 4),
            "sortino_ratio": round(sortino, 4),
            "calmar_ratio": round(calmar, 4),
            "max_drawdown": round(max_dd, 4),
            "current_drawdown": round(current_dd, 4),
        }

    def get_daily_summary(self, date: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Return performance metrics for today (or a specific date).

        Args:
            date: UTC date to summarise (defaults to today).

        Returns:
            Dict with metrics for the given day.
        """
        if date is None:
            date = datetime.now(timezone.utc)
        start = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        trades = self._get_trades(start=start, end=end)
        metrics = self._compute_metrics(trades)
        metrics["date"] = start.date().isoformat()
        return metrics

    def get_performance_report(self, period: str = "30d") -> Dict[str, Any]:
        """
        Return a comprehensive performance report for the given period.

        Args:
            period: Period string e.g. ``"7d"``, ``"30d"``, ``"90d"``,
                ``"all"``.

        Returns:
            Dict with period, metrics, equity curve, and per-pair breakdown.
        """
        now = datetime.now(timezone.utc)
        if period == "all":
            start = None
        else:
            try:
                days = int(period.rstrip("d"))
            except ValueError:
                days = 30
            start = now - timedelta(days=days)

        trades = self._get_trades(start=start)
        metrics = self._compute_metrics(trades)

        # Per-pair breakdown
        pairs = list({t["pair"] for t in trades})
        per_pair: Dict[str, Any] = {}
        for pair in pairs:
            pair_trades = [t for t in trades if t["pair"] == pair]
            per_pair[pair] = self._compute_metrics(pair_trades)

        # Equity curve snapshots
        snap_rows = self._conn.execute(
            "SELECT equity, recorded_at FROM equity_snapshots ORDER BY recorded_at ASC"
        ).fetchall()
        equity_curve = [{"equity": r["equity"], "ts": r["recorded_at"]} for r in snap_rows]

        return {
            "period": period,
            "generated_at": now.isoformat(),
            "metrics": metrics,
            "per_pair": per_pair,
            "equity_curve": equity_curve,
        }

    # ------------------------------------------------------------------
    # CSV export
    # ------------------------------------------------------------------

    def export_csv(self, filepath: str, start: Optional[datetime] = None) -> int:
        """
        Export the trade log as a generic CSV file compatible with tax software.

        Columns: id, pair, side, entry_price, exit_price, amount, fees,
        pnl, strategy, session, opened_at, closed_at.

        Args:
            filepath: Output file path.
            start: Optional start date filter.

        Returns:
            Number of rows written.
        """
        trades = self._get_trades(start=start)
        fieldnames = [
            "id", "pair", "side", "entry_price", "exit_price",
            "amount", "fees", "pnl", "strategy", "session",
            "opened_at", "closed_at",
        ]
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(trades)
        logger.info("PerformanceTracker: exported %d trades to %s", len(trades), filepath)
        return len(trades)

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
