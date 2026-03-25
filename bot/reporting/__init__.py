"""
Tax & compliance reporting module.

Provides SQLite-backed trade journal, CSV export in Koinly/CoinTracker
formats, and markdown performance report generation.
"""
from .trade_journal import TradeJournal
from .tax_exporter import TaxExporter
from .performance_report import PerformanceReportGenerator

__all__ = [
    "TradeJournal",
    "TaxExporter",
    "PerformanceReportGenerator",
]
