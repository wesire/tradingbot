"""
Sentiment aggregator - combines and processes sentiment data from multiple sources.
"""
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import logging
import statistics

from .provider import SentimentProvider, SentimentData

logger = logging.getLogger(__name__)


class AggregatedSentiment:
    """Aggregated sentiment for an asset."""
    
    def __init__(
        self,
        asset: str,
        score: float,
        confidence: float,
        sample_size: int,
        trend: str = "neutral",
        updated_at: Optional[datetime] = None
    ):
        """
        Initialize aggregated sentiment.
        
        Args:
            asset: Asset symbol
            score: Aggregated sentiment score (-1 to 1)
            confidence: Overall confidence (0 to 1)
            sample_size: Number of data points used
            trend: "bullish", "bearish", or "neutral"
            updated_at: When aggregation was computed
        """
        self.asset = asset
        self.score = score
        self.confidence = confidence
        self.sample_size = sample_size
        self.trend = trend
        self.updated_at = updated_at or datetime.now(timezone.utc)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'asset': self.asset,
            'score': self.score,
            'confidence': self.confidence,
            'sample_size': self.sample_size,
            'trend': self.trend,
            'updated_at': self.updated_at.isoformat()
        }


class SentimentAggregator:
    """
    Aggregates sentiment data from multiple providers and computes overall scores.
    """
    
    def __init__(self, providers: List[SentimentProvider]):
        """
        Initialize aggregator.
        
        Args:
            providers: List of sentiment providers
        """
        self.providers = providers
        logger.info(f"Initialized SentimentAggregator with {len(providers)} providers")
    
    def aggregate_sentiment(
        self,
        asset: str,
        lookback_hours: int = 24
    ) -> Optional[AggregatedSentiment]:
        """
        Aggregate sentiment for a single asset.
        
        Args:
            asset: Asset symbol
            lookback_hours: Hours of history to consider
            
        Returns:
            AggregatedSentiment object or None if no data available
        """
        all_sentiments: List[SentimentData] = []
        
        # Collect sentiment from all providers
        for provider in self.providers:
            try:
                sentiments = provider.get_sentiment(asset, lookback_hours)
                all_sentiments.extend(sentiments)
            except Exception as e:
                logger.error(f"Error getting sentiment from provider: {e}")
                continue
        
        if not all_sentiments:
            logger.warning(f"No sentiment data available for {asset}")
            return None
        
        # Calculate weighted average score
        total_weight = 0
        weighted_sum = 0
        
        for sentiment in all_sentiments:
            weight = sentiment.confidence
            weighted_sum += sentiment.score * weight
            total_weight += weight
        
        avg_score = weighted_sum / total_weight if total_weight > 0 else 0
        
        # Calculate overall confidence (average of individual confidences)
        avg_confidence = statistics.mean([s.confidence for s in all_sentiments])
        
        # Determine trend
        if avg_score > 0.15:
            trend = "bullish"
        elif avg_score < -0.15:
            trend = "bearish"
        else:
            trend = "neutral"
        
        return AggregatedSentiment(
            asset=asset,
            score=avg_score,
            confidence=avg_confidence,
            sample_size=len(all_sentiments),
            trend=trend
        )
    
    def aggregate_multi_asset(
        self,
        assets: List[str],
        lookback_hours: int = 24
    ) -> Dict[str, AggregatedSentiment]:
        """
        Aggregate sentiment for multiple assets.
        
        Args:
            assets: List of asset symbols
            lookback_hours: Hours of history to consider
            
        Returns:
            Dictionary mapping asset symbols to AggregatedSentiment objects
        """
        result = {}
        
        for asset in assets:
            # Extract base asset symbol
            base_asset = asset.split('/')[0] if '/' in asset else asset
            
            sentiment = self.aggregate_sentiment(base_asset, lookback_hours)
            if sentiment:
                result[base_asset] = sentiment
        
        return result
    
    def get_market_overview(
        self,
        assets: List[str],
        lookback_hours: int = 24
    ) -> Dict[str, Any]:
        """
        Get overall market sentiment overview.
        
        Args:
            assets: List of asset symbols to analyze
            lookback_hours: Hours of history to consider
            
        Returns:
            Dictionary with market overview statistics
        """
        sentiments = self.aggregate_multi_asset(assets, lookback_hours)
        
        if not sentiments:
            return {
                'overall_score': 0,
                'overall_trend': 'neutral',
                'bullish_count': 0,
                'bearish_count': 0,
                'neutral_count': 0,
                'asset_count': 0
            }
        
        scores = [s.score for s in sentiments.values()]
        trends = [s.trend for s in sentiments.values()]
        
        return {
            'overall_score': statistics.mean(scores),
            'overall_trend': max(set(trends), key=trends.count),  # Most common trend
            'bullish_count': trends.count('bullish'),
            'bearish_count': trends.count('bearish'),
            'neutral_count': trends.count('neutral'),
            'asset_count': len(sentiments),
            'updated_at': datetime.now(timezone.utc).isoformat()
        }
