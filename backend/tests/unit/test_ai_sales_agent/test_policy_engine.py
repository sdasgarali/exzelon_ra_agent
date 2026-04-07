"""Tests for the deterministic Policy Engine."""
import pytest

pytestmark = pytest.mark.unit


class TestDefaultPolicies:
    def test_default_policies_exist(self):
        from app.services.ai_sales_agent.policy_engine import DEFAULT_POLICIES
        assert "max_emails_per_contact_per_day" in DEFAULT_POLICIES
        assert "min_confidence_auto_reply" in DEFAULT_POLICIES
        assert "min_confidence_auto_send" in DEFAULT_POLICIES
        assert "block_weekends" in DEFAULT_POLICIES
        assert "max_contacts_per_company" in DEFAULT_POLICIES

    def test_default_auto_reply_threshold_is_70(self):
        from app.services.ai_sales_agent.policy_engine import DEFAULT_POLICIES
        assert DEFAULT_POLICIES["min_confidence_auto_reply"] == 70


class TestEvaluateSendPolicy:
    def test_blocks_invalid_email(self):
        from app.services.ai_sales_agent.policy_engine import evaluate_send_policy
        ctx = {
            "contact": {"validation_status": "Invalid", "outreach_status": "ACTIVE"},
            "history": {"emails_sent": 0},
        }
        result = evaluate_send_policy(ctx)
        assert result["allowed"] is False
        assert "INVALID_EMAIL" in result["reason_codes"]

    def test_blocks_unsubscribed_contact(self):
        from app.services.ai_sales_agent.policy_engine import evaluate_send_policy
        ctx = {
            "contact": {"validation_status": "Valid", "outreach_status": "UNSUBSCRIBED"},
            "history": {"emails_sent": 0},
        }
        result = evaluate_send_policy(ctx)
        assert result["allowed"] is False
        assert "UNSUBSCRIBED" in result["reason_codes"]

    def test_blocks_inactive_contact(self):
        from app.services.ai_sales_agent.policy_engine import evaluate_send_policy
        ctx = {
            "contact": {"validation_status": "Valid", "outreach_status": "INACTIVE"},
            "history": {"emails_sent": 0},
        }
        result = evaluate_send_policy(ctx)
        assert result["allowed"] is False
        assert "INACTIVE_CONTACT" in result["reason_codes"]

    def test_allows_valid_active_contact(self):
        from app.services.ai_sales_agent.policy_engine import evaluate_send_policy
        ctx = {
            "contact": {"validation_status": "Valid", "outreach_status": "ACTIVE"},
            "history": {"emails_sent": 0, "emails_replied": 0},
        }
        result = evaluate_send_policy(ctx)
        assert result["allowed"] is True
        assert len(result["reason_codes"]) == 0

    def test_blocks_negative_reply_history(self):
        from app.services.ai_sales_agent.policy_engine import evaluate_send_policy
        ctx = {
            "contact": {"validation_status": "Valid", "outreach_status": "ACTIVE"},
            "history": {"emails_sent": 3, "emails_replied": 1, "last_reply_intent": "not_interested"},
        }
        result = evaluate_send_policy(ctx)
        assert result["allowed"] is False
        assert "NEGATIVE_REPLY" in result["reason_codes"]

    def test_allows_catchall_email(self):
        from app.services.ai_sales_agent.policy_engine import evaluate_send_policy
        ctx = {
            "contact": {"validation_status": "Catch-all", "outreach_status": "ACTIVE"},
            "history": {"emails_sent": 0, "emails_replied": 0},
        }
        result = evaluate_send_policy(ctx)
        assert result["allowed"] is True

    def test_custom_policies_override_defaults(self):
        from app.services.ai_sales_agent.policy_engine import evaluate_send_policy
        ctx = {
            "contact": {"validation_status": "Unknown", "outreach_status": "ACTIVE"},
            "history": {"emails_sent": 0},
        }
        # Default requires valid, this should block
        result = evaluate_send_policy(ctx)
        assert result["allowed"] is False
        # Override to not require valid
        result2 = evaluate_send_policy(ctx, policies={"require_valid_email": False})
        assert result2["allowed"] is True


class TestEvaluateReplyPolicy:
    def test_gates_low_confidence(self):
        from app.services.ai_sales_agent.policy_engine import evaluate_reply_policy
        result = evaluate_reply_policy(intent="interested", confidence=40)
        assert result["auto_send_allowed"] is False
        assert "LOW_CONFIDENCE" in result["reason_codes"]

    def test_allows_high_confidence_interested(self):
        from app.services.ai_sales_agent.policy_engine import evaluate_reply_policy
        result = evaluate_reply_policy(intent="interested", confidence=85)
        assert result["auto_send_allowed"] is True

    def test_always_gates_unsubscribe_intent(self):
        from app.services.ai_sales_agent.policy_engine import evaluate_reply_policy
        result = evaluate_reply_policy(intent="unsubscribe", confidence=95)
        assert result["auto_send_allowed"] is False
        assert "DESTRUCTIVE_ACTION" in result["reason_codes"]

    def test_always_gates_do_not_contact(self):
        from app.services.ai_sales_agent.policy_engine import evaluate_reply_policy
        result = evaluate_reply_policy(intent="do_not_contact", confidence=95)
        assert result["auto_send_allowed"] is False
        assert "DESTRUCTIVE_ACTION" in result["reason_codes"]

    def test_custom_threshold_override(self):
        from app.services.ai_sales_agent.policy_engine import evaluate_reply_policy
        result = evaluate_reply_policy(
            intent="interested", confidence=55,
            policies={"min_confidence_auto_reply": 50}
        )
        assert result["auto_send_allowed"] is True


class TestEvaluateContentPolicy:
    def test_blocks_high_spam(self):
        from app.services.ai_sales_agent.policy_engine import evaluate_content_policy
        result = evaluate_content_policy(spam_score=60)
        assert result["allowed"] is False
        assert "HIGH_SPAM_SCORE" in result["reason_codes"]

    def test_blocks_similar_content(self):
        from app.services.ai_sales_agent.policy_engine import evaluate_content_policy
        result = evaluate_content_policy(similarity_score=0.95)
        assert result["allowed"] is False
        assert "CONTENT_TOO_SIMILAR" in result["reason_codes"]

    def test_warns_long_email(self):
        from app.services.ai_sales_agent.policy_engine import evaluate_content_policy
        result = evaluate_content_policy(word_count=300)
        assert result["allowed"] is True  # warnings don't block
        assert "EMAIL_TOO_LONG" in result["warnings"]

    def test_allows_clean_content(self):
        from app.services.ai_sales_agent.policy_engine import evaluate_content_policy
        result = evaluate_content_policy(spam_score=10, similarity_score=0.3, word_count=80)
        assert result["allowed"] is True
