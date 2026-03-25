"""
Portfolio management module.

Provides correlation analysis, risk-parity allocation, and performance
tracking for the multi-pair trading bot.
"""
from .correlation_manager import CorrelationManager
from .risk_parity import RiskParityAllocator
from .performance_tracker import PerformanceTracker

__all__ = [
    "CorrelationManager",
    "RiskParityAllocator",
    "PerformanceTracker",
]
