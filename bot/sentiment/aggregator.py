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
    Aggregates sentiment data from multiple providers with configurable
    per-provider weights.

    Each provider is identified by its class name.  Weights are normalised
    so they always sum to 1.0.  If a provider fails or returns no data, its
    weight is redistributed proportionally among the remaining active
    providers.  Individual provider scores and weights are logged at INFO
    level so operators can audit the aggregation.
    """

    def __init__(
        self,
        providers: List[SentimentProvider],
        weights: Optional[Dict[str, float]] = None,
    ):
        """
        Initialize aggregator.

        Args:
            providers: List of sentiment providers.
            weights: Optional mapping of provider class name to weight
                (e.g. ``{"CryptoPanicSentimentProvider": 0.4,
                "RedditSentimentProvider": 0.3,
                "MockSentimentProvider": 0.3}``).
                Weights are normalised internally.  When omitted, all
                providers receive equal weight.
        """
        self.providers = providers
        self._weights: Dict[str, float] = weights or {}
        logger.info(
            "Initialized SentimentAggregator with %d providers: %s",
            len(providers),
            [type(p).__name__ for p in providers],
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def aggregate_sentiment(
        self,
        asset: str,
        lookback_hours: int = 24
    ) -> Optional[AggregatedSentiment]:
        """
        Aggregate sentiment for a single asset.

        Each provider's contribution is weighted by its configured weight
        (defaulting to equal weighting when weights are not specified).
        Providers that raise exceptions or return no data have their weight
        redistributed proportionally among the remaining providers.

        Args:
            asset: Asset symbol
            lookback_hours: Hours of history to consider

        Returns:
            AggregatedSentiment object or None if no data available
        """
        # Collect per-provider data, skipping failures
        # Use index-qualified keys so multiple instances of the same class
        # can coexist (e.g. two MockSentimentProvider instances).
        provider_results: Dict[str, List[SentimentData]] = {}
        provider_weights: Dict[str, float] = {}

        for idx, provider in enumerate(self.providers):
            class_name = type(provider).__name__
            key = f"{class_name}[{idx}]"
            raw_weight = self._weights.get(class_name, 1.0)
            try:
                sentiments = provider.get_sentiment(asset, lookback_hours)
                if sentiments:
                    provider_results[key] = sentiments
                    provider_weights[key] = raw_weight
                else:
                    logger.warning(
                        "Provider %s returned no data for %s – "
                        "redistributing weight %.2f",
                        class_name, asset, raw_weight,
                    )
            except Exception as exc:
                logger.error(
                    "Error getting sentiment from provider %s for %s: %s",
                    class_name, asset, exc,
                )

        if not provider_results:
            logger.warning("No sentiment data available for %s", asset)
            return None

        # Normalise weights for active providers
        total_weight = sum(provider_weights.values())
        norm_weights = {
            k: v / total_weight for k, v in provider_weights.items()
        }

        # Compute provider-level scores then combine with normalised weights
        weighted_score = 0.0
        weighted_confidence = 0.0
        total_samples = 0

        for name, sentiments in provider_results.items():
            w = norm_weights[name]

            # Confidence-weighted score within this provider
            provider_conf_sum = sum(s.confidence for s in sentiments)
            if provider_conf_sum > 0:
                provider_score = (
                    sum(s.score * s.confidence for s in sentiments)
                    / provider_conf_sum
                )
            else:
                provider_score = statistics.mean(
                    [s.score for s in sentiments]
                )

            provider_confidence = statistics.mean(
                [s.confidence for s in sentiments]
            )

            logger.info(
                "Sentiment provider %s [weight=%.2f]: "
                "score=%.3f confidence=%.3f samples=%d",
                key, w, provider_score, provider_confidence, len(sentiments),
            )

            weighted_score += provider_score * w
            weighted_confidence += provider_confidence * w
            total_samples += len(sentiments)

        # Determine trend
        if weighted_score > 0.15:
            trend = "bullish"
        elif weighted_score < -0.15:
            trend = "bearish"
        else:
            trend = "neutral"

        return AggregatedSentiment(
            asset=asset,
            score=weighted_score,
            confidence=weighted_confidence,
            sample_size=total_samples,
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
