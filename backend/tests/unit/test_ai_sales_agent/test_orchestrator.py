"""Tests for the Agent Orchestrator."""
import pytest
from unittest.mock import MagicMock, patch

pytestmark = pytest.mark.unit


class TestOrchestrateSend:
    @patch("app.services.ai_sales_agent.orchestrator.build_interaction_history")
    @patch("app.services.ai_sales_agent.orchestrator.build_contact_context")
    @patch("app.services.ai_sales_agent.orchestrator.make_send_decision")
    @patch("app.services.ai_sales_agent.orchestrator.log_ai_decision")
    def test_blocks_when_policy_denies(self, mock_log, mock_decision, mock_ctx, mock_history):
        from app.services.ai_sales_agent.orchestrator import orchestrate_send

        mock_history.return_value = {"emails_sent": 0, "emails_replied": 0}
        mock_ctx.return_value = {
            "contact": {"validation_status": "Invalid", "outreach_status": "ACTIVE"},
            "lead": {}, "company": {}, "history": {}, "scores": {},
        }
        mock_decision.return_value = {
            "should_send": False,
            "reason_codes": ["INVALID_EMAIL"],
            "confidence": 10,
            "composite_score": 0,
            "reasoning": "INVALID_EMAIL",
        }

        contact = MagicMock()
        contact.contact_id = 1
        campaign = MagicMock()
        campaign.campaign_id = 1

        result = orchestrate_send(
            db=MagicMock(), contact=contact, lead=MagicMock(),
            campaign=campaign, tenant_id=1,
        )
        assert result["should_send"] is False
        assert "INVALID_EMAIL" in result["reason_codes"]

    @patch("app.services.ai_sales_agent.orchestrator.build_interaction_history")
    @patch("app.services.ai_sales_agent.orchestrator.build_contact_context")
    @patch("app.services.ai_sales_agent.orchestrator.make_send_decision")
    @patch("app.services.ai_sales_agent.orchestrator.log_ai_decision")
    def test_allows_when_all_checks_pass(self, mock_log, mock_decision, mock_ctx, mock_history):
        from app.services.ai_sales_agent.orchestrator import orchestrate_send

        mock_history.return_value = {"emails_sent": 0, "emails_replied": 0}
        mock_ctx.return_value = {
            "contact": {"validation_status": "Valid", "outreach_status": "ACTIVE"},
            "lead": {"job_title": "Manager"}, "company": {"name": "Acme"},
            "history": {"emails_sent": 0, "emails_replied": 0},
            "scores": {},
        }
        mock_decision.return_value = {
            "should_send": True, "reason_codes": [],
            "confidence": 90, "composite_score": 65,
            "reasoning": "All checks passed",
        }

        contact = MagicMock()
        contact.contact_id = 2
        campaign = MagicMock()
        campaign.campaign_id = 1

        result = orchestrate_send(
            db=MagicMock(), contact=contact, lead=MagicMock(),
            campaign=campaign, tenant_id=1,
        )
        assert result["should_send"] is True


class TestOrchestrateReply:
    @patch("app.services.ai_sales_agent.orchestrator.build_interaction_history")
    @patch("app.services.ai_sales_agent.orchestrator.build_contact_context")
    @patch("app.services.ai_sales_agent.orchestrator.classify_reply")
    @patch("app.services.ai_sales_agent.orchestrator.determine_next_action_rule_based")
    @patch("app.services.ai_sales_agent.orchestrator.evaluate_reply_policy")
    @patch("app.services.ai_sales_agent.orchestrator.log_ai_decision")
    def test_returns_classification(
        self, mock_log, mock_policy, mock_nba, mock_classify, mock_ctx, mock_history,
    ):
        from app.services.ai_sales_agent.orchestrator import orchestrate_reply

        mock_history.return_value = {"emails_sent": 2, "emails_replied": 0}
        mock_ctx.return_value = {
            "contact": {"name": "John"}, "lead": {}, "company": {"name": "Acme"},
            "history": {"emails_sent": 2, "emails_replied": 0},
            "campaign": {},
        }
        mock_classify.return_value = {
            "intent": "interested", "confidence": 85,
            "sentiment": "positive", "recommended_action": "send_reply",
        }
        mock_nba.return_value = {
            "action": "send_reply", "confidence": 85,
            "delay_hours": 0, "requires_human_approval": False,
        }
        mock_policy.return_value = {
            "auto_send_allowed": True, "reason_codes": [],
        }

        contact = MagicMock()
        contact.contact_id = 1
        campaign = MagicMock()
        campaign.campaign_id = 1

        result = orchestrate_reply(
            db=MagicMock(), email_body="Sounds great, let's talk!",
            contact=contact, campaign=campaign, tenant_id=1,
        )
        assert result["intent"] == "interested"
        assert result["confidence"] == 85
        assert result["next_action"]["action"] == "send_reply"
        assert result["policy_result"]["auto_send_allowed"] is True

    @patch("app.services.ai_sales_agent.orchestrator.build_interaction_history")
    @patch("app.services.ai_sales_agent.orchestrator.build_contact_context")
    @patch("app.services.ai_sales_agent.orchestrator.classify_reply")
    @patch("app.services.ai_sales_agent.orchestrator.determine_next_action_rule_based")
    @patch("app.services.ai_sales_agent.orchestrator.evaluate_reply_policy")
    @patch("app.services.ai_sales_agent.orchestrator.log_ai_decision")
    def test_gates_low_confidence_reply(
        self, mock_log, mock_policy, mock_nba, mock_classify, mock_ctx, mock_history,
    ):
        from app.services.ai_sales_agent.orchestrator import orchestrate_reply

        mock_history.return_value = {}
        mock_ctx.return_value = {
            "contact": {"name": "Jane"}, "lead": {}, "company": {},
            "history": {}, "campaign": {},
        }
        mock_classify.return_value = {
            "intent": "interested", "confidence": 35,
            "sentiment": "neutral",
        }
        mock_nba.return_value = {
            "action": "escalate_to_human", "confidence": 35,
            "delay_hours": 0, "requires_human_approval": True,
        }
        mock_policy.return_value = {
            "auto_send_allowed": False, "reason_codes": ["LOW_CONFIDENCE"],
        }

        contact = MagicMock()
        contact.contact_id = 2
        campaign = MagicMock()
        campaign.campaign_id = 1

        result = orchestrate_reply(
            db=MagicMock(), email_body="maybe later",
            contact=contact, campaign=campaign, tenant_id=1,
        )
        assert result["policy_result"]["auto_send_allowed"] is False
        assert result["next_action"]["action"] == "escalate_to_human"
