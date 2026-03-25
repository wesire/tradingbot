"""
Unit tests for reporting modules: TradeJournal, TaxExporter, PerformanceReportGenerator.
"""
import csv
import os
from datetime import datetime, timezone

import pytest

from bot.reporting.trade_journal import TradeJournal
from bot.reporting.tax_exporter import TaxExporter, _split_pair
from bot.reporting.performance_report import PerformanceReportGenerator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _trade(
    pnl=10.0,
    pair="BTC/USDT",
    side="buy",
    entry=40000.0,
    exit_price=40100.0,
    amount=0.001,
    fees=0.01,
    strategy="test_strategy",
    session="london",
    year=None,
):
    if year is None:
        year = datetime.now(timezone.utc).year
    return {
        "pair": pair,
        "side": side,
        "entry_price": entry,
        "exit_price": exit_price,
        "amount": amount,
        "fees": fees,
        "pnl": pnl,
        "strategy": strategy,
        "session": session,
        "opened_at": datetime.now(timezone.utc).isoformat(),
        "closed_at": datetime.now(timezone.utc).isoformat(),
        "trade_id": "tx_abc123",
    }


# ---------------------------------------------------------------------------
# TradeJournal
# ---------------------------------------------------------------------------

class TestTradeJournal:
    def test_log_and_retrieve(self):
        journal = TradeJournal(db_path=":memory:")
        row_id = journal.log_trade(_trade())
        assert row_id == 1
        trades = journal.get_trades()
        assert len(trades) == 1
        assert trades[0]["pair"] == "BTC/USDT"
        journal.close()

    def test_get_trade_detail(self):
        journal = TradeJournal(db_path=":memory:")
        row_id = journal.log_trade(_trade(pnl=5.5))
        detail = journal.get_trade_detail(row_id)
        assert detail is not None
        assert detail["pnl"] == pytest.approx(5.5)
        journal.close()

    def test_get_trade_detail_not_found(self):
        journal = TradeJournal(db_path=":memory:")
        assert journal.get_trade_detail(999) is None
        journal.close()

    def test_filter_by_pair(self):
        journal = TradeJournal(db_path=":memory:")
        journal.log_trade(_trade(pair="BTC/USDT"))
        journal.log_trade(_trade(pair="ETH/USDT"))
        journal.log_trade(_trade(pair="BTC/USDT"))
        btc_trades = journal.get_trades(pair="BTC/USDT")
        assert len(btc_trades) == 2
        journal.close()

    def test_filter_by_date_range(self):
        journal = TradeJournal(db_path=":memory:")
        # Trade with a far-future timestamp
        t_recent = _trade()
        t_recent["closed_at"] = "2030-06-01T10:05:00+00:00"
        journal.log_trade(t_recent)
        # Trade with an old timestamp
        t_old = _trade()
        t_old["closed_at"] = "2020-06-01T10:05:00+00:00"
        journal.log_trade(t_old)
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        recent = journal.get_trades(start_date=start)
        assert len(recent) == 1
        journal.close()

    def test_multiple_trades(self):
        journal = TradeJournal(db_path=":memory:")
        for i in range(10):
            journal.log_trade(_trade(pnl=float(i)))
        trades = journal.get_trades()
        assert len(trades) == 10
        journal.close()


# ---------------------------------------------------------------------------
# TaxExporter
# ---------------------------------------------------------------------------

