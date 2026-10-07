"""Demo seeding must be idempotent (prod logged 'Failed to seed demo data' on every start)."""
import pytest

from app.db.models.campaign import Campaign
from app.db.models.client import ClientInfo
from app.db.models.contact import ContactDetails
from app.db.models.deal import Deal
from app.db.models.email_template import EmailTemplate
from app.db.models.lead import LeadDetails
from app.services.demo_seeder import seed_demo_data

pytestmark = pytest.mark.integration


def _counts(db, tid):
    return {
        "clients": db.query(ClientInfo).filter(ClientInfo.tenant_id == tid).count(),
        "leads": db.query(LeadDetails).filter(LeadDetails.tenant_id == tid).count(),
        "contacts": db.query(ContactDetails).filter(ContactDetails.tenant_id == tid).count(),
        "templates": db.query(EmailTemplate).filter(EmailTemplate.tenant_id == tid).count(),
        "campaigns": db.query(Campaign).filter(Campaign.tenant_id == tid).count(),
        "deals": db.query(Deal).filter(Deal.tenant_id == tid).count(),
    }


def test_first_seed_creates_everything(db_session, test_tenant):
    result = seed_demo_data(test_tenant.tenant_id, db_session)
    assert result == {"clients": 10, "leads": 25, "contacts": 15,
                      "templates": 2, "campaigns": 1, "deals": 5}
    assert _counts(db_session, test_tenant.tenant_id) == result


def test_seeding_twice_is_a_noop(db_session, test_tenant):
    seed_demo_data(test_tenant.tenant_id, db_session)
    before = _counts(db_session, test_tenant.tenant_id)
    second = seed_demo_data(test_tenant.tenant_id, db_session)
    assert all(v == 0 for v in second.values()), second
    assert _counts(db_session, test_tenant.tenant_id) == before


def test_existing_client_without_leads_does_not_fail(db_session, test_tenant, monkeypatch):
    """The prod case: tenant has 'TechCorp Solutions' but no leads -> IntegrityError on
    idx_client_tenant_name every start. Now the existing client is reused."""
    tid = test_tenant.tenant_id
    existing = ClientInfo(tenant_id=tid, client_name="TechCorp Solutions", industry="Real Co")
    db_session.add(existing)
    db_session.commit()

    from app.services import demo_seeder
    errors = []
    monkeypatch.setattr(demo_seeder.logger, "error", lambda *a, **k: errors.append((a, k)))

    result = seed_demo_data(tid, db_session)
    assert errors == []
    assert result["clients"] == 9  # the existing one was reused, not duplicated
    rows = db_session.query(ClientInfo).filter(
        ClientInfo.tenant_id == tid, ClientInfo.client_name == "TechCorp Solutions").all()
    assert len(rows) == 1 and rows[0].industry == "Real Co"  # untouched
    assert result["leads"] == 25

    again = seed_demo_data(tid, db_session)
    assert all(v == 0 for v in again.values()), again
    assert errors == []


def test_tenant_with_real_leads_is_left_alone(db_session, test_tenant, sample_lead):
    result = seed_demo_data(test_tenant.tenant_id, db_session)
    assert all(v == 0 for v in result.values())
    assert db_session.query(ClientInfo).filter(ClientInfo.tenant_id == test_tenant.tenant_id).count() == 0


def test_concurrent_insert_is_absorbed(db_session, test_tenant, monkeypatch):
    """Two API workers seeding at once: our lookup misses, the insert hits the unique
    index, and the row the other worker wrote is returned instead of failing."""
    from app.services.demo_seeder import _get_or_create

    tid = test_tenant.tenant_id
    winner = ClientInfo(tenant_id=tid, client_name="Race Co")
    db_session.add(winner)
    db_session.commit()

    real_query = db_session.query
    calls = {"n": 0}

    class _Miss:
        def filter_by(self, **_):
            return self

        def first(self):
            return None

    def fake_query(*a, **k):
        calls["n"] += 1
        return _Miss() if calls["n"] == 1 else real_query(*a, **k)

    monkeypatch.setattr(db_session, "query", fake_query)
    row, created = _get_or_create(db_session, ClientInfo, {"tenant_id": tid, "client_name": "Race Co"},
                                  lambda: ClientInfo(tenant_id=tid, client_name="Race Co"))
    monkeypatch.undo()
    assert created is False and row.client_id == winner.client_id
    assert db_session.query(ClientInfo).filter(ClientInfo.client_name == "Race Co").count() == 1


def test_seeding_one_tenant_does_not_touch_another(db_session, test_tenant, starter_tenant):
    seed_demo_data(test_tenant.tenant_id, db_session)
    result = seed_demo_data(starter_tenant.tenant_id, db_session)
    assert result["clients"] == 10 and result["leads"] == 25
