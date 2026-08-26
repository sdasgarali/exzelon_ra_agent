"""ELR-005b (write-guard on previously-deferred endpoints) + ELR-009b
(pre-flight credit gate on paid pipelines)."""
import pytest
from fastapi import HTTPException

from app.api.deps.auth import require_tenant_with_budget
from app.services.credit_metering import record_usage

pytestmark = pytest.mark.integration


# ---- ELR-005b: super-admin must impersonate to write (no silent tenant-1) ----

def test_super_admin_apikey_create_blocked_without_tenant(client, sa_headers):
    r = client.post("/api/v1/integrations/api-keys", headers=sa_headers,
                    json={"name": "k", "scopes": ["read"]})
    assert r.status_code == 400


def test_super_admin_apikey_create_ok_with_impersonation(client, sa_headers, test_tenant):
    r = client.post(
        "/api/v1/integrations/api-keys",
        headers={**sa_headers, "X-Tenant-ID": str(test_tenant.tenant_id)},
        json={"name": "k", "scopes": ["read"]},
    )
    assert r.status_code == 200


# ---- ELR-009b: paid-pipeline credit gate ----

@pytest.mark.asyncio
async def test_budget_dep_blocks_over_ceiling(db_session, professional_capped_tenant, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "CREDIT_ENFORCEMENT_ENABLED", True)
    monkeypatch.setattr(settings, "CREDIT_LIMIT_PROFESSIONAL", 5)
    tid = professional_capped_tenant.tenant_id
    record_usage(db_session, tid, "ai_generation", credits=5)
    with pytest.raises(HTTPException) as exc:
        await require_tenant_with_budget(db=db_session, tenant_id=tid)
    assert exc.value.status_code == 402


@pytest.mark.asyncio
async def test_budget_dep_noop_when_disabled(db_session, professional_capped_tenant):
    tid = professional_capped_tenant.tenant_id
    record_usage(db_session, tid, "ai_generation", credits=999_999)
    # Enforcement off by default → dependency returns the tenant id, no raise.
    assert await require_tenant_with_budget(db=db_session, tenant_id=tid) == tid
