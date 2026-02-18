"""
Strategy registry for mapping pairs to strategy classes.
"""
from typing import Dict, List, Optional, Type
import logging

logger = logging.getLogger(__name__)

# Strategy registry: Maps pair symbols to strategy class names
STRATEGY_REGISTRY: Dict[str, str] = {
    "BTC/USDT:USDT": "BTCScalpStrategy",
    "ETH/USDT:USDT": "ETHScalpStrategy",
    "SOL/USDT:USDT": "SOLMomentumStrategy",
}


def get_strategy_for_pair(pair: str) -> Optional[str]:
    """
    Get strategy class name for a given pair.
    
    Args:
        pair: Trading pair symbol (e.g., "BTC/USDT:USDT")
        
    Returns:
        Strategy class name or None if not found
    """
    strategy = STRATEGY_REGISTRY.get(pair)
    if strategy is None:
        logger.warning(f"No strategy registered for pair: {pair}")
    return strategy


def list_enabled_pairs() -> List[str]:
    """
    Get list of all enabled trading pairs.
    
    Returns:
        List of pair symbols
    """
    return list(STRATEGY_REGISTRY.keys())


def register_strategy(pair: str, strategy_name: str) -> None:
    """
    Register a strategy for a specific pair.
    
    Args:
        pair: Trading pair symbol
        strategy_name: Name of the strategy class
    """
    logger.info(f"Registering strategy '{strategy_name}' for pair '{pair}'")
    STRATEGY_REGISTRY[pair] = strategy_name


def unregister_strategy(pair: str) -> bool:
    """
    Unregister a strategy for a specific pair.
    
    Args:
        pair: Trading pair symbol
        
    Returns:
        True if strategy was unregistered, False if pair was not found
    """
    if pair in STRATEGY_REGISTRY:
        strategy = STRATEGY_REGISTRY.pop(pair)
        logger.info(f"Unregistered strategy '{strategy}' for pair '{pair}'")
        return True
    else:
        logger.warning(f"Cannot unregister: No strategy found for pair '{pair}'")
        return False


def get_registry() -> Dict[str, str]:
    """
    Get complete strategy registry.
    
    Returns:
        Dictionary mapping pairs to strategy names
    """
    return STRATEGY_REGISTRY.copy()
