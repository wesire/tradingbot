"""
Telegram notification channel.

Sends formatted Markdown messages to a configured Telegram chat using
the Bot API (plain ``requests`` – no heavy library required).
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, Optional

import requests

from .base import BaseNotifier, Severity

logger = logging.getLogger(__name__)

# Telegram hard-limit: 30 messages / second.  We stay well below it.
_TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}/sendMessage"
_MIN_SEND_INTERVAL = 1.0 / 20  # 20 messages/s


class TelegramNotifier(BaseNotifier):
    """
    Sends alerts to a Telegram chat.

    Configuration via environment variables:
    - ``TELEGRAM_BOT_TOKEN`` – your bot token from @BotFather.
    - ``TELEGRAM_CHAT_ID``   – the target chat / channel ID.

    Parameters
    ----------
    token:
        Bot token.  Defaults to ``TELEGRAM_BOT_TOKEN`` env var.
    chat_id:
        Target chat ID.  Defaults to ``TELEGRAM_CHAT_ID`` env var.
    timeout:
        HTTP request timeout in seconds.
    """

    # Emoji prefixes keyed by severity
    _SEVERITY_PREFIX: Dict[str, str] = {
        Severity.INFO: "ℹ️",
        Severity.WARNING: "⚠️",
        Severity.CRITICAL: "🔴",
    }

    def __init__(
        self,
        token: Optional[str] = None,
        chat_id: Optional[str] = None,
        timeout: float = 10.0,
    ) -> None:
        self._token = token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self._chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID", "")
        self._timeout = timeout
        self._last_send: float = 0.0

    # ------------------------------------------------------------------
    # BaseNotifier implementation
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        return bool(self._token and self._chat_id)

    def send_alert(
        self,
        title: str,
        message: str,
        severity: Severity = Severity.INFO,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Send a formatted alert message to the configured chat."""
        if not self.is_available():
            logger.debug("TelegramNotifier: not configured, skipping alert")
            return False

        text = self._format_message(title, message, severity, metadata)
        return self._send(text)

    # ------------------------------------------------------------------
    # Trade-specific formatters
    # ------------------------------------------------------------------

    def send_trade_executed(
        self,
        pair: str,
        side: str,
        price: float,
        amount: float,
        pnl: Optional[float] = None,
    ) -> bool:
        """Send a trade execution alert with appropriate emoji."""
        emoji = "📈" if side.lower() == "long" else "📉"
        title = f"{emoji} Trade Executed – {pair}"
        lines = [
            f"Side: *{side.upper()}*",
            f"Price: `{price:.4f}`",
            f"Amount: `{amount}`",
        ]
        if pnl is not None:
            pnl_emoji = "💰" if pnl >= 0 else "🔻"
            lines.append(f"P&L: {pnl_emoji} `{pnl:+.2f} USDT`")
        return self.send_alert(title, "\n".join(lines), Severity.INFO)

    def send_daily_pnl(self, pnl: float, win_rate: float, trades: int) -> bool:
        """Send daily P&L summary."""
        emoji = "💰" if pnl >= 0 else "📉"
        title = f"{emoji} Daily P&L Summary"
        message = (
            f"P&L: `{pnl:+.2f} USDT`\n"
            f"Win Rate: `{win_rate:.1%}`\n"
            f"Trades: `{trades}`"
        )
        return self.send_alert(title, message, Severity.INFO)

    def send_risk_triggered(self, reason: str, details: str) -> bool:
        """Send risk-engine-triggered alert."""
        return self.send_alert(
            f"⚠️ Risk Engine Triggered",
            f"*Reason*: {reason}\n{details}",
            Severity.WARNING,
        )

    def send_sentiment_spike(self, pair: str, score: float, trend: str) -> bool:
        """Send sentiment spike alert."""
        return self.send_alert(
            f"📊 Sentiment Spike – {pair}",
            f"Score: `{score:.2f}`\nTrend: *{trend}*",
            Severity.INFO,
        )

    def send_high_confidence_opportunity(
        self, pair: str, side: str, confidence: float, ml_signal: Optional[str] = None
    ) -> bool:
        """Send high-confidence opportunity alert."""
        msg = f"Side: *{side.upper()}*\nConfidence: `{confidence:.1%}`"
        if ml_signal:
            msg += f"\nML Signal: *{ml_signal}*"
        return self.send_alert(f"🎯 High-Confidence Opportunity – {pair}", msg, Severity.INFO)

    def send_system_health(self, issue: str, details: str) -> bool:
        """Send system health issue alert."""
        return self.send_alert(
            f"🔴 System Health Issue",
            f"*Issue*: {issue}\n{details}",
            Severity.CRITICAL,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _format_message(
        self,
        title: str,
        message: str,
        severity: Severity,
        metadata: Optional[Dict[str, Any]],
    ) -> str:
        prefix = self._SEVERITY_PREFIX.get(severity, "")
        parts = [f"{prefix} *{title}*", "", message]
        if metadata:
            meta_lines = [f"_{k}_: `{v}`" for k, v in metadata.items()]
            parts += ["", *meta_lines]
        return "\n".join(parts)

    def _send(self, text: str) -> bool:
        """Dispatch a Telegram sendMessage request with rate limiting."""
        # Simple rate limiter
        now = time.monotonic()
        elapsed = now - self._last_send
        if elapsed < _MIN_SEND_INTERVAL:
            time.sleep(_MIN_SEND_INTERVAL - elapsed)

        url = _TELEGRAM_API_BASE.format(token=self._token)
        payload = {
            "chat_id": self._chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }
        try:
            resp = requests.post(url, json=payload, timeout=self._timeout)
            resp.raise_for_status()
            self._last_send = time.monotonic()
            return True
        except requests.RequestException as exc:
            logger.error("TelegramNotifier: send failed: %s", exc)
            return False
