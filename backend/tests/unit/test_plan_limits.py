"""Plan-limit enforcement tests (ELR-011).

The shared `test_tenant` fixture is always ENTERPRISE, which short-circuits
`check_plan_limit` — so before this file the cap-enforcement branches had ZERO
coverage. These use the `starter_tenant` / `professional_capped_tenant` fixtures.
"""
import pytest
from fastapi import HTTPException

from app.api.deps.plan_limits import check_plan_limit
from app.db.models.contact import ContactDetails

pytestmark = pytest.mark.unit


def _add_contacts(db, tenant_id, n):
    for i in range(n):
        db.add(ContactDetails(
            tenant_id=tenant_id, client_name="C", first_name="F",
            last_name="L", email=f"c{i}-{tenant_id}@x.com",
        ))
    db.commit()


def test_unconfigured_limits_fall_back_to_plan(db_session, starter_tenant):
    """Regression: a tenant whose max_* columns are all 0 must NOT be locked out.

    `0` used to mean "locked" on the starter plan, so `create_tenant_for_signup()`
    — which provisioned exactly those zeroes — made every self-signup account unable
    to add a mailbox, lead, contact or campaign. `0` now means "not configured", and
    the plan's own number applies.
    """
    check_plan_limit(db_session, starter_tenant.tenant_id, "contacts")  # no raise
    check_plan_limit(db_session, starter_tenant.tenant_id, "mailboxes")
    check_plan_limit(db_session, starter_tenant.tenant_id, "campaigns")
    check_plan_limit(db_session, starter_tenant.tenant_id, "lobs")


def test_free_plan_still_caps_at_its_number(db_session, starter_tenant):
    """...but the Free plan's own cap is real. Free allows 1 mailbox."""
    from app.db.models.sender_mailbox import SenderMailbox
    db_session.add(SenderMailbox(tenant_id=starter_tenant.tenant_id, email="a@x.com"))
    db_session.commit()
    with pytest.raises(HTTPException) as exc:
        check_plan_limit(db_session, starter_tenant.tenant_id, "mailboxes")
    assert exc.value.status_code == 403
    assert "1/1" in exc.value.detail


def test_max_plan_generous_but_not_unlimited(db_session, test_tenant):
    # test_tenant resolves to the Max plan and is nowhere near its caps.
    check_plan_limit(db_session, test_tenant.tenant_id, "contacts")

    from app.core.plans import PLAN_MATRIX
    # No tier is unlimited any more — every Max limit is a real positive number.
    spec = PLAN_MATRIX["max"]
    assert spec.max_mailboxes == 1000
    # Seats and lines of business are not sold on any tier (2026-09-23).
    assert spec.max_users == 1
    assert spec.max_lobs == 1
    assert spec.max_campaigns == 100


def test_super_admin_bypass(db_session):
    check_plan_limit(db_session, None, "contacts")


def test_professional_cap_reached_raises_403(db_session, professional_capped_tenant):
    tid = professional_capped_tenant.tenant_id  # max_contacts = 2
    _add_contacts(db_session, tid, 2)
    with pytest.raises(HTTPException) as exc:
        check_plan_limit(db_session, tid, "contacts")
    assert exc.value.status_code == 403


def test_professional_under_cap_passes(db_session, professional_capped_tenant):
    tid = professional_capped_tenant.tenant_id  # max_contacts = 2
    _add_contacts(db_session, tid, 1)
    check_plan_limit(db_session, tid, "contacts")  # no raise


# ---------------------------------------------------------------------------
# Campaigns count LIVE state, not lifetime (2026-09).
# ---------------------------------------------------------------------------

def _add_campaign(db, tenant_id, name, status):
    from app.db.models.campaign import Campaign
    db.add(Campaign(tenant_id=tenant_id, name=name, status=status))
    db.commit()


def test_completed_campaigns_release_their_slot(db_session, professional_capped_tenant):
    """The cap used to be a one-way ratchet.

    `RESOURCE_COUNTERS["campaigns"]` counted every campaign row a tenant had ever
    created, so finishing your campaigns permanently consumed the quota and left you
    locked out with nothing running. Only ACTIVE and PAUSED hold enrolments and get
    swept by the campaign engine, so only those occupy a slot.
    """
    from app.db.models.campaign import CampaignStatus
    tid = professional_capped_tenant.tenant_id  # max_campaigns = 2

    _add_campaign(db_session, tid, "done-1", CampaignStatus.COMPLETED)
    _add_campaign(db_session, tid, "done-2", CampaignStatus.COMPLETED)
    _add_campaign(db_session, tid, "archived", CampaignStatus.ARCHIVED)
    _add_campaign(db_session, tid, "draft", CampaignStatus.DRAFT)
    # Four rows exist, none of them live → still allowed to start a new one.
    check_plan_limit(db_session, tid, "campaigns")

    _add_campaign(db_session, tid, "live-1", CampaignStatus.ACTIVE)
    _add_campaign(db_session, tid, "live-2", CampaignStatus.PAUSED)
    with pytest.raises(HTTPException) as exc:
        check_plan_limit(db_session, tid, "campaigns")
    assert exc.value.status_code == 403
    assert "active campaigns" in exc.value.detail


# ---------------------------------------------------------------------------
# Lines of business are a metered resource (new in 2026-09).
# ---------------------------------------------------------------------------

def test_lob_cap_enforced(db_session, starter_tenant):
    """Free allows 1 line of business."""
    from app.db.models.line_of_business import LineOfBusiness, LOBType
    tid = starter_tenant.tenant_id

    check_plan_limit(db_session, tid, "lobs")  # none yet
    db_session.add(LineOfBusiness(
        tenant_id=tid, name="Staffing", slug="staffing", lob_type=LOBType.STAFFING,
    ))
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        check_plan_limit(db_session, tid, "lobs")
    assert exc.value.status_code == 403
    assert "lines of business" in exc.value.detail


def test_upgrade_hint_names_the_next_tier(db_session, starter_tenant):
    from app.db.models.line_of_business import LineOfBusiness, LOBType
    db_session.add(LineOfBusiness(
        tenant_id=starter_tenant.tenant_id, name="S", slug="s", lob_type=LOBType.STAFFING,
    ))
    db_session.commit()
    with pytest.raises(HTTPException) as exc:
        check_plan_limit(db_session, starter_tenant.tenant_id, "lobs")
    assert "Upgrade to Pro" in exc.value.detail


def test_new_limit_columns_default_to_use_the_plan(db_session):
    """A limit column added by a migration must default to 0, not to a tier's figure.

    `max_lobs` originally shipped with `server_default="1"`, which stamped an explicit
    one-LOB cap onto every existing row — and because a positive value beats the plan,
    that silently capped Max customers entitled to 25. Defaulting to 0 means
    "not configured", so the plan's number applies and the tenant self-heals.
    """
    from app.core.plans import PLAN_MATRIX, limits_for_tenant
    from app.db.models.tenant import Tenant, TenantPlan

    t = Tenant(name="Fresh Max", slug="fresh-max", plan=TenantPlan.MAX)
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)

    assert t.max_lobs == 0, "column default must mean 'use the plan'"
    assert limits_for_tenant(t)["max_lobs"] == PLAN_MATRIX["max"].max_lobs
    check_plan_limit(db_session, t.tenant_id, "lobs")  # not capped at 1
