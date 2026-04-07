"""Tests for per-domain send throttle service."""
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from app.services.domain_throttle import (
    check_domain_throttle,
    get_domain_send_counts,
    MAJOR_PROVIDER_DOMAINS,
)
from app.db.models.outreach import OutreachEvent, OutreachStatus, OutreachChannel
from app.db.models.contact import ContactDetails


pytestmark = pytest.mark.unit


def _make_contact(db, tenant_id, email, name="Test"):
    """Helper to create a ContactDetails with required fields."""
    c = ContactDetails(
        tenant_id=tenant_id,
        email=email,
        first_name=name,
        last_name="User",
        client_name="Test Co",
    )
    db.add(c)
    db.flush()
    return c


class TestMajorProviderDomains:
    """Test domain categorization."""

    def test_gmail_is_major(self):
        assert "gmail.com" in MAJOR_PROVIDER_DOMAINS

    def test_outlook_is_major(self):
        assert "outlook.com" in MAJOR_PROVIDER_DOMAINS

    def test_yahoo_is_major(self):
        assert "yahoo.com" in MAJOR_PROVIDER_DOMAINS


class TestCheckDomainThrottle:
    """Test per-domain throttle enforcement."""

    def test_allows_when_no_sends(self, db_session, test_tenant):
        allowed, reason = check_domain_throttle(
            db_session, "user@gmail.com", test_tenant.tenant_id,
        )
        assert allowed is True
        assert reason == ""

    def test_allows_under_limit(self, db_session, test_tenant):
        for i in range(5):
            c = _make_contact(db_session, test_tenant.tenant_id, f"user{i}@gmail.com", f"User{i}")
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

        allowed, reason = check_domain_throttle(
            db_session, "newuser@gmail.com", test_tenant.tenant_id,
        )
        assert allowed is True

    def test_blocks_at_major_provider_limit(self, db_session, test_tenant):
        # Major provider limit is 30 by default
        for i in range(31):
            c = _make_contact(db_session, test_tenant.tenant_id, f"person{i}@gmail.com", f"Person{i}")
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

        allowed, reason = check_domain_throttle(
            db_session, "another@gmail.com", test_tenant.tenant_id,
        )
        assert allowed is False
        assert "gmail.com" in reason.lower()

    def test_invalid_email_allowed(self, db_session, test_tenant):
        allowed, reason = check_domain_throttle(
            db_session, "not-an-email", test_tenant.tenant_id,
        )
        assert allowed is True


class TestGetDomainSendCounts:
    """Test domain send count aggregation."""

    def test_empty_returns_empty(self, db_session, test_tenant):
        counts = get_domain_send_counts(db_session, test_tenant.tenant_id)
        assert counts == {}

    def test_counts_by_domain(self, db_session, test_tenant):
        domains = {"gmail.com": 3, "outlook.com": 2}
        for domain, count in domains.items():
            for i in range(count):
                c = _make_contact(db_session, test_tenant.tenant_id, f"user{i}@{domain}", f"User{i}")
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

        counts = get_domain_send_counts(db_session, test_tenant.tenant_id)
        assert counts.get("gmail.com", 0) == 3
        assert counts.get("outlook.com", 0) == 2
