"""Tests for AI decision audit logger."""
import pytest
from unittest.mock import patch, MagicMock

from app.services.ai_audit_logger import (
    hash_prompt,
    should_gate_action,
    log_ai_decision,
)


pytestmark = pytest.mark.unit


class TestHashPrompt:
    """Test prompt hashing."""

    def test_returns_hex_string(self):
        result = hash_prompt("Test prompt")
        assert isinstance(result, str)
        assert len(result) == 16  # SHA-256[:16]

    def test_deterministic(self):
        h1 = hash_prompt("Same prompt")
        h2 = hash_prompt("Same prompt")
        assert h1 == h2

    def test_different_prompts_different_hashes(self):
        h1 = hash_prompt("Prompt A")
        h2 = hash_prompt("Prompt B")
        assert h1 != h2


class TestShouldGateAction:
    """Test confidence-based action gating."""

    def test_low_confidence_gated(self):
        gated, reason = should_gate_action(30, "send_reply")
        assert gated is True
        assert "30" in reason

    def test_high_confidence_allowed(self):
        gated, reason = should_gate_action(85, "send_reply")
        assert gated is False

    def test_always_gate_types_below_threshold(self):
        for action in ["mark_do_not_contact", "mark_unsubscribed", "send_reply"]:
            gated, reason = should_gate_action(60, action, min_confidence=70)
            assert gated is True

    def test_always_gate_types_above_threshold(self):
        gated, reason = should_gate_action(80, "send_reply", min_confidence=70)
        assert gated is False

    def test_very_low_confidence_always_gated(self):
        gated, reason = should_gate_action(40, "classify_email")
        assert gated is True

    def test_moderate_confidence_normal_action_allowed(self):
        gated, reason = should_gate_action(55, "classify_email")
        assert gated is False


class TestLogAIDecision:
    """Test AI decision logging."""

    @patch("app.services.automation_logger.log_automation_event")
    def test_logs_success(self, mock_log):
        db = MagicMock()
        log_ai_decision(
            db,
            tenant_id=1,
            decision_type="reply_classification",
            confidence=85,
            action_taken="draft_created",
        )
        mock_log.assert_called_once()
        call_args = mock_log.call_args
        assert call_args[1]["event_type"] == "ai_reply_classification"
        assert call_args[1]["status"] == "success"

    @patch("app.services.automation_logger.log_automation_event")
    def test_logs_gated_status(self, mock_log):
        db = MagicMock()
        log_ai_decision(
            db,
            tenant_id=1,
            decision_type="auto_reply",
            confidence=50,
            action_taken="send_reply",
            action_gated=True,
            gate_reason="confidence too low",
        )
        mock_log.assert_called_once()
        call_args = mock_log.call_args
        assert call_args[1]["status"] == "gated"

    @patch("app.services.automation_logger.log_automation_event")
    def test_logs_error_status(self, mock_log):
        db = MagicMock()
        log_ai_decision(
            db,
            tenant_id=1,
            decision_type="content_gen",
            error="API timeout",
        )
        mock_log.assert_called_once()
        call_args = mock_log.call_args
        assert call_args[1]["status"] == "error"

    @patch("app.services.automation_logger.log_automation_event", side_effect=Exception("DB error"))
    def test_never_raises(self, mock_log):
        """Audit logging failures must never break the main flow."""
        db = MagicMock()
        # Should not raise even when log_automation_event fails
        log_ai_decision(
            db,
            tenant_id=1,
            decision_type="test",
        )
