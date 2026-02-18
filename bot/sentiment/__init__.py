"""
Sentiment analysis module for trading bot.
"""
from .provider import SentimentProvider, MockSentimentProvider
from .aggregator import SentimentAggregator
from .storage import SentimentStorage

__all__ = [
    'SentimentProvider',
    'MockSentimentProvider',
    'SentimentAggregator',
    'SentimentStorage',
]
