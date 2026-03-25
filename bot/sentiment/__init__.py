"""
Sentiment analysis module for trading bot.
"""
from .provider import SentimentProvider, MockSentimentProvider
from .aggregator import SentimentAggregator, AggregatedSentiment
from .storage import SentimentStorage
from .cryptopanic_provider import CryptoPanicSentimentProvider
from .reddit_provider import RedditSentimentProvider
from .twitter_provider import TwitterSentimentProvider
from .fear_greed_provider import FearGreedProvider
from .economic_calendar import EconomicCalendarFilter

__all__ = [
    'SentimentProvider',
    'MockSentimentProvider',
    'SentimentAggregator',
    'AggregatedSentiment',
    'SentimentStorage',
    'CryptoPanicSentimentProvider',
    'RedditSentimentProvider',
    'TwitterSentimentProvider',
    'FearGreedProvider',
    'EconomicCalendarFilter',
]
