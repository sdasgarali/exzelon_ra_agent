"""Auto-action unsubscribe tests (ELR-014).

An opt-out must be actioned synchronously: suppress the address, mark the contact
UNSUBSCRIBED, and cancel pending campaign enrollments so no further email is sent.
"""
import pytest

from app.services.reply_tracker import apply_unsubscribe
from app.db.models.contact import ContactDetails, OutreachStatus as ContactOutreachStatus
from app.db.models.suppression import SuppressionList
from app.db.models.campaign import Campaign, CampaignContact, CampaignContactStatus

pytestmark = pytest.mark.integration


def _contact(db, tid, email="Foo@Bar.com"):
    c = ContactDetails(tenant_id=tid, client_name="C", first_name="F", last_name="L", email=email)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def test_apply_unsubscribe_suppresses_marks_and_cancels(db_session, test_tenant):
    tid = test_tenant.tenant_id
    contact = _contact(db_session, tid)
    campaign = Campaign(tenant_id=tid, name="C1")
    db_session.add(campaign)
    db_session.commit()
    db_session.refresh(campaign)
    enrollment = CampaignContact(
        campaign_id=campaign.campaign_id, contact_id=contact.contact_id,
        status=CampaignContactStatus.ACTIVE,
    )
    db_session.add(enrollment)
    db_session.commit()

    apply_unsubscribe(db_session, contact)
    db_session.commit()

    # 1. suppressed (lowercased)
    assert db_session.query(SuppressionList).filter(
        SuppressionList.email == "foo@bar.com").count() == 1
    # 2. contact marked unsubscribed
    db_session.refresh(contact)
    assert contact.outreach_status == ContactOutreachStatus.UNSUBSCRIBED
    assert contact.unsubscribed_at is not None
    # 3. pending enrollment cancelled
    db_session.refresh(enrollment)
    assert enrollment.status == CampaignContactStatus.UNSUBSCRIBED


def test_apply_unsubscribe_is_idempotent(db_session, test_tenant):
    tid = test_tenant.tenant_id
    contact = _contact(db_session, tid, email="dup@x.com")
    apply_unsubscribe(db_session, contact)
    apply_unsubscribe(db_session, contact)
    db_session.commit()
    # Only one suppression row despite two calls.
    assert db_session.query(SuppressionList).filter(
        SuppressionList.email == "dup@x.com").count() == 1
