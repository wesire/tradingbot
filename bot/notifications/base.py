"""
Abstract base class for all notification channels.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, Optional


class Severity(str, Enum):
    """Alert severity levels."""

    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class BaseNotifier(ABC):
    """
    Abstract interface that every notification channel must implement.

    All implementations should be thread-safe and handle their own
    error recovery internally (never let a notification failure bubble
    up into the trading loop).
    """

    @abstractmethod
    def send_alert(
        self,
        title: str,
        message: str,
        severity: Severity = Severity.INFO,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Send an alert through this channel.

        Parameters
        ----------
        title:
            Short summary shown as the alert title.
        message:
            Full alert body.
        severity:
            One of ``Severity.INFO``, ``Severity.WARNING``,
            ``Severity.CRITICAL``.
        metadata:
            Optional extra data attached to the alert
            (e.g. trade details, pair, P&L).

        Returns
        -------
        bool
            ``True`` if the alert was delivered successfully.
        """

    def is_available(self) -> bool:
        """
        Return ``True`` if the channel is properly configured.

        Implementations should override this to perform a lightweight
        configuration check (e.g. env vars present).
        """
        return True
