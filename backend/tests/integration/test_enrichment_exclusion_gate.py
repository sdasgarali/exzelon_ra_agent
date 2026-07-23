"""Integration test: the pre-enrichment exclusion gate guarantees ZERO paid
contact-discovery API calls for out-of-scope leads.

This is the proof of the "100% foolproof" requirement — an excluded lead must
never reach ``adapter.search_contacts`` regardless of how it entered the DB.
"""
from unittest.mock import MagicMock

import pytest

from app.db.models.lead import LeadDetails, LeadStatus
from app.db.models.job_run import JobRun
from app.services.pipelines import contact_enrichment

pytestmark = pytest.mark.integration


def test_none_tenant_resolves_to_primary_for_settings_and_run(db_session, monkeypatch):
    """A super-admin run with no tenant selected (tenant_id=None) must resolve the
    Apollo/contact API keys + settings under the PRIMARY tenant (1) — not the global
    (super-admin) settings — so tenant-specific settings take precedence. Regression
    for: enrichment read the global key while labelling the run as tenant 1."""
    captured = {}
    mock_adapter = MagicMock()
    mock_adapter.search_contacts = MagicMock(return_value=[])

    def _adapters(db=None, tenant_id=None):
        captured["adapters_tenant"] = tenant_id  # before the fix this was None (global)
        return [("mockpaid", mock_adapter)]

    monkeypatch.setattr(contact_enrichment, "get_contact_discovery_adapters", _adapters)
    monkeypatch.setattr(db_session, "close", lambda: None)
    monkeypatch.setattr(contact_enrichment, "SessionLocal", lambda: db_session)

    contact_enrichment.run_contact_enrichment_pipeline(triggered_by="test", tenant_id=None)

    assert captured["adapters_tenant"] == 1  # settings/key now read under the primary tenant
    run = (db_session.query(JobRun)
           .filter(JobRun.pipeline_name == "contact_enrichment")
           .order_by(JobRun.run_id.desc()).first())
    assert run is not None and run.tenant_id == 1  # run attribution matches the settings tenant


def _make_lead(db, tenant_id, name, industry, size, **over):
    over.setdefault("lead_status", LeadStatus.NEW)
    over.setdefault("first_name", None)
    lead = LeadDetails(
        tenant_id=tenant_id,
        client_name=name,
        job_title="HR Manager",
        industry=industry,
        company_size=size,
        **over,
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return lead


def test_excluded_lead_never_calls_paid_adapter(db_session, test_tenant, monkeypatch):
    tid = test_tenant.tenant_id

    eligible = _make_lead(db_session, tid, "Northwind Traders", "Manufacturing", "120")
    excluded_it = _make_lead(db_session, tid, "Globex Systems", "Information Technology", "80")
    excluded_big = _make_lead(db_session, tid, "Umbrella Retail", "Retail", "9000")

    # Mock paid adapter — records every search_contacts call, returns no contacts
    # (so the eligible lead is simply marked skipped but the CALL still happens).
    mock_adapter = MagicMock()
    mock_adapter.search_contacts = MagicMock(return_value=[])

    monkeypatch.setattr(
        contact_enrichment, "get_contact_discovery_adapters",
        lambda db=None, tenant_id=None: [("mockpaid", mock_adapter)],
    )
    # Pipeline opens its own SessionLocal — point it at the test session.
    monkeypatch.setattr(db_session, "close", lambda: None)
    monkeypatch.setattr(contact_enrichment, "SessionLocal", lambda: db_session)

    result = contact_enrichment.run_contact_enrichment_pipeline(
        triggered_by="test", tenant_id=tid,
    )

    # Companies that actually hit the paid adapter.
    called_companies = {
        c.kwargs.get("company_name") for c in mock_adapter.search_contacts.call_args_list
    }

    # The eligible lead reached the adapter...
    assert "Northwind Traders" in called_companies
    # ...and NEITHER excluded lead did — no API spend on unwanted leads.
    assert "Globex Systems" not in called_companies
    assert "Umbrella Retail" not in called_companies

    # Excluded leads are now terminal so they never re-enter the queue.
    db_session.expire_all()
    assert db_session.get(LeadDetails, excluded_it.lead_id).lead_status == LeadStatus.EXCLUDED
    assert db_session.get(LeadDetails, excluded_big.lead_id).lead_status == LeadStatus.EXCLUDED
    assert "excluded:" in (db_session.get(LeadDetails, excluded_it.lead_id).skip_reason or "")

    # Counter surfaced for observability. The pipeline returns the counters dict.
    assert result["excluded"] == 2


def test_explicit_lead_ids_path_also_gated(db_session, test_tenant, monkeypatch):
    """The explicit lead_ids path (used by file/bulk import + manual enrich) is
    gated too — an excluded lead passed by id still makes no paid call."""
    tid = test_tenant.tenant_id
    excluded = _make_lead(
        db_session, tid, "Cyberdyne Software", "Computer Software", "300",
        lead_status=LeadStatus.OPEN,   # imported leads arrive as OPEN, not NEW
    )

    mock_adapter = MagicMock()
    mock_adapter.search_contacts = MagicMock(return_value=[])
    monkeypatch.setattr(
        contact_enrichment, "get_contact_discovery_adapters",
        lambda db=None, tenant_id=None: [("mockpaid", mock_adapter)],
    )
    monkeypatch.setattr(db_session, "close", lambda: None)
    monkeypatch.setattr(contact_enrichment, "SessionLocal", lambda: db_session)

    contact_enrichment.run_contact_enrichment_pipeline(
        triggered_by="test", tenant_id=tid, lead_ids=[excluded.lead_id],
    )

    mock_adapter.search_contacts.assert_not_called()
    db_session.expire_all()
    assert db_session.get(LeadDetails, excluded.lead_id).lead_status == LeadStatus.EXCLUDED
