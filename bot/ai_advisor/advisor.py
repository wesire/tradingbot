"""
AI advisor layer - provides advisory guidance only, NEVER places orders directly.

CRITICAL: This module MUST NOT have any order placement capability.
All outputs are advisory only and require deterministic strategy confirmation.
"""
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass, asdict
import logging
import json

logger = logging.getLogger(__name__)

# HARD GATE: This module is advisory only
ADVISORY_ONLY = True  # DO NOT CHANGE THIS

if not ADVISORY_ONLY:
    raise RuntimeError("SECURITY VIOLATION: AI Advisor must always be advisory only")


@dataclass
class AdvisoryOutput:
    """
    Structured output from AI advisor.
    
    This is advisory guidance only and NEVER triggers trades directly.
    """
    pair: str
    timeframe: str
    bias: str  # "bullish", "bearish", "neutral"
    confidence: float  # 0.0-1.0
    rationale: List[str]
    risks: List[str]
    suggested_action: str  # "watch", "consider_long", "consider_short", "avoid"
    disclaimer: str
    generated_at: str
    
    # Technical context
    technical_score: float = 0.0
    regime_alignment: float = 0.0
    sentiment_score: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)


class AIAdvisor:
    """
    AI advisor that combines technical signals, sentiment, and regime data
    to provide advisory guidance.
    
    CRITICAL CONSTRAINTS:
    1. This class NEVER places orders
    2. All outputs are advisory only
    3. Trading requires deterministic strategy confirmation
    4. No direct integration with order execution
    """
    
    DISCLAIMER = (
        "Advisory only. Not financial advice. "
        "All trades require deterministic strategy confirmation. "
        "AI guidance does not guarantee results."
    )
    
    def __init__(
        self,
        technical_weight: float = 0.4,
        regime_weight: float = 0.3,
        sentiment_weight: float = 0.3
    ):
        """
        Initialize AI advisor.
        
        Args:
            technical_weight: Weight for technical signals (0-1)
            regime_weight: Weight for regime alignment (0-1)
            sentiment_weight: Weight for sentiment (0-1)
        """
        # Validate advisory-only mode
        if not ADVISORY_ONLY:
            raise RuntimeError("SECURITY VIOLATION: AI Advisor must be advisory only")
        
        # Normalize weights
        total = technical_weight + regime_weight + sentiment_weight
        self.technical_weight = technical_weight / total
        self.regime_weight = regime_weight / total
        self.sentiment_weight = sentiment_weight / total
        
        logger.info(
            "Initialized AIAdvisor (ADVISORY ONLY) - "
            f"weights: tech={self.technical_weight:.2f}, "
            f"regime={self.regime_weight:.2f}, sentiment={self.sentiment_weight:.2f}"
        )
        
        # Log security warning
        logger.warning(
            "AI Advisor is ADVISORY ONLY. "
            "It CANNOT and WILL NOT place orders. "
            "All trading requires deterministic strategy confirmation."
        )
    
    def generate_advisory(
        self,
        pair: str,
        timeframe: str,
        ohlcv_snapshot: Dict[str, Any],
        technical_signals: Dict[str, Any],
        regime_data: Dict[str, Any],
        sentiment_data: Optional[Dict[str, Any]] = None
    ) -> AdvisoryOutput:
        """
        Generate advisory guidance for a trading pair.
        
        HARD GATE: This method ONLY returns advisory data.
        It has NO capability to place orders.
        
        Args:
            pair: Trading pair symbol
            timeframe: Timeframe for analysis
            ohlcv_snapshot: Recent OHLCV data
            technical_signals: Technical indicator signals
            regime_data: Market regime information
            sentiment_data: Optional sentiment analysis
            
        Returns:
            AdvisoryOutput object with guidance
        """
        # Verify advisory-only mode
        assert ADVISORY_ONLY, "SECURITY VIOLATION: Must be advisory only"
        
        # Score each component
        technical_score = self._score_technical(technical_signals)
        regime_score = self._score_regime(regime_data)
        sentiment_score = self._score_sentiment(sentiment_data) if sentiment_data else 0
        
        # Calculate weighted overall score
        overall_score = (
            technical_score * self.technical_weight +
            regime_score * self.regime_weight +
            sentiment_score * self.sentiment_weight
        )
        
        # Determine bias and confidence
        bias, confidence = self._determine_bias(overall_score)
        
        # Generate rationale
        rationale = self._generate_rationale(
            technical_score, regime_score, sentiment_score,
            technical_signals, regime_data, sentiment_data
        )
        
        # Identify risks
        risks = self._identify_risks(
            technical_signals, regime_data, sentiment_data
        )
        
        # Suggest action (advisory only - no execution)
        suggested_action = self._suggest_action(bias, confidence)
        
        return AdvisoryOutput(
            pair=pair,
            timeframe=timeframe,
            bias=bias,
            confidence=confidence,
            rationale=rationale,
            risks=risks,
            suggested_action=suggested_action,
            disclaimer=self.DISCLAIMER,
            generated_at=datetime.utcnow().isoformat() + 'Z',
            technical_score=technical_score,
            regime_alignment=regime_score,
            sentiment_score=sentiment_score
        )
    
    def _score_technical(self, signals: Dict[str, Any]) -> float:
        """
        Score technical signals from -1 (bearish) to +1 (bullish).
        
        Args:
            signals: Dictionary of technical signals
            
        Returns:
            Score from -1 to 1
        """
        score = 0.0
        count = 0
        
        # RSI signal
        if 'rsi' in signals:
            rsi = signals['rsi']
            if rsi < 35:
                score += 0.5  # Oversold - bullish
            elif rsi > 65:
                score -= 0.5  # Overbought - bearish
            count += 1
        
        # EMA alignment
        if 'price_vs_ema' in signals:
            if signals['price_vs_ema'] > 0:
                score += 0.3
            else:
                score -= 0.3
            count += 1
        
        # Volume
        if 'volume_above_avg' in signals:
            if signals['volume_above_avg']:
                score += 0.2  # Strong volume confirms trend
            count += 1
        
        # ATR (volatility)
        if 'atr_status' in signals:
            if signals['atr_status'] == 'normal':
                score += 0.1  # Normal volatility is good
            elif signals['atr_status'] == 'extreme':
                score -= 0.3  # Extreme volatility is risky
            count += 1
        
        return score / count if count > 0 else 0.0
    
    def _score_regime(self, regime: Dict[str, Any]) -> float:
        """
        Score regime alignment from -1 (bearish regime) to +1 (bullish regime).
        
        Args:
            regime: Dictionary with regime information
            
        Returns:
            Score from -1 to 1
        """
        if regime.get('bullish'):
            adx = regime.get('adx', 0)
            # Stronger regime = higher score
            return min(1.0, adx / 50.0)
        elif regime.get('bearish'):
            adx = regime.get('adx', 0)
            return -min(1.0, adx / 50.0)
        else:
            return 0.0  # Neutral regime
    
    def _score_sentiment(self, sentiment: Optional[Dict[str, Any]]) -> float:
        """
        Score sentiment from -1 (very negative) to +1 (very positive).
        
        Args:
            sentiment: Optional sentiment data
            
        Returns:
            Score from -1 to 1
        """
        if not sentiment:
            return 0.0
        
        score = sentiment.get('score', 0.0)
        confidence = sentiment.get('confidence', 0.5)
        
        # Weight sentiment by confidence
        return score * confidence
    
    def _determine_bias(self, overall_score: float) -> Tuple[str, float]:
        """
        Determine bias and confidence from overall score.
        
        Args:
            overall_score: Overall score from -1 to 1
            
        Returns:
            Tuple of (bias, confidence)
        """
        abs_score = abs(overall_score)
        
        if overall_score > 0.2:
            bias = "bullish"
        elif overall_score < -0.2:
            bias = "bearish"
        else:
            bias = "neutral"
        
        # Confidence is based on magnitude of score
        confidence = min(1.0, abs_score * 2)
        
        return bias, confidence
    
    def _generate_rationale(
        self,
        tech_score: float,
        regime_score: float,
        sent_score: float,
        technical: Dict[str, Any],
        regime: Dict[str, Any],
        sentiment: Optional[Dict[str, Any]]
    ) -> List[str]:
        """Generate rationale bullet points."""
        rationale = []
        
        # Technical rationale
        if abs(tech_score) > 0.2:
            direction = "bullish" if tech_score > 0 else "bearish"
            rationale.append(f"Technical indicators show {direction} bias")
        
        # Regime rationale
        if regime.get('bullish'):
            rationale.append(f"Market regime is bullish with ADX {regime.get('adx', 0):.1f}")
        elif regime.get('bearish'):
            rationale.append(f"Market regime is bearish with ADX {regime.get('adx', 0):.1f}")
        else:
            rationale.append("Market regime is neutral - consolidation phase")
        
        # Sentiment rationale
        if sentiment and abs(sent_score) > 0.1:
            trend = sentiment.get('trend', 'neutral')
            rationale.append(f"Sentiment analysis suggests {trend} market mood")
        
        # Volume/volatility
        if technical.get('volume_above_avg'):
            rationale.append("Above-average volume confirms price action")
        
        if not rationale:
            rationale.append("Mixed signals - no clear directional bias")
        
        return rationale
    
    def _identify_risks(
        self,
        technical: Dict[str, Any],
        regime: Dict[str, Any],
        sentiment: Optional[Dict[str, Any]]
    ) -> List[str]:
        """Identify key risks."""
        risks = []
        
        # Regime risks
        if regime.get('neutral'):
            risks.append("Neutral regime increases risk of false signals")
        
        # Volatility risks
        if technical.get('atr_status') == 'extreme':
            risks.append("Extreme volatility may lead to wider stops and slippage")
        
        # Volume risks
        if not technical.get('volume_above_avg'):
            risks.append("Below-average volume may indicate weak conviction")
        
        # Sentiment risks
        if sentiment:
            if abs(sentiment.get('score', 0)) > 0.7:
                risks.append("Extreme sentiment may indicate overcrowded positioning")
        
        if not risks:
            risks.append("Standard market risks apply")
        
        return risks
    
    def _suggest_action(self, bias: str, confidence: float) -> str:
        """
        Suggest action based on bias and confidence.
        
        NOTE: This is ADVISORY ONLY - no orders are placed.
        
        Args:
            bias: Market bias
            confidence: Confidence level
            
        Returns:
            Suggested action string
        """
        if confidence < 0.3:
            return "watch"
        elif confidence < 0.6:
            if bias == "bullish":
                return "consider_long"
            elif bias == "bearish":
                return "consider_short"
            else:
                return "watch"
        else:  # High confidence
            if bias == "bullish":
                return "consider_long"
            elif bias == "bearish":
                return "consider_short"
            else:
                return "avoid"
    
    def verify_advisory_only(self) -> bool:
        """
        Verify that this advisor is in advisory-only mode.
        
        Returns:
            True if advisory-only, raises exception otherwise
        """
        if not ADVISORY_ONLY:
            raise RuntimeError("SECURITY VIOLATION: AI Advisor must be advisory only")
        return True
