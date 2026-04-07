"""Tests for AI structured output schemas + JSON parsing."""
import pytest
from app.services.ai_schemas import (
    ReplyClassification,
    DraftEmailResponse,
    NextBestAction,
    SpamCheckResult,
    ReplyIntent,
    NextAction,
    ContentRisk,
    parse_ai_json_response,
    get_schema_instruction,
)


pytestmark = pytest.mark.unit


class TestReplyClassification:
    """Test ReplyClassification schema validation."""

    def test_valid_classification(self):
        rc = ReplyClassification(
            intent=ReplyIntent.INTERESTED,
            confidence=85,
            reasoning="Contact expressed interest in scheduling a call.",
        )
        assert rc.intent == ReplyIntent.INTERESTED
        assert rc.confidence == 85

    def test_confidence_bounds(self):
        rc = ReplyClassification(
            intent=ReplyIntent.QUESTION,
            confidence=50,
            reasoning="Asked about pricing.",
        )
        assert 0 <= rc.confidence <= 100

    def test_all_intents_valid(self):
        for intent in ReplyIntent:
            rc = ReplyClassification(
                intent=intent,
                confidence=70,
                reasoning="test",
            )
            assert rc.intent == intent

    def test_default_fields(self):
        rc = ReplyClassification(
            intent=ReplyIntent.UNKNOWN,
            confidence=50,
        )
        assert rc.sentiment == "neutral"
        assert rc.has_meeting_intent is False
        assert rc.key_phrases == []
        assert rc.recommended_action == NextAction.ESCALATE_TO_HUMAN


class TestDraftEmailResponse:
    """Test DraftEmailResponse schema."""

    def test_valid_response(self):
        resp = DraftEmailResponse(
            subject="Re: Your inquiry",
            body_text="Hi John, thanks for reaching out about our services. I'd love to chat more.",
            tone="professional",
        )
        assert resp.subject == "Re: Your inquiry"
        assert resp.tone == "professional"

    def test_default_fields(self):
        resp = DraftEmailResponse(
            subject="Follow up",
            body_text="Some body text that is long enough to meet the minimum length.",
        )
        assert resp.body_html == ""
        assert resp.personalization_score == 50
        assert resp.content_risk == ContentRisk.LOW


class TestNextBestAction:
    """Test NextBestAction schema."""

    def test_valid_action(self):
        nba = NextBestAction(
            action=NextAction.SCHEDULE_FOLLOWUP,
            confidence=90,
            reasoning="High interest signal detected.",
        )
        assert nba.action == NextAction.SCHEDULE_FOLLOWUP
        assert nba.confidence == 90

    def test_all_actions(self):
        for action in NextAction:
            nba = NextBestAction(
                action=action,
                confidence=75,
                reasoning="test",
            )
            assert nba.action == action

    def test_default_requires_approval(self):
        nba = NextBestAction(
            action=NextAction.SEND_REPLY,
            confidence=80,
        )
        assert nba.requires_human_approval is True


class TestParseAIJsonResponse:
    """Test JSON parsing from AI model output."""

    def test_direct_json(self):
        raw = '{"intent": "interested", "confidence": 80, "reasoning": "Wants to meet"}'
        result, error = parse_ai_json_response(raw, ReplyClassification)
        assert result is not None
        assert error == ""
        assert result.intent == ReplyIntent.INTERESTED
        assert result.confidence == 80

    def test_fenced_json(self):
        raw = """Here is my analysis:
```json
{"intent": "objection", "confidence": 65, "reasoning": "Not interested right now"}
```
"""
        result, error = parse_ai_json_response(raw, ReplyClassification)
        assert result is not None
        assert result.intent == ReplyIntent.OBJECTION

    def test_embedded_braces(self):
        raw = 'The classification is {"intent": "question", "confidence": 70, "reasoning": "Asked about features"} based on the email.'
        result, error = parse_ai_json_response(raw, ReplyClassification)
        assert result is not None
        assert result.intent == ReplyIntent.QUESTION

    def test_invalid_json_returns_none(self):
        raw = "This is not JSON at all."
        result, error = parse_ai_json_response(raw, ReplyClassification, strict=False)
        assert result is None
        assert error != ""

    def test_empty_response(self):
        result, error = parse_ai_json_response("", ReplyClassification)
        assert result is None
        assert "Empty" in error

    def test_spam_check_schema(self):
        raw = '{"spam_score": 45, "risk_level": "medium", "flagged_words": ["free", "guaranteed"], "suggestions": ["Remove trigger words"], "safe_to_send": true}'
        result, error = parse_ai_json_response(raw, SpamCheckResult)
        assert result is not None
        assert result.spam_score == 45
        assert result.risk_level == ContentRisk.MEDIUM
        assert "free" in result.flagged_words


class TestGetSchemaInstruction:
    """Test schema instruction generation for AI prompts."""

    def test_returns_string(self):
        instruction = get_schema_instruction(ReplyClassification)
        assert isinstance(instruction, str)
        assert "JSON" in instruction

    def test_includes_field_names(self):
        instruction = get_schema_instruction(ReplyClassification)
        assert "intent" in instruction
        assert "confidence" in instruction

    def test_includes_field_names_for_action(self):
        instruction = get_schema_instruction(NextBestAction)
        assert "action" in instruction
