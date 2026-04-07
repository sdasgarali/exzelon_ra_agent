"""Tests for campaign safety controls — idempotency, caps, pause, fatigue, dedup."""
import pytest
from datetime import datetime, timedelta, date
from unittest.mock import MagicMock

from app.services.campaign_safety import (
    get_idempotency_key,
    check_company_contact_cap,
    check_reply_received,
    pause_contact_on_reply,
    check_sequence_fatigue,
    check_cross_campaign_conflict,
)
from app.db.models.campaign import CampaignContact, CampaignContactStatus, Campaign
from app.db.models.outreach import OutreachEvent, OutreachStatus, OutreachChannel
from app.db.models.contact import ContactDetails
from app.db.models.inbox_message import InboxMessage, MessageDirection


pytestmark = pytest.mark.unit


def _make_contact(db, tenant_id, email, client_name="Test Co", first_name="Test"):
    """Helper to create a ContactDetails with required fields."""
    c = ContactDetails(
        tenant_id=tenant_id,
        email=email,
        first_name=first_name,
        last_name="User",
        client_name=client_name,
    )
    db.add(c)
    db.flush()
    return c


class TestIdempotencyKey:
    """Test idempotency key generation."""

    def test_generates_key_with_cc_step_date(self):
        cc = MagicMock()
        cc.id = 42
        cc.current_step = 3
        key = get_idempotency_key(cc)
        assert "cc:42" in key
        assert "step:3" in key
        assert date.today().isoformat() in key

    def test_different_steps_different_keys(self):
        cc1 = MagicMock(id=1, current_step=1)
        cc2 = MagicMock(id=1, current_step=2)
        assert get_idempotency_key(cc1) != get_idempotency_key(cc2)

    def test_different_contacts_different_keys(self):
        cc1 = MagicMock(id=1, current_step=1)
        cc2 = MagicMock(id=2, current_step=1)
        assert get_idempotency_key(cc1) != get_idempotency_key(cc2)


class TestCompanyContactCap:
    """Test company-level contact cap checks."""

    def test_allows_when_unknown_company(self, db_session, test_tenant):
        contact = _make_contact(
            db_session, test_tenant.tenant_id,
            "test@example.com", client_name="unknown",
        )
        db_session.commit()

        allowed, reason = check_company_contact_cap(
            db_session, contact, test_tenant.tenant_id,
        )
        assert allowed is True

    def test_allows_under_cap(self, db_session, test_tenant):
        contact = _make_contact(
            db_session, test_tenant.tenant_id,
            "test@acme.com", client_name="Acme Corp",
        )
        db_session.commit()

        allowed, reason = check_company_contact_cap(
            db_session, contact, test_tenant.tenant_id, max_per_company=5,
        )
        assert allowed is True

    def test_blocks_at_cap(self, db_session, test_tenant):
        # Create contacts with outreach at same company
        for i in range(5):
            c = _make_contact(
                db_session, test_tenant.tenant_id,
                f"person{i}@acme.com", client_name="Acme Corp", first_name=f"Person{i}",
            )
            event = OutreachEvent(
                tenant_id=test_tenant.tenant_id,
                contact_id=c.contact_id,
                channel=OutreachChannel.SMTP,
                subject="Test",
                status=OutreachStatus.SENT,
                sent_at=datetime.utcnow(),
            )
            db_session.add(event)
        db_session.commit()

        # New contact at same company
        new_contact = _make_contact(
            db_session, test_tenant.tenant_id,
            "new@acme.com", client_name="Acme Corp", first_name="New",
        )
        db_session.commit()

        allowed, reason = check_company_contact_cap(
            db_session, new_contact, test_tenant.tenant_id, max_per_company=5,
        )
        assert allowed is False
        assert "cap reached" in reason.lower()


class TestReplyReceived:
    """Test reply detection for smart pause."""

    def test_no_reply(self, db_session, test_tenant):
        has_reply = check_reply_received(db_session, contact_id=999, campaign_id=999)
        assert has_reply is False

    def test_detects_reply(self, db_session, test_tenant):
        contact = _make_contact(
            db_session, test_tenant.tenant_id,
            "replier@example.com",
        )
        db_session.commit()

        msg = InboxMessage(
            tenant_id=test_tenant.tenant_id,
            contact_id=contact.contact_id,
            campaign_id=1,
            direction=MessageDirection.RECEIVED,
            from_email="replier@example.com",
            to_email="sender@ourco.com",
            subject="Re: Hello",
            received_at=datetime.utcnow(),
            thread_id="thread-123",
        )
        db_session.add(msg)
        db_session.commit()

        has_reply = check_reply_received(
            db_session, contact.contact_id, campaign_id=1,
        )
        assert has_reply is True


