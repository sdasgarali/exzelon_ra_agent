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


def _patch_pitch(monkeypatch, enabled, summary):
    import app.services.integrations.resource_pool_client as mod
    monkeypatch.setattr(mod, "get_tenant_setting_bool", lambda *a, **k: enabled)

    class _C:
        timeout = 30
        def get_match_summary(self, ext, threshold=80):
            return summary

    monkeypatch.setattr(mod.ResourcePoolClient, "from_settings",
                        classmethod(lambda cls, db, tenant_id=None: _C()))
    return mod


def test_candidate_pitch_none_when_disabled(monkeypatch):
    mod = _patch_pitch(monkeypatch, False, {"matchCount": 5})
    assert mod.build_candidate_pitch(db=None, lead_id=9001, tenant_id=1) is None


def test_candidate_pitch_none_when_zero_matches(monkeypatch):
    mod = _patch_pitch(monkeypatch, True, {"matchCount": 0})
    assert mod.build_candidate_pitch(db=None, lead_id=9002, tenant_id=1) is None


def test_candidate_pitch_none_without_lead(monkeypatch):
    mod = _patch_pitch(monkeypatch, True, {"matchCount": 5})
    assert mod.build_candidate_pitch(db=None, lead_id=None, tenant_id=1) is None


def test_candidate_pitch_formats_with_role_and_count(monkeypatch):
    mod = _patch_pitch(monkeypatch, True, {"matchCount": 5, "jobTitle": "Operations Manager"})
    p = mod.build_candidate_pitch(db=None, lead_id=9003, tenant_id=1)
    assert p is not None
    assert "5 pre-screened candidates" in p
    assert "Operations Manager" in p
    assert "80%" in p


def test_get_match_summary_calls_by_code_endpoint(monkeypatch):
    captured = {}

    class _Resp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"matchCount": 3, "threshold": 80, "topMatches": []}

    class _Client:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, url, params=None, headers=None):
            captured.update(url=url, params=params, headers=headers)
            return _Resp()

    monkeypatch.setattr("app.services.integrations.resource_pool_client.httpx.Client", _Client)
    c = ResourcePoolClient(base_url="https://rp.example.com", api_key="exz_k")
    out = c.get_match_summary("ra-lead-815", threshold=80)
    assert out["matchCount"] == 3
    assert captured["url"] == "https://rp.example.com/api/v1/jobs/by-code/ra-lead-815/match-summary"
    assert captured["params"] == {"threshold": 80}
    assert captured["headers"]["Authorization"] == "Bearer exz_k"


def test_auto_push_noop_when_disabled(monkeypatch):
    """When resourcepool_auto_push_on_reply is off, the auto-push is a no-op and
    never touches the network."""
    import app.services.integrations.resource_pool_client as mod
    monkeypatch.setattr(mod, "get_tenant_setting_bool", lambda *a, **k: False)
    called = {"n": 0}
    monkeypatch.setattr(mod, "push_lead_by_id", lambda *a, **k: called.__setitem__("n", called["n"] + 1))
    contact = SimpleNamespace(tenant_id=1, lead_id=42)
    assert mod.auto_push_lead_on_interested_reply(db=None, contact=contact) is None
    assert called["n"] == 0


def test_auto_push_noop_when_no_lead(monkeypatch):
    import app.services.integrations.resource_pool_client as mod
    monkeypatch.setattr(mod, "get_tenant_setting_bool", lambda *a, **k: True)
    contact = SimpleNamespace(tenant_id=1, lead_id=None)  # no linked lead
    assert mod.auto_push_lead_on_interested_reply(db=None, contact=contact) is None


def test_auto_push_calls_push_when_enabled(monkeypatch):
    import app.services.integrations.resource_pool_client as mod
    monkeypatch.setattr(mod, "get_tenant_setting_bool", lambda *a, **k: True)
    seen = {}
    monkeypatch.setattr(mod, "push_lead_by_id",
                        lambda db, lead_id, tenant_id=None, stage="LEAD": seen.update(lead_id=lead_id, stage=stage) or {"opportunityId": "o9", "jobId": "j9"})
    monkeypatch.setattr(mod, "_log_event", lambda *a, **k: None)
    contact = SimpleNamespace(tenant_id=1, lead_id=815)
    out = mod.auto_push_lead_on_interested_reply(db=None, contact=contact)
    assert out["opportunityId"] == "o9"
    assert seen == {"lead_id": 815, "stage": "QUALIFIED"}  # positive reply → QUALIFIED


def test_auto_push_swallows_errors(monkeypatch):
    """A push failure must never propagate out of inbox processing."""
    import app.services.integrations.resource_pool_client as mod
    monkeypatch.setattr(mod, "get_tenant_setting_bool", lambda *a, **k: True)
    def _boom(*a, **k):
        raise RuntimeError("rp down")
    monkeypatch.setattr(mod, "push_lead_by_id", _boom)
    monkeypatch.setattr(mod, "_log_event", lambda *a, **k: None)
    contact = SimpleNamespace(tenant_id=1, lead_id=815)
    assert mod.auto_push_lead_on_interested_reply(db=None, contact=contact) is None  # no raise


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