class TestTaxExporter:
    def _make_journal(self):
        year = datetime.now(timezone.utc).year
        journal = TradeJournal(db_path=":memory:")
        journal.log_trade(_trade(pair="BTC/USDT", side="buy", pnl=10.0))
        journal.log_trade(_trade(pair="ETH/USDT", side="sell", pnl=-5.0))
        # One trade in a past year
        t_past = _trade(pair="SOL/USDT", side="buy", pnl=3.0)
        t_past["opened_at"] = "2020-06-01T10:00:00+00:00"
        t_past["closed_at"] = "2020-06-01T10:05:00+00:00"
        journal.log_trade(t_past)
        return journal, year

    def test_export_koinly_csv(self, tmp_path):
        journal, year = self._make_journal()
        exporter = TaxExporter(journal)
        path = str(tmp_path / "koinly.csv")
        count = exporter.export_koinly_csv(path, year=year)
        assert count == 2
        with open(path) as fh:
            reader = csv.DictReader(fh)
            rows = list(reader)
        assert len(rows) == 2
        assert "Date" in rows[0]
        assert "Received Currency" in rows[0]
        journal.close()

    def test_export_koinly_buy_trade(self, tmp_path):
        journal = TradeJournal(db_path=":memory:")
        journal.log_trade(_trade(pair="BTC/USDT", side="buy"))
        exporter = TaxExporter(journal)
        year = datetime.now(timezone.utc).year
        path = str(tmp_path / "koinly_buy.csv")
        exporter.export_koinly_csv(path, year=year)
        with open(path) as fh:
            reader = csv.DictReader(fh)
            row = next(reader)
        assert row["Received Currency"] == "BTC"
        assert row["Sent Currency"] == "USDT"
        journal.close()

    def test_export_koinly_sell_trade(self, tmp_path):
        journal = TradeJournal(db_path=":memory:")
        journal.log_trade(_trade(pair="BTC/USDT", side="sell"))
        exporter = TaxExporter(journal)
        year = datetime.now(timezone.utc).year
        path = str(tmp_path / "koinly_sell.csv")
        exporter.export_koinly_csv(path, year=year)
        with open(path) as fh:
            reader = csv.DictReader(fh)
            row = next(reader)
        assert row["Sent Currency"] == "BTC"
        assert row["Received Currency"] == "USDT"
        journal.close()

    def test_export_cointracker_csv(self, tmp_path):
        journal, year = self._make_journal()
        exporter = TaxExporter(journal)
        path = str(tmp_path / "cointracker.csv")
        count = exporter.export_cointracker_csv(path, year=year)
        assert count == 2
        with open(path) as fh:
            reader = csv.DictReader(fh)
            rows = list(reader)
        assert len(rows) == 2
        assert "Received Quantity" in rows[0]
        journal.close()

    def test_export_generic_csv(self, tmp_path):
        journal, year = self._make_journal()
        exporter = TaxExporter(journal)
        path = str(tmp_path / "generic.csv")
        count = exporter.export_generic_csv(path, year=year)
        assert count == 2
        with open(path) as fh:
            reader = csv.DictReader(fh)
            rows = list(reader)
        assert "pnl" in rows[0]
        journal.close()

    def test_export_filters_by_year(self, tmp_path):
        journal, year = self._make_journal()
        exporter = TaxExporter(journal)
        path = str(tmp_path / "year2020.csv")
        count = exporter.export_koinly_csv(path, year=2020)
        assert count == 1  # Only SOL trade is in 2020
        journal.close()


# ---------------------------------------------------------------------------
# TaxExporter helper: _split_pair
# ---------------------------------------------------------------------------

class TestSplitPair:
    def test_standard_pair(self):
        assert _split_pair("BTC/USDT") == ("BTC", "USDT")

    def test_margin_pair(self):
        base, quote = _split_pair("BTC/USDT:USDT")
        assert base == "BTC"
        assert quote == "USDT"

    def test_no_slash(self):
        base, quote = _split_pair("BTCUSDT")
        assert base == "BTCUSDT"
        assert quote == "USDT"


# ---------------------------------------------------------------------------
# PerformanceReportGenerator
# ---------------------------------------------------------------------------

class TestPerformanceReportGenerator:
    def _make_journal_with_trades(self):
        journal = TradeJournal(db_path=":memory:")
        journal.log_trade(_trade(pnl=10.0, pair="BTC/USDT", strategy="scalp"))
        journal.log_trade(_trade(pnl=-5.0, pair="ETH/USDT", strategy="scalp"))
        journal.log_trade(_trade(pnl=7.0, pair="BTC/USDT", strategy="momentum"))
        return journal

    def test_daily_report_has_trades(self):
        journal = self._make_journal_with_trades()
        gen = PerformanceReportGenerator(journal)
        report = gen.generate_daily_report()
        assert "Daily Report" in report
        assert "Trades" in report
        journal.close()

    def test_daily_report_no_trades(self):
        journal = TradeJournal(db_path=":memory:")
        gen = PerformanceReportGenerator(journal)
        report = gen.generate_daily_report()
        assert "No trades" in report
        journal.close()

    def test_weekly_report_has_section_headers(self):
        journal = self._make_journal_with_trades()
        gen = PerformanceReportGenerator(journal)
        report = gen.generate_weekly_report()
        assert "Weekly Report" in report
        journal.close()

    def test_monthly_report_contains_month_name(self):
        journal = self._make_journal_with_trades()
        gen = PerformanceReportGenerator(journal)
        now = datetime.now(timezone.utc)
        report = gen.generate_monthly_report(year=now.year, month=now.month)
        assert "Monthly Report" in report
        journal.close()

    def test_monthly_report_no_trades(self):
        journal = TradeJournal(db_path=":memory:")
        gen = PerformanceReportGenerator(journal)
        report = gen.generate_monthly_report(year=2020, month=1)
        assert "No trades" in report
        journal.close()

    def test_report_contains_pnl_and_win_rate(self):
        journal = self._make_journal_with_trades()
        gen = PerformanceReportGenerator(journal)
        report = gen.generate_weekly_report()
        assert "P&L" in report or "pnl" in report.lower()
        assert "Win Rate" in report
        journal.close()
