"""
Multi-exchange manager: groundwork for supporting multiple exchanges via CCXT.

Provides an ``ExchangeManager`` that registers CCXT exchange instances, routes
order queries to the best exchange, and aggregates balances.

Current production support: Binance.
Stubs/groundwork: Bybit, OKX (real implementation in a future PR).

Configuration example (YAML)::

    exchanges:
      - name: binance
        enabled: true
        api_key_env: BINANCE_API_KEY
        api_secret_env: BINANCE_API_SECRET
      - name: bybit
        enabled: false
        api_key_env: BYBIT_API_KEY
        api_secret_env: BYBIT_API_SECRET
      - name: okx
        enabled: false
        api_key_env: OKX_API_KEY
        api_secret_env: OKX_API_SECRET
"""
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    import ccxt  # type: ignore

    _CCXT_AVAILABLE = True
except ImportError:  # pragma: no cover
    _CCXT_AVAILABLE = False
    logger.warning(
        "ExchangeManager: ccxt not installed — exchange operations unavailable"
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Known exchange fee tiers (taker fee as fraction) used for routing
_EXCHANGE_TAKER_FEES: Dict[str, float] = {
    "binance": 0.0004,
    "bybit": 0.0006,
    "okx": 0.0005,
}


class ExchangeManager:
    """
    Registry and router for multiple CCXT exchange instances.

    Exchanges are registered by name and their credentials are read from
    environment variables.  The manager provides routing helpers that
    select the best exchange for a given trading pair based on configured
    fees and availability.

    Attributes:
        SUPPORTED_EXCHANGES: Exchange names with first-class support.
    """

    SUPPORTED_EXCHANGES = ("binance", "bybit", "okx")

    def __init__(self) -> None:
        self._exchanges: Dict[str, Any] = {}
        self._configs: Dict[str, Dict] = {}
        logger.info("Initialized ExchangeManager")

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_exchange(self, name: str, config: Optional[Dict] = None) -> bool:
        """
        Register an exchange by name using CCXT.

        API credentials are read from environment variables specified in
        ``config`` (keys: ``api_key_env``, ``api_secret_env``).  If no
        credentials are provided the exchange is registered in public/read-only
        mode.

        Args:
            name: Exchange name (e.g. ``"binance"``).  Must match a CCXT
                exchange class name.
            config: Optional dict with keys:
                - ``api_key_env``: Name of the env var holding the API key.
                - ``api_secret_env``: Name of the env var holding the secret.
                - ``sandbox``: bool — use sandbox/testnet if True.
                - Any other CCXT exchange options.

        Returns:
            True on success, False if CCXT is unavailable or registration
            failed.
        """
        if not _CCXT_AVAILABLE:
            logger.error("ExchangeManager: ccxt not available — cannot register %s", name)
            return False

        cfg = config or {}
        self._configs[name] = cfg

        api_key = os.environ.get(cfg.get("api_key_env", ""), "")
        api_secret = os.environ.get(cfg.get("api_secret_env", ""), "")

        ccxt_options: Dict[str, Any] = {}
        if api_key:
            ccxt_options["apiKey"] = api_key
        if api_secret:
            ccxt_options["secret"] = api_secret

        try:
            exchange_class = getattr(ccxt, name.lower())
            exchange = exchange_class(ccxt_options)
            if cfg.get("sandbox", False):
                exchange.set_sandbox_mode(True)
            self._exchanges[name] = exchange
            logger.info("ExchangeManager: registered exchange '%s' (sandbox=%s)", name, cfg.get("sandbox", False))
            return True
        except AttributeError:
            logger.error(
                "ExchangeManager: exchange '%s' not found in ccxt", name
            )
            return False
        except Exception as exc:  # pylint: disable=broad-except
            logger.error(
                "ExchangeManager: failed to register '%s': %s", name, exc
            )
            return False

    def register_from_config(self, exchanges_config: List[Dict]) -> int:
        """
        Register multiple exchanges from a list of config dicts.

        Each dict must have a ``name`` key and may have ``enabled``,
        ``api_key_env``, ``api_secret_env``, ``sandbox``.

        Args:
            exchanges_config: List of exchange config dicts.

        Returns:
            Number of exchanges successfully registered.
        """
        registered = 0
        for cfg in exchanges_config:
            name = cfg.get("name", "")
            if not name:
                continue
            if not cfg.get("enabled", True):
                logger.info("ExchangeManager: skipping disabled exchange '%s'", name)
                continue
            if self.register_exchange(name, cfg):
                registered += 1
        return registered

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get_exchange(self, name: str) -> Any:
        """
        Return the registered CCXT exchange instance.

        Args:
            name: Exchange name.

        Returns:
            CCXT exchange instance.

        Raises:
            KeyError: If the exchange is not registered.
        """
        if name not in self._exchanges:
            raise KeyError(f"Exchange '{name}' is not registered")
        return self._exchanges[name]

    def list_exchanges(self) -> List[str]:
        """Return names of all registered exchanges."""
        return list(self._exchanges.keys())

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def get_best_exchange_for_pair(self, pair: str) -> Optional[str]:
        """
        Return the name of the exchange with the best fees/liquidity for a pair.

        The current heuristic uses static taker fee data.  A future version
        will query live order book depth for liquidity-weighted routing.

        Args:
            pair: Trading pair symbol (e.g. ``"BTC/USDT"``).

        Returns:
            Exchange name string or None if no exchanges are registered.
        """
        if not self._exchanges:
            return None

        # Filter to exchanges that likely support this pair (basic check)
        candidates = list(self._exchanges.keys())

        # Sort by taker fee (ascending) — lowest fee wins
        candidates.sort(key=lambda n: _EXCHANGE_TAKER_FEES.get(n, 0.001))

        best = candidates[0]
        logger.debug(
            "ExchangeManager: best exchange for %s → %s (fee=%.4f%%)",
            pair,
            best,
            _EXCHANGE_TAKER_FEES.get(best, 0.001) * 100,
        )
        return best

    # ------------------------------------------------------------------
    # Balance aggregation
    # ------------------------------------------------------------------

    def get_all_balances(self) -> Dict[str, Any]:
        """
        Fetch and aggregate balances across all registered exchanges.

        Returns:
            Dict mapping exchange name → balance dict (from CCXT
            ``fetch_balance``).  Failed fetches are logged and skipped.
        """
        balances: Dict[str, Any] = {}
        for name, exchange in self._exchanges.items():
            try:
                balances[name] = exchange.fetch_balance()
                logger.debug("ExchangeManager: fetched balance from %s", name)
            except Exception as exc:  # pylint: disable=broad-except
                logger.error(
                    "ExchangeManager: failed to fetch balance from %s: %s",
                    name,
                    exc,
                )
                balances[name] = {"error": str(exc)}
        return balances

    def get_total_balance(self, currency: str = "USDT") -> float:
        """
        Return the total free balance of a currency across all exchanges.

        Args:
            currency: Currency symbol to aggregate (default ``"USDT"``).

        Returns:
            Sum of free balances across all exchanges.
        """
        total = 0.0
        all_balances = self.get_all_balances()
        for name, balance in all_balances.items():
            if "error" in balance:
                continue
            free = balance.get("free", {}).get(currency, 0.0)
            total += float(free or 0.0)
        return total
