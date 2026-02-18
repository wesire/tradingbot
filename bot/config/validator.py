"""
Configuration validator for trading bot.
Validates pairs, risk parameters, and strategy configs at startup.
"""
import yaml
import logging
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
import re

logger = logging.getLogger(__name__)

# Supported exchanges and their pair formats
EXCHANGE_PAIR_FORMATS = {
    "binance": r"^[A-Z]{3,10}/[A-Z]{3,10}:[A-Z]{3,10}$",
    "bybit": r"^[A-Z]{3,10}/[A-Z]{3,10}:[A-Z]{3,10}$",
    "okx": r"^[A-Z]{3,10}/[A-Z]{3,10}:[A-Z]{3,10}$",
}


class ConfigValidationError(Exception):
    """Raised when configuration validation fails."""
    pass


class ConfigValidator:
    """Validates trading bot configuration."""
    
    def __init__(self, config_dir: str = "config"):
        """
        Initialize validator.
        
        Args:
            config_dir: Path to configuration directory
        """
        self.config_dir = Path(config_dir)
        self.errors: List[str] = []
        self.warnings: List[str] = []
        
    def validate_all(self, exchange: str = "binance") -> Tuple[bool, List[str], List[str]]:
        """
        Validate all configuration files.
        
        Args:
            exchange: Exchange name for pair validation
            
        Returns:
            Tuple of (is_valid, errors, warnings)
        """
        self.errors.clear()
        self.warnings.clear()
        
        # Validate each config file
        self._validate_pairs_config(exchange)
        self._validate_risk_config()
        self._validate_strategy_configs()
        
        is_valid = len(self.errors) == 0
        return is_valid, self.errors, self.warnings
    
    def _load_yaml(self, filename: str) -> Optional[Dict[str, Any]]:
        """
        Load YAML configuration file.
        
        Args:
            filename: Name of the YAML file
            
        Returns:
            Parsed YAML as dictionary or None if file doesn't exist
        """
        filepath = self.config_dir / filename
        if not filepath.exists():
            self.warnings.append(f"Config file not found: {filepath}")
            return None
        
        try:
            with open(filepath, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            self.errors.append(f"Failed to parse {filepath}: {e}")
            return None
    
    def _validate_pairs_config(self, exchange: str) -> None:
        """Validate pairs.yaml configuration."""
        config = self._load_yaml("pairs.yaml")
        if config is None:
            return
        
        # Check for required keys
        if 'pairs' not in config:
            self.errors.append("pairs.yaml: Missing 'pairs' key")
            return
        
        pairs = config.get('pairs', [])
        if not isinstance(pairs, list):
            self.errors.append("pairs.yaml: 'pairs' must be a list")
            return
        
        if len(pairs) == 0:
            self.errors.append("pairs.yaml: No pairs configured")
        
        # Get pair format regex for exchange
        pair_format = EXCHANGE_PAIR_FORMATS.get(exchange.lower())
        if not pair_format:
            self.warnings.append(f"Unknown exchange '{exchange}', skipping pair format validation")
            pair_format = None
        
        enabled_pairs = []
        for i, pair_config in enumerate(pairs):
            self._validate_pair_entry(pair_config, i, pair_format, enabled_pairs)
        
        # Check global settings
        global_config = config.get('global', {})
        self._validate_global_settings(global_config)
    
    def _validate_pair_entry(
        self,
        pair_config: Dict[str, Any],
        index: int,
        pair_format: Optional[str],
        enabled_pairs: List[str]
    ) -> None:
        """Validate individual pair entry."""
        required_keys = ['symbol', 'enabled', 'timeframe', 'leverage_cap', 'stake_allocation', 'strategy']
        
        for key in required_keys:
            if key not in pair_config:
                self.errors.append(f"pairs.yaml: Pair at index {index} missing required key '{key}'")
        
        # Validate symbol format
        symbol = pair_config.get('symbol')
        if symbol and pair_format:
            if not re.match(pair_format, symbol):
                self.errors.append(f"pairs.yaml: Invalid pair symbol format '{symbol}'")
        
        # Check for duplicate enabled pairs
        if pair_config.get('enabled') and symbol:
            if symbol in enabled_pairs:
                self.errors.append(f"pairs.yaml: Duplicate enabled pair '{symbol}'")
            enabled_pairs.append(symbol)
        
        # Validate leverage
        leverage = pair_config.get('leverage_cap')
        if leverage is not None:
            if not isinstance(leverage, (int, float)) or leverage < 1 or leverage > 125:
                self.errors.append(f"pairs.yaml: Invalid leverage_cap {leverage} for {symbol}")
        
        # Validate stake allocation
        stake = pair_config.get('stake_allocation')
        if stake is not None:
            if not isinstance(stake, (int, float)) or stake <= 0 or stake > 1:
                self.errors.append(f"pairs.yaml: Invalid stake_allocation {stake} for {symbol} (must be 0-1)")
        
        # Validate timeframe
        timeframe = pair_config.get('timeframe')
        valid_timeframes = ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '12h', '1d']
        if timeframe and timeframe not in valid_timeframes:
            self.warnings.append(f"pairs.yaml: Unusual timeframe '{timeframe}' for {symbol}")
    
    def _validate_global_settings(self, global_config: Dict[str, Any]) -> None:
        """Validate global pair settings."""
        max_trades = global_config.get('max_open_trades')
        if max_trades is not None:
            if not isinstance(max_trades, int) or max_trades < 1 or max_trades > 20:
                self.errors.append(f"pairs.yaml: Invalid max_open_trades {max_trades} (must be 1-20)")
    
    def _validate_risk_config(self) -> None:
        """Validate risk.yaml configuration."""
        config = self._load_yaml("risk.yaml")
        if config is None:
            return
        
        # Validate position sizing
        position_sizing = config.get('position_sizing', {})
        self._validate_risk_percentage('max_risk_per_trade', position_sizing.get('max_risk_per_trade'))
        self._validate_risk_percentage('max_risk_per_pair', position_sizing.get('max_risk_per_pair'))
        
        # Validate daily limits
        daily_limits = config.get('daily_limits', {})
        self._validate_risk_percentage('max_daily_drawdown', daily_limits.get('max_daily_drawdown'))
        
        max_losses = daily_limits.get('max_consecutive_losses')
        if max_losses is not None:
            if not isinstance(max_losses, int) or max_losses < 1 or max_losses > 10:
                self.errors.append(f"risk.yaml: Invalid max_consecutive_losses {max_losses}")
        
        # Validate stoploss profiles
        profiles = config.get('stoploss', {}).get('profiles', {})
        for profile_name, profile_config in profiles.items():
            self._validate_stoploss_profile(profile_name, profile_config)
    
    def _validate_risk_percentage(self, name: str, value: Any) -> None:
        """Validate a risk percentage parameter."""
        if value is not None:
            if not isinstance(value, (int, float)) or value <= 0 or value > 0.5:
                self.errors.append(f"risk.yaml: Invalid {name} {value} (must be 0-0.5)")
    
    def _validate_stoploss_profile(self, name: str, profile: Dict[str, Any]) -> None:
        """Validate a stoploss profile."""
        required_keys = ['initial_stop_atr_multiplier', 'breakeven_trigger_atr', 
                        'partial_tp_sizes', 'partial_tp_distances']
        
        for key in required_keys:
            if key not in profile:
                self.errors.append(f"risk.yaml: Profile '{name}' missing key '{key}'")
        
        # Validate partial TP sizes sum to ~1.0
        tp_sizes = profile.get('partial_tp_sizes', [])
        if tp_sizes and abs(sum(tp_sizes) - 1.0) > 0.01:
            self.errors.append(f"risk.yaml: Profile '{name}' partial_tp_sizes must sum to 1.0")
    
    def _validate_strategy_configs(self) -> None:
        """Validate strategy configuration files."""
        strategy_dir = self.config_dir / "strategies"
        if not strategy_dir.exists():
            self.warnings.append(f"Strategy config directory not found: {strategy_dir}")
            return
        
        strategy_files = list(strategy_dir.glob("*.yaml"))
        if not strategy_files:
            self.warnings.append("No strategy configuration files found")
        
        for filepath in strategy_files:
            self._validate_strategy_file(filepath)
    
    def _validate_strategy_file(self, filepath: Path) -> None:
        """Validate individual strategy configuration file."""
        try:
            with open(filepath, 'r') as f:
                config = yaml.safe_load(f)
        except Exception as e:
            self.errors.append(f"Failed to parse {filepath.name}: {e}")
            return
        
        if 'strategy' not in config:
            self.errors.append(f"{filepath.name}: Missing 'strategy' section")
            return
        
        strategy = config['strategy']
        required_keys = ['name', 'class_name', 'description']
        for key in required_keys:
            if key not in strategy:
                self.errors.append(f"{filepath.name}: Missing strategy.{key}")


def validate_config_at_startup(
    config_dir: str = "config",
    exchange: str = "binance",
    fail_fast: bool = True
) -> bool:
    """
    Validate configuration at application startup.
    
    Args:
        config_dir: Path to configuration directory
        exchange: Exchange name
        fail_fast: If True, raise exception on validation failure
        
    Returns:
        True if validation passed
        
    Raises:
        ConfigValidationError: If fail_fast=True and validation fails
    """
    validator = ConfigValidator(config_dir)
    is_valid, errors, warnings = validator.validate_all(exchange)
    
    # Log warnings
    for warning in warnings:
        logger.warning(f"Config validation warning: {warning}")
    
    # Log/raise errors
    if not is_valid:
        error_msg = "Configuration validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
        logger.error(error_msg)
        
        if fail_fast:
            raise ConfigValidationError(error_msg)
    else:
        logger.info("Configuration validation passed")
    
    return is_valid
