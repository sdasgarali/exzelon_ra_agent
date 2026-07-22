"""Phase 2: Resource Pool outcome webhook → attribution."""
import hashlib
import hmac
import json

import pytest

from app.core.settings_resolver import set_tenant_setting
from app.db.models.lead import LeadDetails, LeadStatus
from app.db.models.resource_pool_attribution import ResourcePoolAttribution

pytestmark = pytest.mark.integration

WEBHOOK = "/api/v1/integrations/resource-pool/webhook"
SECRET = "whsec_test_secret"


def _sign(body: str) -> str:
    return hmac.new(SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()


def _mk_lead(db, tenant_id, source="fantastic_jobs"):
    lead = LeadDetails(tenant_id=tenant_id, client_name="Acme Mfg", job_title="Ops Manager",
                       source=source, lead_status=LeadStatus.NEW)
    db.add(lead)
    db.commit()
    return lead


def _envelope(event, data):
    return json.dumps({"event": event, "createdAt": "2026-07-22T00:00:00Z", "data": data})


def test_webhook_no_secret_returns_503(client):
    body = _envelope("placement.created", {})
    resp = client.post(WEBHOOK, content=body, headers={"X-Exzelon-Signature": _sign(body)})
    assert resp.status_code == 503


def test_webhook_bad_signature_401(client, db_session):
    set_tenant_setting(db_session, "resourcepool_webhook_secret", SECRET, tenant_id=None)
    db_session.commit()
    body = _envelope("placement.created", {"placementId": "p1"})
    resp = client.post(WEBHOOK, content=body, headers={"X-Exzelon-Signature": "deadbeef"})
    assert resp.status_code == 401


def test_webhook_records_and_maps_attribution(client, db_session, test_tenant):
    set_tenant_setting(db_session, "resourcepool_webhook_secret", SECRET, tenant_id=None)
    db_session.commit()
    lead = _mk_lead(db_session, test_tenant.tenant_id)
    data = {"externalRef": f"ra-lead-{lead.lead_id}", "placementId": "plc_9",
            "candidateId": "c1", "billRate": 85, "companyName": "Acme Mfg"}
    body = _envelope("placement.created", data)
    resp = client.post(WEBHOOK, content=body, headers={"X-Exzelon-Signature": _sign(body)})
    assert resp.status_code == 200

    rows = db_session.query(ResourcePoolAttribution).filter(
        ResourcePoolAttribution.event_type == "placement.created",
        ResourcePoolAttribution.rp_entity_id == "plc_9").all()
    assert len(rows) == 1
    r = rows[0]
    assert r.lead_id == lead.lead_id
    assert r.source == "fantastic_jobs"
    assert float(r.amount) == 85.0


def test_webhook_is_idempotent(client, db_session, test_tenant):
    set_tenant_setting(db_session, "resourcepool_webhook_secret", SECRET, tenant_id=None)
    db_session.commit()
    lead = _mk_lead(db_session, test_tenant.tenant_id)
    data = {"externalRef": f"ra-lead-{lead.lead_id}", "offerId": "off_1", "offerAmount": 120000}
    body = _envelope("offer.accepted", data)
    for _ in range(2):
        assert client.post(WEBHOOK, content=body, headers={"X-Exzelon-Signature": _sign(body)}).status_code == 200
    rows = db_session.query(ResourcePoolAttribution).filter(
        ResourcePoolAttribution.event_type == "offer.accepted",
        ResourcePoolAttribution.rp_entity_id == "off_1").all()
    assert len(rows) == 1  # no duplicate on re-delivery


def test_webhook_ignores_unsubscribed_event(client, db_session):
    set_tenant_setting(db_session, "resourcepool_webhook_secret", SECRET, tenant_id=None)
    db_session.commit()
    body = _envelope("candidate.updated", {"id": "x"})
    resp = client.post(WEBHOOK, content=body, headers={"X-Exzelon-Signature": _sign(body)})
    assert resp.status_code == 200
    assert resp.json().get("ignored") == "candidate.updated"


def test_attribution_summary_date_filter(client, db_session, test_tenant, auth_headers):
    from datetime import datetime
    db_session.add_all([
        ResourcePoolAttribution(tenant_id=test_tenant.tenant_id, event_type="invoice.paid",
                                rp_entity_id="in_old", source="src", amount=1000,
                                occurred_at=datetime(2026, 1, 15)),
        ResourcePoolAttribution(tenant_id=test_tenant.tenant_id, event_type="invoice.paid",
                                rp_entity_id="in_new", source="src", amount=2000,
                                occurred_at=datetime(2026, 7, 15)),
    ])
    db_session.commit()
    # July window → only the $2000 row
    r1 = client.get("/api/v1/integrations/resource-pool/attribution?start=2026-07-01&end=2026-07-31",
                    headers=auth_headers)
    assert r1.status_code == 200
    assert r1.json()["totals"]["revenue_paid"] == 2000.0
    # full-year window → both
    r2 = client.get("/api/v1/integrations/resource-pool/attribution?start=2026-01-01&end=2026-12-31",
                    headers=auth_headers)
    assert r2.json()["totals"]["revenue_paid"] == 3000.0


def test_attribution_summary(client, db_session, test_tenant, auth_headers):
    db_session.add_all([
        ResourcePoolAttribution(tenant_id=test_tenant.tenant_id, event_type="placement.created",
                                rp_entity_id="p1", source="fantastic_jobs", amount=90),
        ResourcePoolAttribution(tenant_id=test_tenant.tenant_id, event_type="invoice.paid",
                                rp_entity_id="i1", source="fantastic_jobs", amount=5000),
    ])
    db_session.commit()
    resp = client.get("/api/v1/integrations/resource-pool/attribution", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["totals"]["placements"] == 1
    assert body["totals"]["revenue_paid"] == 5000.0
    assert any(s["source"] == "fantastic_jobs" for s in body["by_source"])
