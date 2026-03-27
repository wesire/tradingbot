"""
Opportunity scorer - scores and ranks potential trading opportunities.
"""
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


@dataclass
class Opportunity:
    """Represents a scored trading opportunity."""
    
    pair: str
    side: str  # "long" or "short"
    confidence: float  # 0.0-1.0
    entry_zone: str  # e.g., "0.45-0.46"
    invalidation: str  # Price level where setup is invalidated
    risk_reward: float  # Expected R:R ratio
    timeframe: str
    
    # Component scores
    technical_score: float
    regime_score: float
    sentiment_score: float
    liquidity_score: float
    
    # Additional context
    rationale: List[str]
    last_updated: str

    # ML enrichment (populated when a SignalClassifier is loaded)
    ml_confidence: Optional[float] = field(default=None)
    ml_signal: Optional[str] = field(default=None)
    ml_explanation: Optional[str] = field(default=None)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


class OpportunityScorer:
    """
    Scores trading opportunities per enabled pair using weighted components.
    
    Components:
    - Technical setup score (from signal filters)
    - Regime alignment score (from regime filter)
    - Sentiment score (from sentiment pipeline)
    - Liquidity/volatility quality score (from ATR/volume)

    Optionally enriches opportunities with ML signals when a
    ``SignalClassifier`` and ``FeatureEngineer`` are provided.
    """
    
    def __init__(
        self,
        technical_weight: float = 0.35,
        regime_weight: float = 0.30,
        sentiment_weight: float = 0.20,
        liquidity_weight: float = 0.15,
        ml_classifier: Optional[Any] = None,
        feature_engineer: Optional[Any] = None,
        ml_explainer: Optional[Any] = None,
        min_ml_confidence: float = 0.60,
    ):
        """
        Initialize opportunity scorer.
        
        Args:
            technical_weight: Weight for technical setup (0-1)
            regime_weight: Weight for regime alignment (0-1)
            sentiment_weight: Weight for sentiment (0-1)
            liquidity_weight: Weight for liquidity/volatility (0-1)
            ml_classifier: Optional fitted SignalClassifier instance.
            feature_engineer: Optional FeatureEngineer used to build
                the feature matrix fed to *ml_classifier*.
            ml_explainer: Optional ModelExplainer for SHAP explanations.
            min_ml_confidence: Minimum ML probability to include a
                non-neutral ML signal.
        """
        # Normalize weights
        total = technical_weight + regime_weight + sentiment_weight + liquidity_weight
        self.technical_weight = technical_weight / total
        self.regime_weight = regime_weight / total
        self.sentiment_weight = sentiment_weight / total
        self.liquidity_weight = liquidity_weight / total

        # ML components (all optional)
        self.ml_classifier = ml_classifier
        self.feature_engineer = feature_engineer
        self.ml_explainer = ml_explainer
        self.min_ml_confidence = min_ml_confidence
        
        logger.info(
            f"Initialized OpportunityScorer - weights: "
            f"tech={self.technical_weight:.2f}, regime={self.regime_weight:.2f}, "
            f"sentiment={self.sentiment_weight:.2f}, liquidity={self.liquidity_weight:.2f}"
        )
    
    def score_opportunity(
        self,
        pair: str,
        timeframe: str,
        technical_data: Dict[str, Any],
        regime_data: Dict[str, Any],
        sentiment_data: Optional[Dict[str, Any]] = None,
        liquidity_data: Optional[Dict[str, Any]] = None,
        ohlcv_df: Optional[Any] = None,
    ) -> Optional[Opportunity]:
        """
        Score a single trading opportunity.
        
        Args:
            pair: Trading pair symbol
            timeframe: Timeframe for analysis
            technical_data: Technical indicators and signals
            regime_data: Regime filter data
            sentiment_data: Optional sentiment data
            liquidity_data: Optional liquidity/volatility data
            ohlcv_df: Optional OHLCV DataFrame used for ML feature generation.
            
        Returns:
            Opportunity object or None if no valid setup
        """
        # Score each component
        tech_score = self._score_technical(technical_data)
        regime_score = self._score_regime(regime_data)
        sent_score = self._score_sentiment(sentiment_data) if sentiment_data else 0.0
        liq_score = self._score_liquidity(liquidity_data) if liquidity_data else 0.5
        
        # Calculate weighted overall confidence
        confidence = (
            tech_score * self.technical_weight +
            regime_score * self.regime_weight +
            sent_score * self.sentiment_weight +
            liq_score * self.liquidity_weight
        )
        
        # Determine side bias
        side = self._determine_side(technical_data, regime_data)
        
        if side is None or confidence < 0.1:
            # No clear opportunity
            return None
        
        # Calculate entry zone and invalidation
        entry_zone, invalidation = self._calculate_levels(
            technical_data, side
        )
        
        # Calculate risk-reward estimate
        risk_reward = self._estimate_risk_reward(
            technical_data, side
        )
        
        # Generate rationale
        rationale = self._generate_rationale(
            tech_score, regime_score, sent_score, liq_score,
            technical_data, regime_data, sentiment_data
        )

        # ML enrichment (optional – gracefully degraded when not configured)
        ml_confidence, ml_signal, ml_explanation = self._ml_enrich(ohlcv_df)
        
        return Opportunity(
            pair=pair,
            side=side,
            confidence=confidence,
            entry_zone=entry_zone,
            invalidation=invalidation,
            risk_reward=risk_reward,
            timeframe=timeframe,
            technical_score=tech_score,
            regime_score=regime_score,
            sentiment_score=sent_score,
            liquidity_score=liq_score,
            rationale=rationale,
            last_updated=datetime.now(timezone.utc).isoformat(),
            ml_confidence=ml_confidence,
            ml_signal=ml_signal,
            ml_explanation=ml_explanation,
        )
    
    def score_multiple(
        self,
        pairs_data: Dict[str, Dict[str, Any]]
    ) -> List[Opportunity]:
        """
        Score opportunities for multiple pairs.
        
        Args:
            pairs_data: Dictionary mapping pair symbols to their data
            
        Returns:
            List of Opportunity objects, sorted by confidence (descending)
        """
        opportunities = []
        
        for pair, data in pairs_data.items():
            try:
                opp = self.score_opportunity(
                    pair=pair,
                    timeframe=data.get('timeframe', '5m'),
                    technical_data=data.get('technical', {}),
                    regime_data=data.get('regime', {}),
                    sentiment_data=data.get('sentiment'),
                    liquidity_data=data.get('liquidity')
                )
                
                if opp:
                    opportunities.append(opp)
            except Exception as e:
                logger.error(f"Error scoring opportunity for {pair}: {e}")
                continue
        
        # Sort by confidence descending
        opportunities.sort(key=lambda x: x.confidence, reverse=True)
        
        return opportunities
    
    def _score_technical(self, data: Dict[str, Any]) -> float:
        """
        Score technical setup from 0 to 1.
        
        Args:
            data: Technical indicator data
            
        Returns:
            Score from 0 to 1
        """
        score = 0.5  # Neutral baseline
        
        # RSI positioning
        rsi = data.get('rsi', 50)
        if rsi < 35:
            score += 0.2  # Oversold - potential bounce
        elif rsi > 65:
            score += 0.2  # Overbought - potential fade
        
        # EMA alignment
        if data.get('price_vs_ema'):
            score += 0.15
        
        # Filters passed
        if data.get('filters_passed'):
            score += 0.15
        
        # Volume confirmation
        if data.get('volume_above_avg'):
            score += 0.1
        
        return min(1.0, score)
    
    def _score_regime(self, data: Dict[str, Any]) -> float:
        """
        Score regime alignment from 0 to 1.
        
        Args:
            data: Regime filter data
            
        Returns:
            Score from 0 to 1
        """
        if data.get('bullish') or data.get('bearish'):
            adx = data.get('adx', 0)
            # Higher ADX = stronger regime = higher score
            return min(1.0, adx / 40.0)
        else:
            return 0.3  # Neutral regime gets low score
    
    def _score_sentiment(self, data: Optional[Dict[str, Any]]) -> float:
        """
        Score sentiment from 0 to 1.
        
        Args:
            data: Optional sentiment data
            
        Returns:
            Score from 0 to 1
        """
        if not data:
            return 0.5  # Neutral
        
        score = data.get('score', 0.0)  # -1 to 1
        confidence = data.get('confidence', 0.5)
        
        # Convert to 0-1 scale, weighted by confidence
        normalized = (score + 1) / 2  # Convert -1,1 to 0,1
        return normalized * confidence + 0.5 * (1 - confidence)
    
    def _score_liquidity(self, data: Optional[Dict[str, Any]]) -> float:
        """
        Score liquidity/volatility quality from 0 to 1.
        
        Args:
            data: Optional liquidity/volatility data
            
        Returns:
            Score from 0 to 1
        """
        if not data:
            return 0.5  # Neutral
        
        score = 0.5
        
        # ATR status
        atr_status = data.get('atr_status', 'normal')
        if atr_status == 'normal':
            score += 0.3
        elif atr_status == 'low':
            score -= 0.2
        elif atr_status == 'extreme':
            score -= 0.3
        
        # Volume quality
        if data.get('volume_consistent'):
            score += 0.2
        
        return max(0.0, min(1.0, score))
    
    def _determine_side(
        self,
        technical: Dict[str, Any],
        regime: Dict[str, Any]
    ) -> Optional[str]:
        """
        Determine trade side (long/short) or None.
        
        Args:
            technical: Technical data
            regime: Regime data
            
        Returns:
            "long", "short", or None
        """
        if regime.get('bullish') and technical.get('rsi', 50) <= 55:
            return "long"
        elif regime.get('bearish') and technical.get('rsi', 50) >= 45:
            return "short"
        elif technical.get('rsi', 50) < 35:
            return "long"  # oversold bounce regardless of regime
        elif technical.get('rsi', 50) > 65:
            return "short"  # overbought fade regardless of regime
        else:
            return None
    
    def _calculate_levels(
        self,
        technical: Dict[str, Any],
        side: str
    ) -> tuple[str, str]:
        """
        Calculate entry zone and invalidation level.
        
        Args:
            technical: Technical data
            side: Trade side
            
        Returns:
            Tuple of (entry_zone, invalidation)
        """
        current_price = technical.get('close', 0)
        atr = technical.get('atr', current_price * 0.01)
        
        if side == "long":
            entry_low = current_price - atr * 0.5
            entry_high = current_price + atr * 0.3
            invalidation = current_price - atr * 2
        else:  # short
            entry_low = current_price - atr * 0.3
            entry_high = current_price + atr * 0.5
            invalidation = current_price + atr * 2
        
        entry_zone = f"{entry_low:.4f}-{entry_high:.4f}"
        invalidation_str = f"{invalidation:.4f}"
        
        return entry_zone, invalidation_str
    
    def _estimate_risk_reward(
        self,
        technical: Dict[str, Any],
        side: str
    ) -> float:
        """
        Estimate risk-reward ratio.
        
        Args:
            technical: Technical data
            side: Trade side
            
        Returns:
            R:R ratio
        """
        # Simple estimation based on ATR multiples
        # Typically using 2 ATR stop and 3-4 ATR target
        return 2.0  # Conservative estimate
    
    def _generate_rationale(
        self,
        tech_score: float,
        regime_score: float,
        sent_score: float,
        liq_score: float,
        technical: Dict[str, Any],
        regime: Dict[str, Any],
        sentiment: Optional[Dict[str, Any]]
    ) -> List[str]:
        """Generate rationale for the opportunity."""
        rationale = []
        
        # Technical rationale
        if tech_score > 0.6:
            rationale.append("Strong technical setup with confirmed signals")
        
        # Regime rationale
        if regime.get('bullish'):
            rationale.append(f"Bullish regime with ADX {regime.get('adx', 0):.1f}")
        elif regime.get('bearish'):
            rationale.append(f"Bearish regime with ADX {regime.get('adx', 0):.1f}")
        
        # Sentiment rationale
        if sentiment and abs(sent_score - 0.5) > 0.2:
            trend = sentiment.get('trend', 'neutral')
            rationale.append(f"Sentiment aligns: {trend}")
        
        # Liquidity rationale
        if liq_score > 0.6:
            rationale.append("Good liquidity and normal volatility")
        
        if not rationale:
            rationale.append("Moderate setup with mixed factors")
        
        return rationale

    def _ml_enrich(
        self,
        ohlcv_df: Optional[Any],
    ) -> tuple:
        """
        Run ML inference and return (ml_confidence, ml_signal, ml_explanation).

        Returns ``(None, None, None)`` when no ML components are configured
        or when an error occurs (graceful degradation).
        """
        if (
            self.ml_classifier is None
            or self.feature_engineer is None
            or ohlcv_df is None
        ):
            return None, None, None

        try:
            features = self.feature_engineer.transform(ohlcv_df)
            if features.empty:
                return None, None, None

            ml_signal, ml_confidence = self.ml_classifier.predict(features)

            # Build SHAP explanation if explainer is available
            ml_explanation: Optional[str] = None
            if self.ml_explainer is not None:
                try:
                    shap_vals = self.ml_explainer.explain_prediction(
                        self.ml_classifier._model,
                        features.iloc[[-1]],
                    )
                    ml_explanation = self.ml_explainer.format_explanation(
                        shap_vals,
                        self.feature_engineer.feature_names,
                        top_n=3,
                    )
                except Exception as exc:
                    logger.debug("SHAP explanation failed: %s", exc)

            return float(ml_confidence), str(ml_signal), ml_explanation

        except Exception as exc:
            logger.warning("ML enrichment failed: %s", exc)
            return None, None, None
