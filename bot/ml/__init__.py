"""
ML Signal Enhancement module for the trading bot.

Provides machine-learning-based signal classification,
feature engineering, model explainability, and model monitoring.
"""
from .feature_engineer import FeatureEngineer
from .signal_classifier import SignalClassifier
from .explainer import ModelExplainer
from .model_monitor import ModelMonitor
from .backtester import MLBacktester, BacktestResult

__all__ = [
    "FeatureEngineer",
    "SignalClassifier",
    "ModelExplainer",
    "ModelMonitor",
    "MLBacktester",
    "BacktestResult",
]
