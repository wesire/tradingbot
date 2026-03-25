"""
Performance report generator.

Produces formatted markdown/text reports for daily, weekly, and monthly
periods.  Reports can be printed, logged, or forwarded to the Telegram
notifier.
"""
import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .trade_journal import TradeJournal

logger = logging.getLogger(__name__)


def _pct(value: float) -> str:
    """Format a decimal fraction as a percentage string."""
    return f"{value * 100:.2f}%"


def _sign(value: float) -> str:
    """Return '+' for non-negative values, empty string otherwise."""
    return "+" if value >= 0 else ""


class PerformanceReportGenerator:
    """
    Generate human-readable performance reports from trade journal data.

    Reports include P&L, win rate, Sharpe/Sortino ratios, drawdown, and
    per-pair breakdown.
    """

    def __init__(self, journal: TradeJournal) -> None:
        """
        Initialise with a TradeJournal instance.

        Args:
            journal: The TradeJournal to source trade data from.
        """
        self._journal = journal

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _sharpe(pnls: List[float]) -> float:
        if len(pnls) < 2:
            return 0.0
        mean = sum(pnls) / len(pnls)
        var = sum((x - mean) ** 2 for x in pnls) / (len(pnls) - 1)
        std = math.sqrt(var)
        return (mean / std) * math.sqrt(252) if std > 0 else 0.0

    @staticmethod
    def _max_dd(pnls: List[float]) -> float:
        equity = [0.0]
        for p in pnls:
            equity.append(equity[-1] + p)
        peak = equity[0]
        max_dd = 0.0
        for eq in equity:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak if peak > 0 else 0.0
            max_dd = max(max_dd, dd)
        return max_dd

    def _build_metrics(self, trades: List[Dict]) -> Dict[str, Any]:
        if not trades:
            return {}
        pnls = [t["pnl"] for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        total_pnl = sum(pnls)
        win_rate = len(wins) / len(pnls)
        gross_profit = sum(wins) if wins else 0.0
        gross_loss = abs(sum(losses)) if losses else 0.0
        pf = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")
        return {
            "total_trades": len(trades),
            "total_pnl": total_pnl,
            "win_rate": win_rate,
            "profit_factor": pf,
            "avg_win": sum(wins) / len(wins) if wins else 0.0,
            "avg_loss": sum(losses) / len(losses) if losses else 0.0,
            "sharpe": self._sharpe(pnls),
            "max_drawdown": self._max_dd(pnls),
        }

    @staticmethod
    def _pair_breakdown(trades: List[Dict]) -> Dict[str, Dict]:
        pairs = list({t["pair"] for t in trades})
        result = {}
        for pair in pairs:
            pt = [t for t in trades if t["pair"] == pair]
            pnls = [t["pnl"] for t in pt]
            wins = [p for p in pnls if p > 0]
            result[pair] = {
                "trades": len(pt),
                "pnl": sum(pnls),
                "win_rate": len(wins) / len(pnls) if pnls else 0.0,
            }
        return result

    @staticmethod
    def _strategy_breakdown(trades: List[Dict]) -> Dict[str, Dict]:
        strategies = list({t.get("strategy") or "unknown" for t in trades})
        result = {}
        for strat in strategies:
            st = [t for t in trades if (t.get("strategy") or "unknown") == strat]
            pnls = [t["pnl"] for t in st]
            wins = [p for p in pnls if p > 0]
            result[strat] = {
                "trades": len(st),
                "pnl": sum(pnls),
                "win_rate": len(wins) / len(pnls) if pnls else 0.0,
            }
        return result

    # ------------------------------------------------------------------
    # Report builders
    # ------------------------------------------------------------------

    def generate_daily_report(
        self, date: Optional[datetime] = None
    ) -> str:
        """
        Generate a markdown daily performance report.

        Args:
            date: UTC date to report on (defaults to today).

        Returns:
            Markdown-formatted string.
        """
        now = date or datetime.now(timezone.utc)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        trades = self._journal.get_trades(start_date=start, end_date=end)
        m = self._build_metrics(trades)
        date_str = start.strftime("%Y-%m-%d")

        if not m:
            return f"## 📊 Daily Report — {date_str}\n\n_No trades today._\n"

        lines = [
            f"## 📊 Daily Report — {date_str}",
            "",
            f"**Trades:** {m['total_trades']}  |  "
            f"**P&L:** {_sign(m['total_pnl'])}{m['total_pnl']:.4f}  |  "
            f"**Win Rate:** {_pct(m['win_rate'])}",
            f"**Profit Factor:** {m['profit_factor']:.2f}  |  "
            f"**Avg Win:** {m['avg_win']:.4f}  |  "
            f"**Avg Loss:** {m['avg_loss']:.4f}",
            "",
        ]

        pb = self._pair_breakdown(trades)
        if pb:
            lines.append("### Per-Pair")
            for pair, stats in sorted(pb.items()):
                lines.append(
                    f"- **{pair}**: {stats['trades']} trades, "
                    f"P&L {_sign(stats['pnl'])}{stats['pnl']:.4f}, "
                    f"WR {_pct(stats['win_rate'])}"
                )
            lines.append("")

        return "\n".join(lines)

    def generate_weekly_report(
        self, end_date: Optional[datetime] = None
    ) -> str:
        """
        Generate a markdown weekly performance report.

        Args:
            end_date: End of the week (defaults to now UTC).

        Returns:
            Markdown-formatted string.
        """
        now = end_date or datetime.now(timezone.utc)
        start = now - timedelta(days=7)
        trades = self._journal.get_trades(start_date=start, end_date=now)
        m = self._build_metrics(trades)
        period = f"{start.strftime('%Y-%m-%d')} to {now.strftime('%Y-%m-%d')}"

        if not m:
            return f"## 📈 Weekly Report — {period}\n\n_No trades this week._\n"

        lines = [
            f"## 📈 Weekly Report — {period}",
            "",
            f"**Trades:** {m['total_trades']}  |  "
            f"**P&L:** {_sign(m['total_pnl'])}{m['total_pnl']:.4f}  |  "
            f"**Win Rate:** {_pct(m['win_rate'])}",
            f"**Sharpe:** {m['sharpe']:.2f}  |  "
            f"**Max DD:** {_pct(m['max_drawdown'])}  |  "
            f"**PF:** {m['profit_factor']:.2f}",
            "",
        ]

        pb = self._pair_breakdown(trades)
        if pb:
            lines.append("### Per-Pair")
            for pair, stats in sorted(pb.items()):
                lines.append(
                    f"- **{pair}**: {stats['trades']} trades, "
                    f"P&L {_sign(stats['pnl'])}{stats['pnl']:.4f}, "
                    f"WR {_pct(stats['win_rate'])}"
                )
            lines.append("")

        sb = self._strategy_breakdown(trades)
        if sb:
            lines.append("### Per-Strategy")
            for strat, stats in sorted(sb.items()):
                lines.append(
                    f"- **{strat}**: {stats['trades']} trades, "
                    f"P&L {_sign(stats['pnl'])}{stats['pnl']:.4f}, "
                    f"WR {_pct(stats['win_rate'])}"
                )
            lines.append("")

        return "\n".join(lines)

    def generate_monthly_report(
        self, year: Optional[int] = None, month: Optional[int] = None
    ) -> str:
        """
        Generate a markdown monthly performance report.

        Args:
            year: Year (defaults to current year).
            month: Month 1-12 (defaults to current month).

        Returns:
            Markdown-formatted string.
        """
        now = datetime.now(timezone.utc)
        y = year or now.year
        mo = month or now.month
        start = datetime(y, mo, 1, tzinfo=timezone.utc)
        # First day of next month
        if mo == 12:
            end = datetime(y + 1, 1, 1, tzinfo=timezone.utc)
        else:
            end = datetime(y, mo + 1, 1, tzinfo=timezone.utc)

        trades = self._journal.get_trades(start_date=start, end_date=end)
        m = self._build_metrics(trades)
        period = start.strftime("%B %Y")

        if not m:
            return f"## 📅 Monthly Report — {period}\n\n_No trades this month._\n"

        lines = [
            f"## 📅 Monthly Report — {period}",
            "",
            f"**Trades:** {m['total_trades']}  |  "
            f"**P&L:** {_sign(m['total_pnl'])}{m['total_pnl']:.4f}  |  "
            f"**Win Rate:** {_pct(m['win_rate'])}",
            f"**Sharpe:** {m['sharpe']:.2f}  |  "
            f"**Max DD:** {_pct(m['max_drawdown'])}  |  "
            f"**Profit Factor:** {m['profit_factor']:.2f}",
            "",
        ]

        pb = self._pair_breakdown(trades)
        if pb:
            lines.append("### Per-Pair Performance")
            for pair, stats in sorted(pb.items()):
                lines.append(
                    f"- **{pair}**: {stats['trades']} trades, "
                    f"P&L {_sign(stats['pnl'])}{stats['pnl']:.4f}, "
                    f"WR {_pct(stats['win_rate'])}"
                )
            lines.append("")

        sb = self._strategy_breakdown(trades)
        if sb:
            lines.append("### Per-Strategy Performance")
            for strat, stats in sorted(sb.items()):
                lines.append(
                    f"- **{strat}**: {stats['trades']} trades, "
                    f"P&L {_sign(stats['pnl'])}{stats['pnl']:.4f}, "
                    f"WR {_pct(stats['win_rate'])}"
                )
            lines.append("")

        return "\n".join(lines)
