"""Tests for RA-only auto-send gating (OutreachRole.auto_outbound)."""
import pytest

from app.db.models.outreach_role import OutreachRole
from app.db.models.sender_mailbox import SenderMailbox, WarmupStatus
from app.services.mailbox_selector import select_best_mailbox

pytestmark = pytest.mark.integration


def _mailbox(db, tenant_id, email, role_id):
    mb = SenderMailbox(
        tenant_id=tenant_id, email=email, outreach_role_id=role_id,
        is_active=True, warmup_status=WarmupStatus.COLD_READY,
        daily_send_limit=30, emails_sent_today=0,
        connection_status="successful", is_blacklisted=False,
    )
    db.add(mb)
    db.commit()
    db.refresh(mb)
    return mb


@pytest.fixture
def roles_and_mailboxes(db_session, test_tenant):
    tid = test_tenant.tenant_id
    ra = OutreachRole(tenant_id=tid, role_name="RA", description="auto", auto_outbound=True)
    bdm = OutreachRole(tenant_id=tid, role_name="BDM", description="manual", auto_outbound=False)
    db_session.add_all([ra, bdm])
    db_session.commit()
    db_session.refresh(ra)
    db_session.refresh(bdm)
    ra_mb = _mailbox(db_session, tid, "ra@auto.com", ra.role_id)
    bdm_mb = _mailbox(db_session, tid, "bdm@manual.com", bdm.role_id)
    return {"ra": ra, "bdm": bdm, "ra_mb": ra_mb, "bdm_mb": bdm_mb}


class TestAutoSendGating:
    def test_auto_pool_only_selects_auto_outbound_role(self, db_session, roles_and_mailboxes):
        # No explicit mailbox ids → automated pool → only the RA (auto_outbound) mailbox.
        picked = select_best_mailbox([], db_session)
        assert picked is not None
        assert picked.mailbox_id == roles_and_mailboxes["ra_mb"].mailbox_id

    def test_explicit_assignment_bypasses_gate(self, db_session, roles_and_mailboxes):
        # Explicitly assigning the BDM mailbox (manual) still works.
        bdm_id = roles_and_mailboxes["bdm_mb"].mailbox_id
        picked = select_best_mailbox([bdm_id], db_session)
        assert picked is not None
        assert picked.mailbox_id == bdm_id

    def test_no_auto_outbound_mailbox_returns_none(self, db_session, test_tenant):
        # Only a non-auto_outbound role exists → nothing auto-selectable.
        bdm = OutreachRole(tenant_id=test_tenant.tenant_id, role_name="BDM", auto_outbound=False)
        db_session.add(bdm)
        db_session.commit()
        db_session.refresh(bdm)
        _mailbox(db_session, test_tenant.tenant_id, "only-bdm@x.com", bdm.role_id)
        assert select_best_mailbox([], db_session) is None


class TestOutreachRoleAutoOutboundApi:
    def test_create_and_toggle_auto_outbound(self, client, sa_headers, auth_headers):
        created = client.post("/api/v1/outreach-roles", headers=sa_headers,
                             json={"role_name": "Blaster", "auto_outbound": True}).json()
        assert created["auto_outbound"] is True
        role_id = created["role_id"]
        # list surfaces it
        listed = client.get("/api/v1/outreach-roles", headers=auth_headers).json()
        assert next(x for x in listed if x["role_id"] == role_id)["auto_outbound"] is True
        # toggle off
        upd = client.put(f"/api/v1/outreach-roles/{role_id}", headers=sa_headers,
                        json={"auto_outbound": False})
        assert upd.status_code == 200
        assert upd.json()["auto_outbound"] is False
