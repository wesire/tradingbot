"""
Sentiment provider base class and mock implementation.
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import logging
import random

logger = logging.getLogger(__name__)


class SentimentData:
    """Container for sentiment data."""
    
    def __init__(
        self,
        asset: str,
        score: float,
        confidence: float,
        headline: str = "",
        source: str = "",
        timestamp: Optional[datetime] = None
    ):
        """
        Initialize sentiment data.
        
        Args:
            asset: Asset symbol (e.g., "BTC", "ETH")
            score: Sentiment score from -1 (very negative) to +1 (very positive)
            confidence: Confidence level from 0 to 1
            headline: News headline or summary
            source: Source of sentiment data
            timestamp: When sentiment was measured
        """
        self.asset = asset
        self.score = max(-1.0, min(1.0, score))  # Clamp to [-1, 1]
        self.confidence = max(0.0, min(1.0, confidence))  # Clamp to [0, 1]
        self.headline = headline
        self.source = source
        self.timestamp = timestamp or datetime.now(timezone.utc)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'asset': self.asset,
            'score': self.score,
            'confidence': self.confidence,
            'headline': self.headline,
            'source': self.source,
            'timestamp': self.timestamp.isoformat()
        }


class SentimentProvider(ABC):
    """Abstract base class for sentiment providers."""
    
    @abstractmethod
    def get_sentiment(self, asset: str, lookback_hours: int = 24) -> List[SentimentData]:
        """
        Get sentiment data for an asset.
        
        Args:
            asset: Asset symbol (e.g., "BTC", "ETH")
            lookback_hours: Number of hours to look back
            
        Returns:
            List of SentimentData objects
        """
        pass
    
    @abstractmethod
    def get_multi_asset_sentiment(
        self,
        assets: List[str],
        lookback_hours: int = 24
    ) -> Dict[str, List[SentimentData]]:
        """
        Get sentiment data for multiple assets.
        
        Args:
            assets: List of asset symbols
            lookback_hours: Number of hours to look back
            
        Returns:
            Dictionary mapping asset symbols to lists of SentimentData
        """
        pass


class MockSentimentProvider(SentimentProvider):
    """
    Mock sentiment provider for testing and development.
    
    Generates random but realistic-looking sentiment data.
    """
    
    MOCK_HEADLINES = {
        "BTC": [
            "Bitcoin surges past key resistance level amid institutional buying",
            "BTC network hashrate reaches all-time high",
            "Major exchange sees record Bitcoin withdrawals",
            "Analysts predict Bitcoin consolidation before next move",
            "Bitcoin ETF sees continued inflows this week",
        ],
        "ETH": [
            "Ethereum network activity hits new highs",
            "ETH staking yields attract institutional investors",
            "Layer 2 solutions drive Ethereum adoption",
            "Ethereum developers announce major upgrade timeline",
            "DeFi activity on Ethereum continues to grow",
        ],
        "SOL": [
            "Solana network upgrade improves transaction speed",
            "SOL ecosystem sees surge in new projects",
            "Institutional interest in Solana grows",
            "Solana DEX volumes reach new milestone",
            "SOL price action shows strong momentum",
        ]
    }
    
    def __init__(self, base_sentiment: float = 0.1):
        """
        Initialize mock provider.
        
        Args:
            base_sentiment: Base sentiment bias (-1 to 1)
        """
        self.base_sentiment = base_sentiment
        logger.info("Initialized MockSentimentProvider")
    
    def get_sentiment(self, asset: str, lookback_hours: int = 24) -> List[SentimentData]:
        """Generate mock sentiment data for an asset."""
        num_datapoints = max(1, lookback_hours // 4)  # One datapoint every 4 hours
        sentiments = []
        
        # Extract base asset symbol (e.g., "BTC" from "BTC/USDT:USDT")
        base_asset = asset.split('/')[0] if '/' in asset else asset
        
        headlines = self.MOCK_HEADLINES.get(base_asset, [
            f"{base_asset} market shows continued activity",
            f"{base_asset} technical indicators suggest trend continuation",
        ])
        
        for i in range(num_datapoints):
            # Generate sentiment with some randomness around base
            score = self.base_sentiment + random.uniform(-0.3, 0.3)
            score = max(-1.0, min(1.0, score))
            
            # Higher confidence for neutral sentiment, lower for extremes
            confidence = 0.7 - abs(score) * 0.2 + random.uniform(-0.1, 0.1)
            confidence = max(0.0, min(1.0, confidence))
            
            sentiment = SentimentData(
                asset=base_asset,
                score=score,
                confidence=confidence,
                headline=random.choice(headlines),
                source="mock_provider",
                timestamp=datetime.now(timezone.utc)
            )
            sentiments.append(sentiment)
        
        return sentiments
    
    def get_multi_asset_sentiment(
        self,
        assets: List[str],
        lookback_hours: int = 24
    ) -> Dict[str, List[SentimentData]]:
        """Generate mock sentiment data for multiple assets."""
        result = {}
        for asset in assets:
            result[asset] = self.get_sentiment(asset, lookback_hours)
        return result
