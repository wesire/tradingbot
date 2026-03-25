"""
Notification manager – multi-channel routing with throttling.

Routes alerts to one or more notifiers based on severity, prevents
duplicate alerts within a configurable window, and uses a background
queue so that sending never blocks the main trading loop.
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .base import BaseNotifier, Severity

logger = logging.getLogger(__name__)


class NotificationManager:
    """
    Manages alert delivery across multiple notification channels.

    Parameters
    ----------
    throttle_minutes:
        Suppress duplicate ``(title, severity)`` combinations within
        this many minutes.
    queue_size:
        Maximum number of enqueued alerts before blocking.
    """

    def __init__(
        self,
        throttle_minutes: float = 5.0,
        queue_size: int = 256,
    ) -> None:
        self._notifiers: Dict[str, BaseNotifier] = {}
        self._throttle_seconds = throttle_minutes * 60.0
        self._sent_cache: Dict[Tuple[str, str], float] = {}  # (title, sev) → timestamp
        self._queue: queue.Queue[Optional[Dict[str, Any]]] = queue.Queue(
            maxsize=queue_size
        )
        self._worker = threading.Thread(
            target=self._worker_loop, daemon=True, name="NotificationManager"
        )
        self._running = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background worker thread."""
        if not self._running:
            self._running = True
            self._worker.start()
            logger.info("NotificationManager started")

    def stop(self, timeout: float = 5.0) -> None:
        """Gracefully drain the queue and stop the worker thread."""
        self._running = False
        self._queue.put(None)  # Sentinel
        self._worker.join(timeout=timeout)
        logger.info("NotificationManager stopped")

    # ------------------------------------------------------------------
    # Channel management
    # ------------------------------------------------------------------

    def add_notifier(self, name: str, notifier: BaseNotifier) -> None:
        """Register a notification channel."""
        self._notifiers[name] = notifier
        logger.info("NotificationManager: registered channel '%s'", name)

    def remove_notifier(self, name: str) -> None:
        """Remove a registered channel."""
        self._notifiers.pop(name, None)

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------

    def send_alert(
        self,
        title: str,
        message: str,
        severity: Severity = Severity.INFO,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Enqueue an alert for delivery (non-blocking).

        The alert is silently dropped if a duplicate was sent within the
        throttle window.
        """
        if self._is_throttled(title, severity):
            logger.debug(
                "NotificationManager: throttled duplicate alert '%s' [%s]",
                title,
                severity,
            )
            return

        item: Dict[str, Any] = {
            "title": title,
            "message": message,
            "severity": severity,
            "metadata": metadata,
            "enqueued_at": time.monotonic(),
        }
        try:
            self._queue.put_nowait(item)
        except queue.Full:
            logger.warning(
                "NotificationManager: queue full, dropping alert '%s'", title
            )

    def send_alert_sync(
        self,
        title: str,
        message: str,
        severity: Severity = Severity.INFO,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, bool]:
        """
        Send an alert *synchronously* and return per-channel results.

        Useful for testing or when you need immediate delivery confirmation.
        """
        if self._is_throttled(title, severity):
            return {}

        return self._dispatch(title, message, severity, metadata)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _worker_loop(self) -> None:
        """Background thread: drain the queue and dispatch alerts."""
        while self._running:
            try:
                item = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue

            if item is None:
                break  # Sentinel received

            self._dispatch(
                item["title"],
                item["message"],
                item["severity"],
                item.get("metadata"),
            )
            self._queue.task_done()

    def _dispatch(
        self,
        title: str,
        message: str,
        severity: Severity,
        metadata: Optional[Dict[str, Any]],
    ) -> Dict[str, bool]:
        """Send ``title``/``message`` to all eligible channels."""
        results: Dict[str, bool] = {}
        channels = self._select_channels(severity)

        for name in channels:
            notifier = self._notifiers.get(name)
            if notifier is None or not notifier.is_available():
                continue
            try:
                ok = notifier.send_alert(title, message, severity, metadata)
                results[name] = ok
            except Exception as exc:
                logger.error(
                    "NotificationManager: channel '%s' raised %s", name, exc
                )
                results[name] = False

        # Record in throttle cache (even on failure to avoid storm)
        self._mark_sent(title, severity)
        return results

    def _select_channels(self, severity: Severity) -> List[str]:
        """
        Return channel names to use for the given severity.

        Routing rules:
        - INFO     → all channels
        - WARNING  → all channels
        - CRITICAL → all channels
        (Extend here for fine-grained routing, e.g. SMS-only for CRITICAL.)
        """
        return list(self._notifiers.keys())

    def _is_throttled(self, title: str, severity: Severity) -> bool:
        key = (title, str(severity))
        last = self._sent_cache.get(key, 0.0)
        return (time.monotonic() - last) < self._throttle_seconds

    def _mark_sent(self, title: str, severity: Severity) -> None:
        self._sent_cache[(title, str(severity))] = time.monotonic()
        # Prune old entries to avoid unbounded growth
        cutoff = time.monotonic() - self._throttle_seconds
        self._sent_cache = {
            k: v for k, v in self._sent_cache.items() if v > cutoff
        }
