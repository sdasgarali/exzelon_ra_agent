"""Unit tests for the Resource Pool ATS hand-off connector (Phase 1)."""
from types import SimpleNamespace

import pytest

from app.services.integrations.resource_pool_client import (
    ResourcePoolClient, build_lead_payload,
)

pytestmark = pytest.mark.unit


def _lead(**over):
    base = dict(lead_id=42, client_name="Acme Manufacturing", job_title="Operations Manager",
                state="TX", city="Dallas", industry="Manufacturing",
                employer_website="https://acme.com", job_description="Run the plant.")
    base.update(over)
    return SimpleNamespace(**base)


def test_build_lead_payload_maps_core_fields():
    p = build_lead_payload(_lead())
    assert p["externalRef"] == "ra-lead-42"
    assert p["company"]["name"] == "Acme Manufacturing"
    assert p["company"]["industry"] == "Manufacturing"
    assert p["company"]["website"] == "https://acme.com"
    assert p["job"]["jobTitle"] == "Operations Manager"
    assert p["job"]["location"] == "Dallas, TX"
    assert p["job"]["description"] == "Run the plant."
    assert p["job"]["status"] == "OPEN"
    assert p["opportunity"]["stage"] == "LEAD"
    assert "contact" not in p  # none supplied


def test_build_lead_payload_prefers_company_and_contact():
    company = SimpleNamespace(client_name="Acme Mfg Inc", industry="Industrial",
                             website=None, domain="acme.com", location_state="TX")
    contact = SimpleNamespace(first_name="Jane", last_name="Poster", email="jane@acme.com",
                              phone="555-1", title="HR Director", client_name="Acme")
    p = build_lead_payload(_lead(), company=company, contact=contact, stage="QUALIFIED")
    assert p["company"]["name"] == "Acme Mfg Inc"       # company wins over lead.client_name
    assert p["company"]["website"] == "acme.com"        # domain fallback
    assert p["opportunity"]["stage"] == "QUALIFIED"
    assert p["contact"] == {"name": "Jane Poster", "email": "jane@acme.com",
                            "phone": "555-1", "title": "HR Director"}


def test_invalid_stage_defaults_to_lead():
    assert build_lead_payload(_lead(), stage="BOGUS")["opportunity"]["stage"] == "LEAD"


def test_push_lead_sends_bearer_and_returns_json(monkeypatch):
    captured = {}

    class _Resp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"ok": True, "jobId": "j1", "companyId": "c1", "opportunityId": "o1"}

    class _Client:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, url, json=None, headers=None):
            captured.update(url=url, json=json, headers=headers)
            return _Resp()

    monkeypatch.setattr("app.services.integrations.resource_pool_client.httpx.Client", _Client)
    c = ResourcePoolClient(base_url="https://rp.example.com/", api_key="exz_secret")
    out = c.push_lead({"externalRef": "ra-lead-42"})
    assert out["jobId"] == "j1"
    assert captured["url"] == "https://rp.example.com/api/v1/leads"
    assert captured["headers"]["Authorization"] == "Bearer exz_secret"
