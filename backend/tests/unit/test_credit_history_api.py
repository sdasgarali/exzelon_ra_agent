"""Credit history API — the ledger the top-bar meter and history page read."""
from datetime import datetime

import pytest

from app.db.models.credit_usage import CreditUsage

pytestmark = pytest.mark.unit


def _row(db, tenant_id, usage_type, credits, **kw):
    row = CreditUsage(tenant_id=tenant_id, usage_type=usage_type, credits_used=credits,
                      recorded_at=kw.pop("recorded_at", datetime.utcnow()), **kw)
    db.add(row)
    db.commit()
    return row


def test_usage_items_carry_label_and_category(client, db_session, test_tenant, auth_headers):
    _row(db_session, test_tenant.tenant_id, "lead_sourced", 12, reference_id="run-1")
    _row(db_session, test_tenant.tenant_id, "topup_purchase", -1000)

    res = client.get("/api/v1/credits/usage", headers=auth_headers)
    assert res.status_code == 200
    by_type = {i["usage_type"]: i for i in res.json()["items"]}

    assert by_type["lead_sourced"]["label"] == "Lead sourced"
    assert by_type["lead_sourced"]["category"] == "data"
    assert by_type["topup_purchase"]["label"] == "Credits purchased"
    assert by_type["topup_purchase"]["category"] == "grant"


def test_usage_is_tenant_scoped(client, db_session, test_tenant, auth_headers):
    from app.db.models.tenant import Tenant
    other = Tenant(name="Other Co", slug="other-co-hist", plan="free")
    db_session.add(other)
    db_session.commit()
    _row(db_session, other.tenant_id, "contact_enriched", 3)
    _row(db_session, test_tenant.tenant_id, "email_validated", 1)

    items = client.get("/api/v1/credits/usage", headers=auth_headers).json()["items"]
    assert {i["tenant_id"] for i in items} == {test_tenant.tenant_id}


def test_summary_excludes_topups_from_usage(client, db_session, test_tenant, auth_headers):
    _row(db_session, test_tenant.tenant_id, "contact_enriched", 9)
    _row(db_session, test_tenant.tenant_id, "topup_purchase", -1000)

    body = client.get("/api/v1/credits/summary", headers=auth_headers).json()
    assert body["total_credits_used"] == 9
    assert [r["usage_type"] for r in body["by_type"]] == ["contact_enriched"]
    assert body["by_type"][0]["label"] == "Contact discovered"


def test_usage_filters_by_type_and_date(client, db_session, test_tenant, auth_headers):
    _row(db_session, test_tenant.tenant_id, "lead_sourced", 5,
         recorded_at=datetime(2026, 1, 5))
    _row(db_session, test_tenant.tenant_id, "lead_sourced", 7,
         recorded_at=datetime(2026, 2, 5))
    _row(db_session, test_tenant.tenant_id, "email_validated", 1,
         recorded_at=datetime(2026, 2, 6))

    res = client.get("/api/v1/credits/usage", headers=auth_headers, params={
        "usage_type": "lead_sourced", "from_date": "2026-02-01", "to_date": "2026-02-28"})
    items = res.json()["items"]
    assert [i["credits_used"] for i in items] == [7]
