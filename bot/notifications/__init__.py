"""
Notifications module for the trading bot.

Provides multi-channel alert delivery (Telegram, …) with
severity-based routing, duplicate throttling, and a queue-based
sending layer that does not block the main trading loop.
"""
from .base import BaseNotifier, Severity
from .telegram_notifier import TelegramNotifier
from .notification_manager import NotificationManager

__all__ = [
    "BaseNotifier",
    "Severity",
    "TelegramNotifier",
    "NotificationManager",
]
