"""Unit tests for cost tracking — pipeline, contact-discovery, and AI/LLM costs,
plus query-side negative-keyword helpers."""
import pytest

from app.services import cost_tracker as ct
from app.services.adapters.base import JobSourceAdapter
from app.services.adapters.job_sources.serpapi import SerpAPIAdapter
from app.db.models.cost_tracking import CostEntry

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# AI token cost computation
# ---------------------------------------------------------------------------

def test_ai_token_cost_known_model():
    # gpt-4.1-nano = (0.10 in, 0.40 out) per 1M tokens
    cost = ct._ai_token_cost("openai", "gpt-4.1-nano", 1_000_000, 1_000_000)
    assert cost == pytest.approx(0.50)


def test_ai_token_cost_groq_is_free():
    assert ct._ai_token_cost("groq", "llama-3.3-70b-versatile", 5000, 5000) == 0.0


def test_ai_token_cost_unknown_model_uses_provider_fallback():
    # Unknown anthropic model → fallback (0.80, 4.00)
    cost = ct._ai_token_cost("anthropic", "claude-x-unknown", 1_000_000, 0)
    assert cost == pytest.approx(0.80)


def test_ai_token_cost_unknown_provider_defaults_zero():
    assert ct._ai_token_cost("nobody", "no-model", 1_000_000, 1_000_000) == 0.0


# ---------------------------------------------------------------------------
# record_pipeline_cost — category + tenant_id
# ---------------------------------------------------------------------------

def test_record_pipeline_cost_contact_discovery_category(db_session):
    entry = ct.record_pipeline_cost(
        db_session, "rocketreach", api_calls=10, results=8,
        category="contact_discovery", tenant_id=5,
    )
    db_session.commit()
    assert entry is not None
    assert entry.category == "contact_discovery"
    assert entry.tenant_id == 5
    assert entry.source_adapter == "rocketreach"
    assert entry.api_calls_count == 10
    assert entry.results_count == 8
    # rocketreach $0.10/req, free_monthly 5 → ~0/day free → billable
    assert float(entry.amount) > 0


def test_record_pipeline_cost_defaults_lead_sourcing_tenant1(db_session):
    entry = ct.record_pipeline_cost(db_session, "serpapi", 3, 50)
    db_session.commit()
    assert entry.category == "lead_sourcing"
    assert entry.tenant_id == 1


# ---------------------------------------------------------------------------
# record_ai_cost — SAVEPOINT-isolated, caller's session
# ---------------------------------------------------------------------------

def test_record_ai_cost_inserts_entry(db_session):
    entry = ct.record_ai_cost(
        db_session, provider="openai", model="gpt-4.1-nano",
        input_tokens=2000, output_tokens=1000, feature="campaign", tenant_id=3,
    )
    db_session.commit()
    assert entry is not None
    rows = db_session.query(CostEntry).filter(CostEntry.category == "ai").all()
    assert len(rows) == 1
    assert rows[0].source_adapter == "openai"
    assert rows[0].tenant_id == 3
    assert float(rows[0].amount) > 0
    assert "gpt-4.1-nano" in rows[0].notes


def test_record_ai_cost_zero_tokens_is_noop(db_session):
    entry = ct.record_ai_cost(db_session, "openai", "gpt-4.1-nano", 0, 0)
    assert entry is None
    assert db_session.query(CostEntry).count() == 0


def test_record_ai_cost_does_not_break_caller_transaction(db_session):
    """A failed savepoint must not corrupt the caller's pending work."""
    ct.record_ai_cost(db_session, "groq", "llama-3.3-70b-versatile", 100, 50)
    # Groq is free → amount 0 but tokens present → entry still recorded
    other = CostEntry(
        tenant_id=1, category="lead_sourcing", amount=1.23,
        entry_date=__import__("datetime").date.today(), source_adapter="serpapi",
    )
    db_session.add(other)
    db_session.commit()
    assert db_session.query(CostEntry).count() == 2


# ---------------------------------------------------------------------------
# Negative-keyword query helpers (cost-reduction optimization)
# ---------------------------------------------------------------------------

def test_build_negative_terms_dedups_and_bounds():
    terms = JobSourceAdapter.build_negative_terms(
        exclude_keywords=["Intern", "staffing agency"],
        exclude_title_keywords=["intern", "Recruiter"],  # dup "intern" (case-insensitive)
        max_terms=12,
    )
    assert terms == ["Intern", "staffing agency", "Recruiter"]


def test_build_negative_terms_respects_max():
    terms = JobSourceAdapter.build_negative_terms(
        exclude_keywords=[f"kw{i}" for i in range(20)], max_terms=5
    )
    assert len(terms) == 5


def test_google_negative_suffix_quotes_multiword():
    suffix = JobSourceAdapter.google_negative_suffix(["intern", "staffing agency"])
    assert suffix == ' -intern -"staffing agency"'


def test_google_negative_suffix_empty():
    assert JobSourceAdapter.google_negative_suffix([]) == ""


def test_adapter_negative_terms_honors_push_flag():
    a = SerpAPIAdapter(api_key="x")
    a._exclude_title = ["intern"]
    a._push_negatives = False
    assert a._negative_terms(["staffing"]) == []
    a._push_negatives = True
    assert "staffing" in a._negative_terms(["staffing"])
    assert "intern" in a._negative_terms(["staffing"])