class TestPauseContactOnReply:
    """Test contact pause behavior."""

    def test_pauses_active_contact(self):
        cc = MagicMock()
        cc.status = CampaignContactStatus.ACTIVE
        cc.next_send_at = datetime.utcnow()

        pause_contact_on_reply(MagicMock(), cc)

        assert cc.status == CampaignContactStatus.PAUSED
        assert cc.next_send_at is None

    def test_no_change_if_already_paused(self):
        cc = MagicMock()
        cc.status = CampaignContactStatus.PAUSED
        original_status = cc.status

        pause_contact_on_reply(MagicMock(), cc)

        assert cc.status == original_status


class TestSequenceFatigue:
    """Test sequence fatigue detection."""

    def test_allows_when_few_sends(self, db_session, test_tenant):
        contact = _make_contact(db_session, test_tenant.tenant_id, "fresh@example.com")

        for i in range(2):
            event = OutreachEvent(
                tenant_id=test_tenant.tenant_id,
                contact_id=contact.contact_id,
                channel=OutreachChannel.SMTP,
                subject="Test",
                status=OutreachStatus.SENT,
                sent_at=datetime.utcnow() - timedelta(days=i),
            )
            db_session.add(event)
        db_session.commit()

        should_send, reason = check_sequence_fatigue(
            db_session, contact.contact_id, test_tenant.tenant_id,
        )
        assert should_send is True

    def test_blocks_when_too_many_unanswered(self, db_session, test_tenant):
        contact = _make_contact(db_session, test_tenant.tenant_id, "fatigued@example.com")

        for i in range(6):
            event = OutreachEvent(
                tenant_id=test_tenant.tenant_id,
                contact_id=contact.contact_id,
                channel=OutreachChannel.SMTP,
                subject="Test",
                status=OutreachStatus.SENT,
                sent_at=datetime.utcnow() - timedelta(days=i),
            )
            db_session.add(event)
        db_session.commit()

        should_send, reason = check_sequence_fatigue(
            db_session, contact.contact_id, test_tenant.tenant_id,
            max_unanswered=5,
        )
        assert should_send is False
        assert "fatigue" in reason.lower()

    def test_allows_if_contact_replied(self, db_session, test_tenant):
        contact = _make_contact(db_session, test_tenant.tenant_id, "replied@example.com")

        for i in range(6):
            event = OutreachEvent(
                tenant_id=test_tenant.tenant_id,
                contact_id=contact.contact_id,
                channel=OutreachChannel.SMTP,
                subject="Test",
                status=OutreachStatus.SENT,
                sent_at=datetime.utcnow() - timedelta(days=i),
            )
            db_session.add(event)

        reply = InboxMessage(
            tenant_id=test_tenant.tenant_id,
            contact_id=contact.contact_id,
            direction=MessageDirection.RECEIVED,
            from_email="replied@example.com",
            to_email="us@ourco.com",
            subject="Re: Test",
            received_at=datetime.utcnow() - timedelta(days=2),
            thread_id="thread-456",
        )
        db_session.add(reply)
        db_session.commit()

        should_send, reason = check_sequence_fatigue(
            db_session, contact.contact_id, test_tenant.tenant_id,
            max_unanswered=5,
        )
        assert should_send is True


class TestCrossCampaignConflict:
    """Test cross-campaign contact dedup."""

    def test_allows_when_no_other_campaigns(self, db_session, test_tenant):
        allowed, reason = check_cross_campaign_conflict(
            db_session, contact_id=1, campaign_id=1,
        )
        assert allowed is True

    def test_blocks_when_active_in_other(self, db_session, test_tenant):
        campaign1 = Campaign(
            tenant_id=test_tenant.tenant_id,
            name="Campaign A",
            status="active",
        )
        campaign2 = Campaign(
            tenant_id=test_tenant.tenant_id,
            name="Campaign B",
            status="active",
        )
        db_session.add_all([campaign1, campaign2])
        db_session.commit()

        contact = _make_contact(db_session, test_tenant.tenant_id, "multi@example.com")
        db_session.commit()

        cc = CampaignContact(
            campaign_id=campaign1.campaign_id,
            contact_id=contact.contact_id,
            status=CampaignContactStatus.ACTIVE,
        )
        db_session.add(cc)
        db_session.commit()

        allowed, reason = check_cross_campaign_conflict(
            db_session, contact.contact_id, campaign2.campaign_id,
        )
        assert allowed is False
        assert "Campaign A" in reason
