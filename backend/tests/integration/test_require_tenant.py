"""A super-admin must SELECT (impersonate) a tenant before running a tenant-scoped
pipeline. `require_tenant_id` returns 400 when no concrete tenant is resolved, so
the run can't silently fall back to a default tenant / the global settings."""
import pytest
from fastapi import HTTPException

from app.api.deps.auth import require_tenant_id

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_require_tenant_id_blocks_none():
    with pytest.raises(HTTPException) as exc:
        await require_tenant_id(tenant_id=None)
    assert exc.value.status_code == 400
    assert "select a tenant" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_require_tenant_id_passes_concrete():
    assert await require_tenant_id(tenant_id=7) == 7


def test_superadmin_without_tenant_is_blocked_on_pipeline_run(client, super_admin_headers):
    """Super-admin (tenant_id=None) with no X-Tenant-ID → 400 at the dependency
    (before the endpoint body), not a silent default. The concrete-tenant pass-through
    is covered by test_require_tenant_id_passes_concrete above."""
    resp = client.post("/api/v1/pipelines/contact-enrichment/run", headers=super_admin_headers)
    assert resp.status_code == 400
    assert "select a tenant" in resp.json()["detail"].lower()
