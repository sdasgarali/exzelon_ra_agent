"""Tests for the centralized Scoring Engine."""
import pytest

pytestmark = pytest.mark.unit


class TestLeadScore:
    def test_active_hiring_adds_points(self):
        from app.services.ai_sales_agent.scoring_engine import calculate_lead_score
        ctx = {
            "lead": {"job_title": "Warehouse Manager", "posting_date": "2026-04-05"},
            "company": {"size": "51-200", "industry": "Manufacturing",
                        "linkedin": "https://linkedin.com/company/test",
                        "website": "https://test.com"},
        }
        result = calculate_lead_score(ctx)
        assert result["score"] > 0
        assert "ACTIVE_HIRING" in result["factors"]

    def test_no_job_title_low_score(self):
        from app.services.ai_sales_agent.scoring_engine import calculate_lead_score
        ctx = {
            "lead": {"job_title": None, "posting_date": None},
            "company": {"size": None, "industry": None, "linkedin": None, "website": None},
        }
        result = calculate_lead_score(ctx)
        assert result["score"] == 0

    def test_mid_market_adds_15(self):
        from app.services.ai_sales_agent.scoring_engine import calculate_lead_score
        ctx = {
            "lead": {"job_title": "Manager", "posting_date": None},
            "company": {"size": "201-500", "industry": None, "linkedin": None, "website": None},
        }
        result = calculate_lead_score(ctx)
        assert "MID_MARKET" in result["factors"]
        assert result["factors"]["MID_MARKET"] == 15

    def test_high_salary_adds_points(self):
        from app.services.ai_sales_agent.scoring_engine import calculate_lead_score
        ctx = {
            "lead": {"job_title": "Director", "posting_date": None, "salary_min": 100000},
            "company": {"size": None, "industry": None, "linkedin": None, "website": None},
        }
        result = calculate_lead_score(ctx)
        assert "HIGH_BUDGET_ROLE" in result["factors"]

    def test_score_capped_at_100(self):
        from app.services.ai_sales_agent.scoring_engine import calculate_lead_score
        ctx = {
            "lead": {"job_title": "Dir", "posting_date": "2026-04-06", "salary_min": 120000},
            "company": {"size": "201-500", "industry": "Tech",
                        "linkedin": "http://li.com", "website": "http://x.com"},
        }
        result = calculate_lead_score(ctx)
        assert result["score"] <= 100


class TestEngagementScore:
    def test_zero_engagement_with_sends(self):
        from app.services.ai_sales_agent.scoring_engine import calculate_engagement_score
        history = {"emails_sent": 3, "emails_replied": 0, "emails_opened": 0, "emails_clicked": 0}
        result = calculate_engagement_score(history)
        assert result["level"] == "dead"

    def test_no_sends_is_cold(self):
        from app.services.ai_sales_agent.scoring_engine import calculate_engagement_score
        history = {"emails_sent": 0, "emails_replied": 0, "emails_opened": 0, "emails_clicked": 0}
        result = calculate_engagement_score(history)
        assert result["score"] == 0
        assert result["level"] == "cold"

    def test_reply_boosts_engagement(self):
        from app.services.ai_sales_agent.scoring_engine import calculate_engagement_score
        history = {"emails_sent": 3, "emails_replied": 1, "emails_opened": 2, "emails_clicked": 1}
        result = calculate_engagement_score(history)
        assert result["score"] > 0
        assert result["level"] in ("warm", "hot")

    def test_open_only_is_warm(self):
        from app.services.ai_sales_agent.scoring_engine import calculate_engagement_score
        history = {"emails_sent": 2, "emails_replied": 0, "emails_opened": 5, "emails_clicked": 0}
        result = calculate_engagement_score(history)
        assert result["level"] == "warm"


class TestCompositeScore:
    def test_composite_combines_scores(self):
        from app.services.ai_sales_agent.scoring_engine import calculate_composite_score
        ctx = {
            "lead": {"job_title": "Manager", "posting_date": None},
            "company": {"size": "51-200", "industry": "Manufacturing",
                        "linkedin": None, "website": None},
            "history": {"emails_sent": 1, "emails_replied": 1,
                        "emails_opened": 1, "emails_clicked": 0},
            "contact": {"priority": "P1_JOB_POSTER"},
        }
        result = calculate_composite_score(ctx)
        assert "lead_score" in result
        assert "engagement_score" in result
        assert "composite" in result
        assert 0 <= result["composite"] <= 100

    def test_composite_without_priority(self):
        from app.services.ai_sales_agent.scoring_engine import calculate_composite_score
        ctx = {
            "lead": {"job_title": None, "posting_date": None},
            "company": {"size": None, "industry": None, "linkedin": None, "website": None},
            "history": {"emails_sent": 0, "emails_replied": 0,
                        "emails_opened": 0, "emails_clicked": 0},
            "contact": {"priority": None},
        }
        result = calculate_composite_score(ctx)
        assert result["composite"] >= 0
