"""Tests for the Send Decision Engine."""
import pytest

pytestmark = pytest.mark.unit


class TestMakeSendDecision:
    def test_blocks_invalid_email(self):
        from app.services.ai_sales_agent.send_decision import make_send_decision
        ctx = {
            "contact": {"validation_status": "Invalid", "outreach_status": "ACTIVE"},
            "lead": {"job_title": "Manager", "posting_date": None},
            "company": {"name": "Acme", "size": "51-200", "industry": "Mfg",
                        "linkedin": None, "website": None},
            "history": {"emails_sent": 0, "emails_replied": 0,
                        "emails_opened": 0, "emails_clicked": 0},
        }
        result = make_send_decision(ctx)
        assert result["should_send"] is False
        assert "INVALID_EMAIL" in result["reason_codes"]

    def test_allows_valid_contact(self):
        from app.services.ai_sales_agent.send_decision import make_send_decision
        ctx = {
            "contact": {"validation_status": "Valid", "outreach_status": "ACTIVE"},
            "lead": {"job_title": "Manager", "posting_date": None},
            "company": {"name": "Acme", "size": "51-200", "industry": "Mfg",
                        "linkedin": None, "website": None},
            "history": {"emails_sent": 0, "emails_replied": 0,
                        "emails_opened": 0, "emails_clicked": 0},
        }
        result = make_send_decision(ctx)
        assert result["should_send"] is True
        assert len(result["reason_codes"]) == 0

    def test_blocks_high_spam_score(self):
        from app.services.ai_sales_agent.send_decision import make_send_decision
        ctx = {
            "contact": {"validation_status": "Valid", "outreach_status": "ACTIVE"},
            "lead": {"job_title": "Manager", "posting_date": None},
            "company": {"name": "Acme", "size": None, "industry": None,
                        "linkedin": None, "website": None},
            "history": {"emails_sent": 0, "emails_replied": 0,
                        "emails_opened": 0, "emails_clicked": 0},
        }
        result = make_send_decision(ctx, spam_score=80)
        assert result["should_send"] is False
        assert "HIGH_SPAM_SCORE" in result["reason_codes"]

    def test_blocks_similar_content(self):
        from app.services.ai_sales_agent.send_decision import make_send_decision
        ctx = {
            "contact": {"validation_status": "Valid", "outreach_status": "ACTIVE"},
            "lead": {"job_title": "Manager", "posting_date": None},
            "company": {"name": "Acme", "size": None, "industry": None,
                        "linkedin": None, "website": None},
            "history": {"emails_sent": 0, "emails_replied": 0,
                        "emails_opened": 0, "emails_clicked": 0},
        }
        result = make_send_decision(ctx, similarity_score=0.95)
        assert result["should_send"] is False
        assert "CONTENT_TOO_SIMILAR" in result["reason_codes"]

    def test_includes_scoring(self):
        from app.services.ai_sales_agent.send_decision import make_send_decision
        ctx = {
            "contact": {"validation_status": "Valid", "outreach_status": "ACTIVE",
                        "priority": "P1_JOB_POSTER"},
            "lead": {"job_title": "Warehouse Manager", "posting_date": None},
            "company": {"name": "Acme", "size": "201-500", "industry": "Manufacturing",
                        "linkedin": None, "website": None},
            "history": {"emails_sent": 1, "emails_replied": 1,
                        "emails_opened": 1, "emails_clicked": 0},
        }
        result = make_send_decision(ctx)
        assert "composite_score" in result
        assert "lead_score" in result
        assert "engagement_score" in result
        assert result["composite_score"] > 0

    def test_multiple_violations_accumulate(self):
        from app.services.ai_sales_agent.send_decision import make_send_decision
        ctx = {
            "contact": {"validation_status": "Invalid", "outreach_status": "UNSUBSCRIBED"},
            "lead": {"job_title": None, "posting_date": None},
            "company": {"name": None, "size": None, "industry": None,
                        "linkedin": None, "website": None},
            "history": {"emails_sent": 0, "emails_replied": 0,
                        "emails_opened": 0, "emails_clicked": 0},
        }
        result = make_send_decision(ctx, spam_score=90)
        assert result["should_send"] is False
        assert len(result["reason_codes"]) >= 2  # At least INVALID_EMAIL + UNSUBSCRIBED
