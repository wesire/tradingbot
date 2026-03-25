"""
Unit tests for TradeApprovalQueue.
"""
import time
import pytest
from unittest.mock import MagicMock

from bot.execution.trade_approval import (
    TradeApprovalQueue,
    PendingTrade,
    TradeStatus,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _trade(**kwargs) -> PendingTrade:
    defaults = {
        "symbol": "BTC/USDT:USDT",
        "side": "buy",
        "amount": 0.01,
        "price": 50000.0,
        "strategy": "btc_scalp",
        "signal_confidence": 0.85,
    }
    defaults.update(kwargs)
    return PendingTrade(**defaults)


# ===========================================================================
# TradeApprovalQueue tests
# ===========================================================================

class TestTradeApprovalQueue:

    # -----------------------------------------------------------------------
    # Pass-through (disabled) mode
    # -----------------------------------------------------------------------

    def test_disabled_executes_immediately(self):
        execute_fn = MagicMock()
        queue = TradeApprovalQueue(enabled=False, execute_fn=execute_fn)
        trade = _trade()
        queue.submit_trade(trade)
        execute_fn.assert_called_once_with(trade)

    def test_disabled_sets_approved_status(self):
        queue = TradeApprovalQueue(enabled=False)
        trade = _trade()
        queue.submit_trade(trade)
        assert trade.status == TradeStatus.APPROVED

    def test_disabled_no_pending_queue(self):
        queue = TradeApprovalQueue(enabled=False)
        queue.submit_trade(_trade())
        assert queue.get_pending_trades() == []

    # -----------------------------------------------------------------------
    # Submit
    # -----------------------------------------------------------------------

    def test_submit_adds_to_pending(self):
        queue = TradeApprovalQueue(enabled=True, auto_action="none")
        trade = _trade()
        queue.submit_trade(trade)
        pending = queue.get_pending_trades()
        assert len(pending) == 1
        assert pending[0].trade_id == trade.trade_id

    def test_submit_returns_trade_id(self):
        queue = TradeApprovalQueue(enabled=True, auto_action="none")
        trade = _trade()
        returned_id = queue.submit_trade(trade)
        assert returned_id == trade.trade_id

    def test_submit_sends_notification(self):
        notify_fn = MagicMock()
        queue = TradeApprovalQueue(
            enabled=True, auto_action="none", notify_fn=notify_fn
        )
        trade = _trade()
        queue.submit_trade(trade)
        notify_fn.assert_called_once_with(trade)

    def test_submit_notify_error_does_not_raise(self):
        """Notification failure is logged but does not crash submit."""
        notify_fn = MagicMock(side_effect=RuntimeError("telegram error"))
        queue = TradeApprovalQueue(
            enabled=True, auto_action="none", notify_fn=notify_fn
        )
        trade = _trade()
        queue.submit_trade(trade)  # should not raise
        assert trade.status == TradeStatus.PENDING

    # -----------------------------------------------------------------------
    # Approve
    # -----------------------------------------------------------------------

    def test_approve_executes_trade(self):
        execute_fn = MagicMock()
        queue = TradeApprovalQueue(
            enabled=True, auto_action="none", execute_fn=execute_fn
        )
        trade = _trade()
        queue.submit_trade(trade)
        result = queue.approve_trade(trade.trade_id)
        assert result is True
        execute_fn.assert_called_once_with(trade)

    def test_approve_updates_status(self):
        queue = TradeApprovalQueue(enabled=True, auto_action="none")
        trade = _trade()
        queue.submit_trade(trade)
        queue.approve_trade(trade.trade_id)
        fetched = queue.get_trade(trade.trade_id)
        assert fetched.status in (TradeStatus.APPROVED, TradeStatus.EXECUTED)
        assert fetched.decided_at is not None

    def test_approve_removes_from_pending(self):
        queue = TradeApprovalQueue(enabled=True, auto_action="none")
        trade = _trade()
        queue.submit_trade(trade)
        queue.approve_trade(trade.trade_id)
        assert queue.get_pending_trades() == []

    def test_approve_unknown_id_returns_false(self):
        queue = TradeApprovalQueue(enabled=True, auto_action="none")
        result = queue.approve_trade("nonexistent-id")
        assert result is False

    def test_double_approve_returns_false(self):
        queue = TradeApprovalQueue(enabled=True, auto_action="none")
        trade = _trade()
        queue.submit_trade(trade)
        queue.approve_trade(trade.trade_id)
        result = queue.approve_trade(trade.trade_id)
        assert result is False

    # -----------------------------------------------------------------------
    # Reject
    # -----------------------------------------------------------------------

    def test_reject_updates_status(self):
        queue = TradeApprovalQueue(enabled=True, auto_action="none")
        trade = _trade()
        queue.submit_trade(trade)
        result = queue.reject_trade(trade.trade_id, "too risky")
        assert result is True
        fetched = queue.get_trade(trade.trade_id)
        assert fetched.status == TradeStatus.REJECTED
        assert fetched.decision_reason == "too risky"

    def test_reject_does_not_execute(self):
        execute_fn = MagicMock()
        queue = TradeApprovalQueue(
            enabled=True, auto_action="none", execute_fn=execute_fn
        )
        trade = _trade()
        queue.submit_trade(trade)
        queue.reject_trade(trade.trade_id, "rejected")
        execute_fn.assert_not_called()

    def test_reject_removes_from_pending(self):
        queue = TradeApprovalQueue(enabled=True, auto_action="none")
        trade = _trade()
        queue.submit_trade(trade)
        queue.reject_trade(trade.trade_id)
        assert queue.get_pending_trades() == []

    def test_reject_unknown_id_returns_false(self):
        queue = TradeApprovalQueue(enabled=True, auto_action="none")
        result = queue.reject_trade("bad-id")
        assert result is False

    # -----------------------------------------------------------------------
    # Auto-approve timeout
    # -----------------------------------------------------------------------

    def test_auto_approve_on_timeout(self):
        execute_fn = MagicMock()
        queue = TradeApprovalQueue(
            enabled=True,
            timeout_seconds=1,
            auto_action="approve",
            execute_fn=execute_fn,
        )
        trade = _trade()
        queue.submit_trade(trade)
        time.sleep(1.5)
        execute_fn.assert_called_once_with(trade)

    def test_auto_reject_on_timeout(self):
        execute_fn = MagicMock()
        queue = TradeApprovalQueue(
            enabled=True,
            timeout_seconds=1,
            auto_action="reject",
            execute_fn=execute_fn,
        )
        trade = _trade()
        queue.submit_trade(trade)
        time.sleep(1.5)
        execute_fn.assert_not_called()
        fetched = queue.get_trade(trade.trade_id)
        assert fetched.status == TradeStatus.REJECTED

    def test_manual_approval_cancels_timer(self):
        """Approving before timeout should not double-fire."""
        execute_fn = MagicMock()
        queue = TradeApprovalQueue(
            enabled=True,
            timeout_seconds=1,
            auto_action="approve",
            execute_fn=execute_fn,
        )
        trade = _trade()
        queue.submit_trade(trade)
        queue.approve_trade(trade.trade_id)
        time.sleep(1.5)
        # execute_fn should only be called once (by manual approval)
        assert execute_fn.call_count == 1

    # -----------------------------------------------------------------------
    # Multiple trades
    # -----------------------------------------------------------------------

    def test_multiple_pending_trades(self):
        queue = TradeApprovalQueue(enabled=True, auto_action="none")
        trades = [_trade(symbol=f"COIN{i}/USDT") for i in range(3)]
        for t in trades:
            queue.submit_trade(t)
        pending = queue.get_pending_trades()
        assert len(pending) == 3

    def test_get_pending_only_returns_pending(self):
        queue = TradeApprovalQueue(enabled=True, auto_action="none")
        t1, t2, t3 = _trade(), _trade(), _trade()
        queue.submit_trade(t1)
        queue.submit_trade(t2)
        queue.submit_trade(t3)
        queue.approve_trade(t1.trade_id)
        queue.reject_trade(t2.trade_id)
        pending = queue.get_pending_trades()
        assert len(pending) == 1
        assert pending[0].trade_id == t3.trade_id

    # -----------------------------------------------------------------------
    # Invalid configuration
    # -----------------------------------------------------------------------

    def test_invalid_auto_action_raises(self):
        with pytest.raises(ValueError):
            TradeApprovalQueue(auto_action="invalid")

    # -----------------------------------------------------------------------
    # PendingTrade serialisation
    # -----------------------------------------------------------------------

    def test_trade_to_dict(self):
        trade = _trade()
        d = trade.to_dict()
        assert d["symbol"] == trade.symbol
        assert d["status"] == TradeStatus.PENDING.value
        assert "trade_id" in d
        assert "submitted_at" in d
