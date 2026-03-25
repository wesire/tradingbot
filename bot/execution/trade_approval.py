"""
Trade approval workflow.

When enabled, trades are held in a pending queue instead of executing
immediately.  Each pending trade can be manually approved or rejected (e.g.
via a Telegram inline keyboard).  If no action is taken within the configured
timeout, the queue auto-approves or auto-rejects the trade according to the
``auto_action`` setting.

Configuration (YAML)::

    trade_approval:
      enabled: false
      timeout_seconds: 300
      auto_action: "approve"   # approve | reject | none
      notify_channels: ["telegram"]
"""
import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enumerations / data containers
# ---------------------------------------------------------------------------

class TradeStatus(str, Enum):
    """Lifecycle status of a trade in the approval queue."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    EXECUTED = "executed"


@dataclass
class PendingTrade:
    """A trade that is waiting for approval."""

    trade_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    symbol: str = ""
    side: str = ""          # "buy" or "sell"
    amount: float = 0.0
    price: Optional[float] = None
    strategy: str = ""
    signal_confidence: float = 0.0
    extra: Dict[str, Any] = field(default_factory=dict)
    status: TradeStatus = TradeStatus.PENDING
    submitted_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    decided_at: Optional[datetime] = None
    decision_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "side": self.side,
            "amount": self.amount,
            "price": self.price,
            "strategy": self.strategy,
            "signal_confidence": self.signal_confidence,
            "status": self.status.value,
            "submitted_at": self.submitted_at.isoformat(),
            "decided_at": self.decided_at.isoformat() if self.decided_at else None,
            "decision_reason": self.decision_reason,
        }


# ---------------------------------------------------------------------------
# TradeApprovalQueue
# ---------------------------------------------------------------------------

class TradeApprovalQueue:
    """
    Holds trades pending manual approval before execution.

    When :attr:`enabled` is ``False``, :meth:`submit_trade` immediately
    executes the trade by calling *execute_fn* (pass-through mode).

    Args:
        enabled: When ``False``, all trades are executed immediately without
            queuing (default ``False``).
        timeout_seconds: Seconds to wait for a decision before auto-action
            fires (default 300 = 5 min).
        auto_action: Action taken on timeout — ``"approve"``, ``"reject"``,
            or ``"none"`` (wait indefinitely) (default ``"approve"``).
        execute_fn: Callable invoked when a trade is approved.  Receives
            :class:`PendingTrade` as its only argument.
        notify_fn: Optional callable invoked when a new trade is submitted.
            Receives :class:`PendingTrade` as its only argument.
    """

    def __init__(
        self,
        enabled: bool = False,
        timeout_seconds: int = 300,
        auto_action: str = "approve",
        execute_fn: Optional[Callable[[PendingTrade], None]] = None,
        notify_fn: Optional[Callable[[PendingTrade], None]] = None,
    ) -> None:
        if auto_action not in ("approve", "reject", "none"):
            raise ValueError(
                f"auto_action must be 'approve', 'reject', or 'none', "
                f"got {auto_action!r}"
            )
        self.enabled = enabled
        self.timeout_seconds = timeout_seconds
        self.auto_action = auto_action
        self._execute_fn = execute_fn
        self._notify_fn = notify_fn
        self._queue: Dict[str, PendingTrade] = {}
        self._lock = threading.Lock()
        self._timers: Dict[str, threading.Timer] = {}
        logger.info(
            "TradeApprovalQueue initialised "
            "(enabled=%s, timeout=%ds, auto_action=%s)",
            enabled,
            timeout_seconds,
            auto_action,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def submit_trade(self, trade: PendingTrade) -> str:
        """
        Submit a trade for approval (or execute immediately if not enabled).

        Args:
            trade: :class:`PendingTrade` describing the trade to submit.

        Returns:
            The ``trade_id`` assigned to this trade.
        """
        if not self.enabled:
            logger.info(
                "TradeApprovalQueue: pass-through mode — executing %s %s %s",
                trade.trade_id,
                trade.side,
                trade.symbol,
            )
            trade.status = TradeStatus.APPROVED
            trade.decided_at = datetime.now(timezone.utc)
            trade.decision_reason = "pass-through (approval disabled)"
            self._execute(trade)
            return trade.trade_id

        with self._lock:
            self._queue[trade.trade_id] = trade

        logger.info(
            "TradeApprovalQueue: queued %s — %s %s %.6f @ %s (timeout=%ds)",
            trade.trade_id,
            trade.side,
            trade.symbol,
            trade.amount,
            trade.price,
            self.timeout_seconds,
        )

        # Send notification
        if self._notify_fn:
            try:
                self._notify_fn(trade)
            except Exception as exc:
                logger.error(
                    "TradeApprovalQueue: notification failed: %s", exc
                )

        # Arm timeout
        if self.auto_action != "none" and self.timeout_seconds > 0:
            timer = threading.Timer(
                self.timeout_seconds,
                self._on_timeout,
                args=(trade.trade_id,),
            )
            timer.daemon = True
            timer.start()
            with self._lock:
                self._timers[trade.trade_id] = timer

        return trade.trade_id

    def approve_trade(self, trade_id: str) -> bool:
        """
        Approve and execute a pending trade.

        Args:
            trade_id: ID of the trade to approve.

        Returns:
            ``True`` if the trade was found and approved, ``False`` otherwise.
        """
        return self._decide(trade_id, TradeStatus.APPROVED, "manual approval")

    def reject_trade(self, trade_id: str, reason: str = "manual rejection") -> bool:
        """
        Reject and discard a pending trade.

        Args:
            trade_id: ID of the trade to reject.
            reason: Human-readable rejection reason (logged).

        Returns:
            ``True`` if the trade was found and rejected, ``False`` otherwise.
        """
        return self._decide(trade_id, TradeStatus.REJECTED, reason)

    def get_pending_trades(self) -> List[PendingTrade]:
        """Return all trades currently in PENDING status."""
        with self._lock:
            return [
                t for t in self._queue.values()
                if t.status == TradeStatus.PENDING
            ]

    def get_trade(self, trade_id: str) -> Optional[PendingTrade]:
        """Return a trade by ID (any status), or ``None`` if not found."""
        with self._lock:
            return self._queue.get(trade_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _decide(
        self, trade_id: str, status: TradeStatus, reason: str
    ) -> bool:
        """Apply a decision to a pending trade."""
        with self._lock:
            trade = self._queue.get(trade_id)
            if trade is None:
                logger.warning(
                    "TradeApprovalQueue: trade %s not found", trade_id
                )
                return False
            if trade.status != TradeStatus.PENDING:
                logger.warning(
                    "TradeApprovalQueue: trade %s already decided (%s)",
                    trade_id,
                    trade.status.value,
                )
                return False
            trade.status = status
            trade.decided_at = datetime.now(timezone.utc)
            trade.decision_reason = reason

            # Cancel timer if still running
            timer = self._timers.pop(trade_id, None)

        if timer is not None:
            timer.cancel()

        logger.info(
            "TradeApprovalQueue: trade %s → %s (%s)",
            trade_id,
            status.value,
            reason,
        )

        if status == TradeStatus.APPROVED:
            self._execute(trade)

        return True

    def _execute(self, trade: PendingTrade) -> None:
        """Call the execute function and update trade status."""
        if self._execute_fn is None:
            logger.debug(
                "TradeApprovalQueue: no execute_fn — skipping execution of %s",
                trade.trade_id,
            )
            return
        try:
            self._execute_fn(trade)
            with self._lock:
                trade.status = TradeStatus.EXECUTED
            logger.info(
                "TradeApprovalQueue: trade %s executed successfully",
                trade.trade_id,
            )
        except Exception as exc:
            logger.error(
                "TradeApprovalQueue: execution of %s failed: %s",
                trade.trade_id,
                exc,
            )

    def _on_timeout(self, trade_id: str) -> None:
        """Callback fired when the approval timeout expires."""
        logger.info(
            "TradeApprovalQueue: timeout for trade %s — auto_action=%s",
            trade_id,
            self.auto_action,
        )
        if self.auto_action == "approve":
            self._decide(trade_id, TradeStatus.APPROVED, "auto-approved on timeout")
        elif self.auto_action == "reject":
            self._decide(trade_id, TradeStatus.REJECTED, "auto-rejected on timeout")
        else:
            logger.debug(
                "TradeApprovalQueue: auto_action=none — leaving %s pending",
                trade_id,
            )
