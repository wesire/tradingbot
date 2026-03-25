"""
Tax CSV exporter.

Exports trade records from the TradeJournal in formats compatible with
popular crypto tax software:
- Koinly
- CoinTracker
- Generic (flat CSV with all fields)
"""
import csv
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .trade_journal import TradeJournal

logger = logging.getLogger(__name__)


class TaxExporter:
    """
    Export trade logs as tax-software-compatible CSV files.

    Supports Koinly, CoinTracker, and a generic format.  All exports can be
    filtered by year.
    """

    def __init__(self, journal: TradeJournal) -> None:
        """
        Initialise with a TradeJournal instance.

        Args:
            journal: The TradeJournal to read trades from.
        """
        self._journal = journal

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _trades_for_year(self, year: int) -> List[Dict]:
        """Return all trades closed in the given calendar year (UTC)."""
        start = datetime(year, 1, 1, tzinfo=timezone.utc)
        end = datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
        return self._journal.get_trades(start_date=start, end_date=end)

    @staticmethod
    def _ensure_dir(filepath: str) -> None:
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Koinly format
    # ------------------------------------------------------------------

    def export_koinly_csv(self, filepath: str, year: int) -> int:
        """
        Export trades in Koinly-compatible CSV format.

        Koinly columns (v2 format):
        Date, Sent Amount, Sent Currency, Received Amount, Received Currency,
        Fee Amount, Fee Currency, Net Worth Amount, Net Worth Currency,
        Label, Description, TxHash

        Buy  → Received = base currency, Sent = USDT
        Sell → Sent = base currency, Received = USDT

        Args:
            filepath: Output file path.
            year: Calendar year to export.

        Returns:
            Number of rows written.
        """
        trades = self._trades_for_year(year)
        self._ensure_dir(filepath)

        fieldnames = [
            "Date",
            "Sent Amount",
            "Sent Currency",
            "Received Amount",
            "Received Currency",
            "Fee Amount",
            "Fee Currency",
            "Net Worth Amount",
            "Net Worth Currency",
            "Label",
            "Description",
            "TxHash",
        ]

        with open(filepath, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            for t in trades:
                base, quote = _split_pair(t["pair"])
                closed_at = _format_iso(t["closed_at"])
                notional = t["exit_price"] * t["amount"]

                if t["side"].lower() == "buy":
                    row = {
                        "Date": closed_at,
                        "Sent Amount": round(notional, 8),
                        "Sent Currency": quote,
                        "Received Amount": round(t["amount"], 8),
                        "Received Currency": base,
                        "Fee Amount": round(t.get("fees", 0.0), 8),
                        "Fee Currency": quote,
                        "Net Worth Amount": round(notional, 8),
                        "Net Worth Currency": "USD",
                        "Label": "trade",
                        "Description": f"Bot trade — {t.get('strategy', '')}",
                        "TxHash": t.get("trade_id", ""),
                    }
                else:
                    row = {
                        "Date": closed_at,
                        "Sent Amount": round(t["amount"], 8),
                        "Sent Currency": base,
                        "Received Amount": round(notional, 8),
                        "Received Currency": quote,
                        "Fee Amount": round(t.get("fees", 0.0), 8),
                        "Fee Currency": quote,
                        "Net Worth Amount": round(notional, 8),
                        "Net Worth Currency": "USD",
                        "Label": "trade",
                        "Description": f"Bot trade — {t.get('strategy', '')}",
                        "TxHash": t.get("trade_id", ""),
                    }
                writer.writerow(row)

        logger.info("TaxExporter: exported %d trades (Koinly) → %s", len(trades), filepath)
        return len(trades)

    # ------------------------------------------------------------------
    # CoinTracker format
    # ------------------------------------------------------------------

    def export_cointracker_csv(self, filepath: str, year: int) -> int:
        """
        Export trades in CoinTracker-compatible CSV format.

        CoinTracker columns:
        Date, Received Quantity, Received Currency, Sent Quantity,
        Sent Currency, Fee Amount, Fee Currency, Tag

        Args:
            filepath: Output file path.
            year: Calendar year to export.

        Returns:
            Number of rows written.
        """
        trades = self._trades_for_year(year)
        self._ensure_dir(filepath)

        fieldnames = [
            "Date",
            "Received Quantity",
            "Received Currency",
            "Sent Quantity",
            "Sent Currency",
            "Fee Amount",
            "Fee Currency",
            "Tag",
        ]

        with open(filepath, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            for t in trades:
                base, quote = _split_pair(t["pair"])
                closed_at = _format_iso(t["closed_at"])
                notional = t["exit_price"] * t["amount"]

                if t["side"].lower() == "buy":
                    row = {
                        "Date": closed_at,
                        "Received Quantity": round(t["amount"], 8),
                        "Received Currency": base,
                        "Sent Quantity": round(notional, 8),
                        "Sent Currency": quote,
                        "Fee Amount": round(t.get("fees", 0.0), 8),
                        "Fee Currency": quote,
                        "Tag": "",
                    }
                else:
                    row = {
                        "Date": closed_at,
                        "Received Quantity": round(notional, 8),
                        "Received Currency": quote,
                        "Sent Quantity": round(t["amount"], 8),
                        "Sent Currency": base,
                        "Fee Amount": round(t.get("fees", 0.0), 8),
                        "Fee Currency": quote,
                        "Tag": "",
                    }
                writer.writerow(row)

        logger.info(
            "TaxExporter: exported %d trades (CoinTracker) → %s", len(trades), filepath
        )
        return len(trades)

    # ------------------------------------------------------------------
    # Generic format
    # ------------------------------------------------------------------

    def export_generic_csv(self, filepath: str, year: int) -> int:
        """
        Export a generic trade log CSV with all available fields.

        Columns: date, pair, side, amount, entry_price, exit_price,
        fees, pnl, strategy, session.

        Args:
            filepath: Output file path.
            year: Calendar year to export.

        Returns:
            Number of rows written.
        """
        trades = self._trades_for_year(year)
        self._ensure_dir(filepath)

        fieldnames = [
            "date",
            "pair",
            "side",
            "amount",
            "entry_price",
            "exit_price",
            "fees",
            "pnl",
            "strategy",
            "session",
        ]

        with open(filepath, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for t in trades:
                row = dict(t)
                row["date"] = _format_iso(t["closed_at"])
                writer.writerow(row)

        logger.info("TaxExporter: exported %d trades (generic) → %s", len(trades), filepath)
        return len(trades)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _split_pair(pair: str):
    """Split a pair like ``"BTC/USDT"`` or ``"BTC/USDT:USDT"`` into (base, quote)."""
    clean = pair.split(":")[0]  # strip margin suffix
    if "/" in clean:
        parts = clean.split("/", 1)
        return parts[0], parts[1]
    return pair, "USDT"


def _format_iso(dt_str: str) -> str:
    """Return a consistently formatted ISO-8601 datetime string."""
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except (ValueError, AttributeError):
        return dt_str
