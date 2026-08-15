"""Integration tests for the deal claim queue (claim/unclaim/assign + list filters)."""
import pytest

from app.db.models.deal import Deal, DealStage

pytestmark = pytest.mark.integration


@pytest.fixture
def stage(db_session, test_tenant):
    s = DealStage(tenant_id=test_tenant.tenant_id, name="New Lead", stage_order=1, color="#111")
    db_session.add(s)
    db_session.commit()
    db_session.refresh(s)
    return s


@pytest.fixture
def other_tenant_stage(db_session):
    from app.db.models.tenant import Tenant, TenantPlan
    t = Tenant(name="Other", slug="other-dealq", plan=TenantPlan.ENTERPRISE,
               max_users=9, max_mailboxes=9, max_contacts=99, max_campaigns=9, max_leads=99)
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)
    s = DealStage(tenant_id=t.tenant_id, name="New Lead", stage_order=1, color="#111")
    db_session.add(s)
    db_session.commit()
    db_session.refresh(s)
    return s


def _mk_deal(db, tenant_id, stage_id, name="Acme — Jane", value=1000, probability=20, **kw):
    d = Deal(tenant_id=tenant_id, name=name, stage_id=stage_id, value=value, probability=probability, **kw)
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


class TestClaim:
    def test_rep_claims_unclaimed(self, client, db_session, operator_headers, operator_user, test_tenant, stage):
        d = _mk_deal(db_session, test_tenant.tenant_id, stage.stage_id)
        resp = client.post(f"/api/v1/deals/{d.deal_id}/claim", headers=operator_headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["is_unclaimed"] is False
        assert body["claimed_by"]["id"] == operator_user.user_id
        assert body["claimed_by"]["initials"]  # e.g. "OU"

    def test_admin_cannot_claim(self, client, db_session, auth_headers, test_tenant, stage):
        d = _mk_deal(db_session, test_tenant.tenant_id, stage.stage_id)
        resp = client.post(f"/api/v1/deals/{d.deal_id}/claim", headers=auth_headers)
        assert resp.status_code == 403

    def test_cannot_claim_already_claimed(self, client, db_session, operator_headers, viewer_headers, viewer_user, test_tenant, stage):
        d = _mk_deal(db_session, test_tenant.tenant_id, stage.stage_id, claimed_by_user_id=viewer_user.user_id)
        resp = client.post(f"/api/v1/deals/{d.deal_id}/claim", headers=operator_headers)
        assert resp.status_code == 400

    def test_claim_is_tenant_isolated(self, client, db_session, operator_headers, other_tenant_stage):
        # deal in another tenant → 404
        d = _mk_deal(db_session, other_tenant_stage.tenant_id, other_tenant_stage.stage_id)
        resp = client.post(f"/api/v1/deals/{d.deal_id}/claim", headers=operator_headers)
        assert resp.status_code == 404


class TestUnclaim:
    def test_claimer_releases(self, client, db_session, operator_headers, operator_user, test_tenant, stage):
        d = _mk_deal(db_session, test_tenant.tenant_id, stage.stage_id, claimed_by_user_id=operator_user.user_id)
        resp = client.post(f"/api/v1/deals/{d.deal_id}/unclaim", headers=operator_headers)
        assert resp.status_code == 200
        assert resp.json()["is_unclaimed"] is True

    def test_other_rep_cannot_release(self, client, db_session, viewer_headers, operator_user, test_tenant, stage):
        d = _mk_deal(db_session, test_tenant.tenant_id, stage.stage_id, claimed_by_user_id=operator_user.user_id)
        resp = client.post(f"/api/v1/deals/{d.deal_id}/unclaim", headers=viewer_headers)
        assert resp.status_code == 403

    def test_admin_can_release(self, client, db_session, auth_headers, operator_user, test_tenant, stage):
        d = _mk_deal(db_session, test_tenant.tenant_id, stage.stage_id, claimed_by_user_id=operator_user.user_id)
        resp = client.post(f"/api/v1/deals/{d.deal_id}/unclaim", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["is_unclaimed"] is True


class TestAssign:
    def test_admin_assigns_to_rep(self, client, db_session, auth_headers, operator_user, test_tenant, stage):
        d = _mk_deal(db_session, test_tenant.tenant_id, stage.stage_id)
        resp = client.post(f"/api/v1/deals/{d.deal_id}/assign", headers=auth_headers, json={"user_id": operator_user.user_id})
        assert resp.status_code == 200, resp.text
        assert resp.json()["owner"]["id"] == operator_user.user_id

    def test_cannot_assign_to_admin(self, client, db_session, auth_headers, admin_user, test_tenant, stage):
        d = _mk_deal(db_session, test_tenant.tenant_id, stage.stage_id)
        resp = client.post(f"/api/v1/deals/{d.deal_id}/assign", headers=auth_headers, json={"user_id": admin_user.user_id})
        assert resp.status_code == 400

    def test_rep_cannot_assign(self, client, db_session, operator_headers, viewer_user, test_tenant, stage):
        d = _mk_deal(db_session, test_tenant.tenant_id, stage.stage_id)
        resp = client.post(f"/api/v1/deals/{d.deal_id}/assign", headers=operator_headers, json={"user_id": viewer_user.user_id})
        assert resp.status_code == 403

    def test_assigned_deal_is_not_unclaimed(self, client, db_session, auth_headers, operator_user, test_tenant, stage):
        # Assigning an owner (but not claiming) → deal is no longer "Unclaimed" (open pool).
        d = _mk_deal(db_session, test_tenant.tenant_id, stage.stage_id)
        resp = client.post(f"/api/v1/deals/{d.deal_id}/assign", headers=auth_headers, json={"user_id": operator_user.user_id})
        assert resp.status_code == 200
        assert resp.json()["is_unclaimed"] is False


class TestListFilters:
    def test_numeric_and_claimed_filters(self, client, db_session, auth_headers, operator_user, test_tenant, stage):
        _mk_deal(db_session, test_tenant.tenant_id, stage.stage_id, name="Cheap", value=100, probability=10)
        _mk_deal(db_session, test_tenant.tenant_id, stage.stage_id, name="Rich", value=9000, probability=90,
                 claimed_by_user_id=operator_user.user_id)
        # value > 1000
        rows = client.get("/api/v1/deals?value_op=gt&value_val=1000", headers=auth_headers).json()["items"]
        assert [r["name"] for r in rows] == ["Rich"]
        # probability between 0 and 50
        rows = client.get("/api/v1/deals?probability_op=between&probability_val=0&probability_val2=50", headers=auth_headers).json()["items"]
        assert [r["name"] for r in rows] == ["Cheap"]
        # unclaimed only = open pool (no claimer AND no owner)
        rows = client.get("/api/v1/deals?claimed_by=unclaimed", headers=auth_headers).json()["items"]
        assert [r["name"] for r in rows] == ["Cheap"]
        # search
        rows = client.get("/api/v1/deals?search=rich", headers=auth_headers).json()["items"]
        assert [r["name"] for r in rows] == ["Rich"]

    def test_unclaimed_filter_excludes_assigned(self, client, db_session, auth_headers, operator_user, test_tenant, stage):
        _mk_deal(db_session, test_tenant.tenant_id, stage.stage_id, name="Open")
        _mk_deal(db_session, test_tenant.tenant_id, stage.stage_id, name="Assigned", owner_id=operator_user.user_id)
        rows = client.get("/api/v1/deals?claimed_by=unclaimed", headers=auth_headers).json()["items"]
        assert [r["name"] for r in rows] == ["Open"]  # assigned deal is not in the open pool

    def test_mine_returns_claimed_or_owned(self, client, db_session, operator_headers, operator_user, test_tenant, stage):
        _mk_deal(db_session, test_tenant.tenant_id, stage.stage_id, name="Claimed", claimed_by_user_id=operator_user.user_id)
        _mk_deal(db_session, test_tenant.tenant_id, stage.stage_id, name="Owned", owner_id=operator_user.user_id)
        _mk_deal(db_session, test_tenant.tenant_id, stage.stage_id, name="Neither")
        rows = client.get("/api/v1/deals?mine=true", headers=operator_headers).json()["items"]
        assert sorted(r["name"] for r in rows) == ["Claimed", "Owned"]
