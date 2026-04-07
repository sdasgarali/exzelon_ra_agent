"""Tests for LLM-powered Reply Intelligence."""
import pytest

pytestmark = pytest.mark.unit


class TestClassifyReplyKeyword:
    def test_interested_keywords(self):
        from app.services.ai_sales_agent.reply_intelligence import classify_reply_keyword
        result = classify_reply_keyword("Sounds good, let's schedule a call")
        assert result["intent"] == "interested"
        assert result["confidence"] >= 40

    def test_objection_keywords(self):
        from app.services.ai_sales_agent.reply_intelligence import classify_reply_keyword
        result = classify_reply_keyword("Not interested at this time, too expensive for us")
        assert result["intent"] == "objection"
        assert result["confidence"] >= 40

    def test_ooo_keywords(self):
        from app.services.ai_sales_agent.reply_intelligence import classify_reply_keyword
        result = classify_reply_keyword("I am out of office until Monday")
        assert result["intent"] == "ooo"

    def test_question_keywords(self):
        from app.services.ai_sales_agent.reply_intelligence import classify_reply_keyword
        result = classify_reply_keyword("How does your service work? Can you explain pricing?")
        assert result["intent"] == "question"

    def test_unsubscribe_keywords(self):
        from app.services.ai_sales_agent.reply_intelligence import classify_reply_keyword
        result = classify_reply_keyword("Please unsubscribe me and stop emailing")
        assert result["intent"] == "unsubscribe"

    def test_unknown_text(self):
        from app.services.ai_sales_agent.reply_intelligence import classify_reply_keyword
        result = classify_reply_keyword("asdf qwerty xyz gibberish")
        assert result["intent"] == "unknown"
        assert result["confidence"] == 30

    def test_meeting_intent_detected(self):
        from app.services.ai_sales_agent.reply_intelligence import classify_reply_keyword
        result = classify_reply_keyword("Let's schedule a call to discuss")
        assert result["has_meeting_intent"] is True

    def test_unsubscribe_intent_detected(self):
        from app.services.ai_sales_agent.reply_intelligence import classify_reply_keyword
        result = classify_reply_keyword("Please remove me from your list, unsubscribe")
        assert result["has_unsubscribe_intent"] is True

    def test_confidence_scales_with_keyword_matches(self):
        from app.services.ai_sales_agent.reply_intelligence import classify_reply_keyword
        # 1 keyword = 40 + 15 = 55
        result1 = classify_reply_keyword("interested")
        # Multiple keywords = higher confidence
        result2 = classify_reply_keyword("interested, sounds good, let's talk, schedule a call")
        assert result2["confidence"] > result1["confidence"]


class TestDetermineNextAction:
    def test_interested_suggests_reply(self):
        from app.services.ai_sales_agent.reply_intelligence import determine_next_action_rule_based
        result = determine_next_action_rule_based("interested", 85)
        assert result["action"] == "send_reply"
        assert result["requires_human_approval"] is False

    def test_interested_low_confidence_needs_approval(self):
        from app.services.ai_sales_agent.reply_intelligence import determine_next_action_rule_based
        result = determine_next_action_rule_based("interested", 55)
        assert result["action"] == "send_reply"
        assert result["requires_human_approval"] is True

    def test_ooo_suggests_followup(self):
        from app.services.ai_sales_agent.reply_intelligence import determine_next_action_rule_based
        result = determine_next_action_rule_based("ooo", 90)
        assert result["action"] == "schedule_followup"
        assert result["delay_hours"] == 72

    def test_unsubscribe_suggests_mark(self):
        from app.services.ai_sales_agent.reply_intelligence import determine_next_action_rule_based
        result = determine_next_action_rule_based("unsubscribe", 80)
        assert result["action"] == "mark_unsubscribed"
        assert result["requires_human_approval"] is True

    def test_low_confidence_escalates(self):
        from app.services.ai_sales_agent.reply_intelligence import determine_next_action_rule_based
        result = determine_next_action_rule_based("interested", 25)
        assert result["action"] == "escalate_to_human"

    def test_objection_always_needs_approval(self):
        from app.services.ai_sales_agent.reply_intelligence import determine_next_action_rule_based
        result = determine_next_action_rule_based("objection", 85)
        assert result["action"] == "send_reply"
        assert result["requires_human_approval"] is True
        assert result["delay_hours"] == 2

    def test_unknown_intent_escalates(self):
        from app.services.ai_sales_agent.reply_intelligence import determine_next_action_rule_based
        result = determine_next_action_rule_based("some_new_intent", 75)
        assert result["action"] == "escalate_to_human"
