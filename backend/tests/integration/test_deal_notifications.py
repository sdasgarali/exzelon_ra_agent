"""Tests for forwarding a new unclaimed deal to a tenant's BDMs/Recruiters."""
import pytest

from app.db.models.deal import Deal, DealStage
from app.db.models.notification import NotificationEntry
from app.db.models.settings import Settings
from app.services.deal_notifications import forward_new_deal_to_reps

pytestmark = pytest.mark.integration


def _deal(db, tenant_id):
    s = DealStage(tenant_id=tenant_id, name="New Lead", stage_order=1, color="#111")
    db.add(s)
    db.commit()
    db.refresh(s)
    d = Deal(tenant_id=tenant_id, name="Acme — Jane", stage_id=s.stage_id, value=0, probability=20)
    db.add(d)
    db.commit()
    db.refresh(d)
    return d


def _notifs(db, tenant_id):
    return db.query(NotificationEntry).filter(
        NotificationEntry.tenant_id == tenant_id,
        NotificationEntry.category == "deal",
    ).all()


class TestForwardNewDeal:
    def test_notifies_reps_not_admins(self, db_session, test_tenant, admin_user, operator_user, viewer_user):
        # admin_user=admin, operator_user=BDM, viewer_user=Recruiter (all tenant 1)
        # mute email in tests to avoid SMTP
        db_session.add(Settings(key="deal_notify_reps_email", value_json="false"))
        db_session.commit()
        d = _deal(db_session, test_tenant.tenant_id)
        n = forward_new_deal_to_reps(db_session, d, test_tenant.tenant_id)
        db_session.commit()
        assert n == 2  # BDM + Recruiter, not the admin
        recipients = {x.user_id for x in _notifs(db_session, test_tenant.tenant_id)}
        assert recipients == {operator_user.user_id, viewer_user.user_id}
        assert admin_user.user_id not in recipients

    def test_disabled_by_setting(self, db_session, test_tenant, operator_user):
        db_session.add(Settings(key="deal_notify_reps_on_new", value_json="false"))
        db_session.commit()
        d = _deal(db_session, test_tenant.tenant_id)
        n = forward_new_deal_to_reps(db_session, d, test_tenant.tenant_id)
        db_session.commit()
        assert n == 0
        assert _notifs(db_session, test_tenant.tenant_id) == []
