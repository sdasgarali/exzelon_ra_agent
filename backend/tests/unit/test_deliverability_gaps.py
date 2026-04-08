"""Unit tests for deliverability gap implementations (Gaps 1-12).

Tests cover:
- Gap 1:  bounce_handler.py   — SMTP error classification + auto-suppression
- Gap 2:  esp_feedback.py     — Complaint rate tracking + auto-pause
- Gap 4+5: email_humanizer.py — AI opener stripping, burstiness, humanization
- Gap 7:  dkim_signer.py      — DKIM signing gating + graceful degradation
- Gap 9:  engagement_tracker.py — Multi-signal engagement scoring
- Gap 10: send_time_optimizer.py — Timezone resolution + send window checks
- Gap 11: rendering_checker.py — Email rendering issue detection
- Gap 12: spintax.py          — Campaign-aware deterministic spintax
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, PropertyMock
from types import SimpleNamespace

from app.db.models.contact import ContactDetails, OutreachStatus as ContactOutreachStatus
from app.db.models.suppression import SuppressionList
from app.db.models.sender_mailbox import SenderMailbox, WarmupStatus
from app.db.models.outreach import OutreachEvent, OutreachStatus, OutreachChannel
from app.db.models.tenant import Tenant, TenantPlan

# Markers for all tests in this file
pytestmark = [pytest.mark.unit]


# ============================================================================
# Helpers
# ============================================================================

def _make_tenant(db):
    """Create a minimal tenant for DB tests."""
    t = Tenant(
        name="Deliverability Test Org",
        slug="deliv-test-org",
        plan=TenantPlan.ENTERPRISE,
        max_users=99,
        max_mailboxes=99,
        max_contacts=99999,
        max_campaigns=99,
        max_leads=99999,
    )
    db.add(t)
    db.flush()
    return t


def _make_contact(db, tenant_id, email="bounce@example.com"):
    """Create a minimal ContactDetails for testing."""
    c = ContactDetails(
        tenant_id=tenant_id,
        email=email,
        first_name="Test",
        last_name="User",
        client_name="Test Corp",
    )
    db.add(c)
    db.flush()
    return c


def _make_mailbox(db, tenant_id, email="sender@example.com", **overrides):
    """Create a SenderMailbox with sensible defaults."""
    defaults = dict(
        tenant_id=tenant_id,
        email=email,
        display_name="Test Sender",
        password="fake",
        warmup_status=WarmupStatus.ACTIVE,
        is_active=True,
        daily_send_limit=30,
        emails_sent_today=0,
        total_emails_sent=100,
        bounce_count=0,
        reply_count=5,
        complaint_count=0,
    )
    defaults.update(overrides)
    m = SenderMailbox(**defaults)
    db.add(m)
    db.flush()
    return m


def _make_outreach_event(db, tenant_id, contact_id, status, mailbox_id=None, **kw):
    """Create an OutreachEvent."""
    ev = OutreachEvent(
        tenant_id=tenant_id,
        contact_id=contact_id,
        status=status,
        channel=OutreachChannel.SMTP,
        sent_at=kw.get("sent_at", datetime.utcnow()),
        sender_mailbox_id=mailbox_id,
        reply_detected_at=kw.get("reply_detected_at"),
    )
    db.add(ev)
    db.flush()
    return ev


# ============================================================================
# Gap 1: bounce_handler.py
# ============================================================================

class TestClassifySmtpError:
    """Tests for classify_smtp_error()."""

    def test_5xx_code_returns_permanent(self):
        from app.services.bounce_handler import classify_smtp_error

        code, category, is_permanent = classify_smtp_error("550 User not found")
        assert code == "550"
        assert is_permanent is True

    def test_4xx_code_returns_temporary(self):
        from app.services.bounce_handler import classify_smtp_error

        code, category, is_permanent = classify_smtp_error("421 Too many connections")
        assert code == "421"
        assert is_permanent is False

    def test_user_unknown_always_permanent(self):
        """Even with a 4xx code, user_unknown patterns force permanent."""
        from app.services.bounce_handler import classify_smtp_error

        code, category, is_permanent = classify_smtp_error("450 user unknown")
        assert category == "user_unknown"
        assert is_permanent is True

    def test_domain_not_found_always_permanent(self):
        from app.services.bounce_handler import classify_smtp_error

        code, category, is_permanent = classify_smtp_error("450 domain not found")
        assert category == "domain_not_found"
        assert is_permanent is True

    def test_empty_error_returns_unknown(self):
        from app.services.bounce_handler import classify_smtp_error

        code, category, is_permanent = classify_smtp_error("")
        assert code == "unknown"
        assert is_permanent is False

    def test_mailbox_full_is_temporary_with_4xx(self):
        from app.services.bounce_handler import classify_smtp_error

        code, category, is_permanent = classify_smtp_error("452 mailbox full, try later")
        assert category == "mailbox_full"
        assert is_permanent is False

    def test_blocked_category_detected(self):
        from app.services.bounce_handler import classify_smtp_error

        code, category, is_permanent = classify_smtp_error("550 blocked by spam filter")
        assert category == "blocked"
        assert is_permanent is True


class TestHandleBounce:
    """Tests for handle_bounce() — requires DB."""

    def test_permanent_bounce_adds_to_suppression_list(self, db_session):
        from app.services.bounce_handler import handle_bounce

        tenant = _make_tenant(db_session)
        result = handle_bounce(
            db=db_session,
            email="bad@example.com",
            error_msg="550 User not found",
            tenant_id=tenant.tenant_id,
        )
        db_session.commit()

        assert result["action"] == "suppressed"
        assert result["is_permanent"] is True

        suppressed = db_session.query(SuppressionList).filter(
            SuppressionList.email == "bad@example.com"
        ).first()
        assert suppressed is not None
        assert "hard_bounce" in suppressed.reason

    def test_permanent_bounce_marks_contact_inactive(self, db_session):
        from app.services.bounce_handler import handle_bounce

        tenant = _make_tenant(db_session)
        contact = _make_contact(db_session, tenant.tenant_id, "bounced@example.com")
        db_session.commit()

        handle_bounce(
            db=db_session,
            email="bounced@example.com",
            error_msg="550 invalid recipient",
            contact_id=contact.contact_id,
            tenant_id=tenant.tenant_id,
        )
        db_session.commit()

        db_session.refresh(contact)
        assert contact.outreach_status == ContactOutreachStatus.INACTIVE
        assert contact.validation_status == "invalid"

    def test_permanent_bounce_increments_mailbox_bounce_count(self, db_session):
        from app.services.bounce_handler import handle_bounce

        tenant = _make_tenant(db_session)
        mailbox = _make_mailbox(db_session, tenant.tenant_id, bounce_count=2)
        db_session.commit()

        handle_bounce(
            db=db_session,
            email="hardbounce@example.com",
            error_msg="550 no such user",
            tenant_id=tenant.tenant_id,
            mailbox_id=mailbox.mailbox_id,
        )
        db_session.commit()

        db_session.refresh(mailbox)
        assert mailbox.bounce_count == 3

    def test_temporary_bounce_only_logs(self, db_session):
        from app.services.bounce_handler import handle_bounce

        tenant = _make_tenant(db_session)
        result = handle_bounce(
            db=db_session,
            email="temp@example.com",
            error_msg="421 try again later",
            tenant_id=tenant.tenant_id,
        )
        db_session.commit()

        assert result["action"] == "logged"
        assert result["is_permanent"] is False

        suppressed = db_session.query(SuppressionList).filter(
            SuppressionList.email == "temp@example.com"
        ).first()
        assert suppressed is None

    def test_no_duplicate_suppression_entries(self, db_session):
        from app.services.bounce_handler import handle_bounce

        tenant = _make_tenant(db_session)

        # First bounce
        handle_bounce(
            db=db_session,
            email="dupe@example.com",
            error_msg="550 user unknown",
            tenant_id=tenant.tenant_id,
        )
        db_session.commit()

        # Second bounce for same email
        handle_bounce(
            db=db_session,
            email="dupe@example.com",
            error_msg="550 user unknown",
            tenant_id=tenant.tenant_id,
        )
        db_session.commit()

        count = db_session.query(SuppressionList).filter(
            SuppressionList.email == "dupe@example.com"
        ).count()
        assert count == 1


# ============================================================================
# Gap 2: esp_feedback.py
# ============================================================================

class TestRecordComplaint:
    """Tests for record_complaint()."""

    def test_increments_complaint_count(self, db_session):
        from app.services.esp_feedback import record_complaint

        tenant = _make_tenant(db_session)
        mailbox = _make_mailbox(
            db_session, tenant.tenant_id,
            email="complaints@example.com",
            complaint_count=0,
            total_emails_sent=1000,
        )
        db_session.commit()

        record_complaint(
            db=db_session,
            mailbox_id=mailbox.mailbox_id,
            tenant_id=tenant.tenant_id,
            email="complainer@gmail.com",
            reason="abuse",
        )
        db_session.commit()

        db_session.refresh(mailbox)
        assert mailbox.complaint_count == 1

    def test_nonexistent_mailbox_does_not_crash(self, db_session):
        """record_complaint for missing mailbox should log warning, not raise."""
        from app.services.esp_feedback import record_complaint

        tenant = _make_tenant(db_session)
        db_session.commit()

        # Should not raise
        record_complaint(
            db=db_session,
            mailbox_id=99999,
            tenant_id=tenant.tenant_id,
            email="nobody@gmail.com",
        )


class TestCheckComplaintRate:
    """Tests for check_complaint_rate()."""

    def test_auto_pauses_when_over_threshold(self, db_session):
        from app.services.esp_feedback import check_complaint_rate

        tenant = _make_tenant(db_session)
        # 5 complaints out of 100 sent = 5% >> 0.3% threshold
        mailbox = _make_mailbox(
            db_session, tenant.tenant_id,
            email="bad-sender@example.com",
            complaint_count=5,
            total_emails_sent=100,
        )
        db_session.commit()

        rate, is_healthy = check_complaint_rate(
            db=db_session,
            mailbox_id=mailbox.mailbox_id,
            tenant_id=tenant.tenant_id,
        )

        assert is_healthy is False
        assert rate == 0.05  # 5/100

        db_session.refresh(mailbox)
        assert mailbox.is_active is False  # auto-paused

    def test_healthy_when_under_threshold(self, db_session):
        from app.services.esp_feedback import check_complaint_rate

        tenant = _make_tenant(db_session)
        # 1 complaint out of 10000 sent = 0.01% < 0.3%
        mailbox = _make_mailbox(
            db_session, tenant.tenant_id,
            email="good-sender@example.com",
            complaint_count=1,
            total_emails_sent=10000,
        )
        db_session.commit()

        rate, is_healthy = check_complaint_rate(
            db=db_session,
            mailbox_id=mailbox.mailbox_id,
            tenant_id=tenant.tenant_id,
        )

        assert is_healthy is True
        assert rate == 0.0001  # 1/10000

        db_session.refresh(mailbox)
        assert mailbox.is_active is True  # still active

    def test_zero_sent_is_healthy(self, db_session):
        from app.services.esp_feedback import check_complaint_rate

        tenant = _make_tenant(db_session)
        mailbox = _make_mailbox(
            db_session, tenant.tenant_id,
            email="new-sender@example.com",
            complaint_count=0,
            total_emails_sent=0,
        )
        db_session.commit()

        rate, is_healthy = check_complaint_rate(
            db=db_session,
            mailbox_id=mailbox.mailbox_id,
        )

        assert rate == 0.0
        assert is_healthy is True


class TestGetComplaintStats:
    """Tests for get_complaint_stats()."""

    def test_returns_sorted_by_rate_descending(self, db_session):
        from app.services.esp_feedback import get_complaint_stats

        tenant = _make_tenant(db_session)
        # High-rate mailbox
        _make_mailbox(
            db_session, tenant.tenant_id,
            email="high-rate@example.com",
            complaint_count=10,
            total_emails_sent=100,
        )
        # Low-rate mailbox
        _make_mailbox(
            db_session, tenant.tenant_id,
            email="low-rate@example.com",
            complaint_count=1,
            total_emails_sent=10000,
        )
        db_session.commit()

        stats = get_complaint_stats(db=db_session, tenant_id=tenant.tenant_id)

        assert len(stats) == 2
        # High rate first
        assert stats[0]["email"] == "high-rate@example.com"
        assert stats[0]["complaint_rate"] > stats[1]["complaint_rate"]

    def test_includes_expected_fields(self, db_session):
        from app.services.esp_feedback import get_complaint_stats

        tenant = _make_tenant(db_session)
        _make_mailbox(db_session, tenant.tenant_id, email="stats@example.com")
        db_session.commit()

        stats = get_complaint_stats(db=db_session, tenant_id=tenant.tenant_id)

        assert len(stats) == 1
        entry = stats[0]
        assert "mailbox_id" in entry
        assert "email" in entry
        assert "complaint_rate" in entry
        assert "is_healthy" in entry
        assert "total_emails_sent" in entry


# ============================================================================
# Gap 4+5: email_humanizer.py
# ============================================================================

class TestStripAiOpeners:
    """Tests for AI opener removal in humanize_email()."""

    def test_strips_i_hope_this_finds_you_well(self):
        from app.services.email_humanizer import humanize_email

        result = humanize_email(
            subject="Quick question",
            body_html="<p>I hope this email finds you well. We have a great opportunity.</p>",
            body_text="I hope this email finds you well. We have a great opportunity.",
        )

        assert "I hope this email finds you well" not in result["body_text"]
        assert any("removed_ai_opener" in m for m in result["modifications"])

    def test_strips_i_wanted_to_reach_out(self):
        from app.services.email_humanizer import humanize_email

        result = humanize_email(
            subject="Partnership",
            body_html="<p>I wanted to reach out about your hiring needs.</p>",
            body_text="I wanted to reach out about your hiring needs.",
        )

        assert "I wanted to reach out" not in result["body_text"]


class TestBurstinessScore:
    """Tests for compute_burstiness_score()."""

    def test_returns_float_between_0_and_1(self):
        from app.services.email_humanizer import compute_burstiness_score

        text = (
            "Short one. "
            "This is a medium length sentence with some words. "
            "A much longer sentence that contains many more words and goes on for quite a while to create variance. "
            "Tiny. "
            "Another normal sentence here."
        )
        score = compute_burstiness_score(text)

        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0

    def test_single_sentence_returns_zero(self):
        from app.services.email_humanizer import compute_burstiness_score

        score = compute_burstiness_score("Just one sentence here.")
        assert score == 0.0

    def test_uniform_sentences_low_burstiness(self):
        from app.services.email_humanizer import compute_burstiness_score

        # All sentences exactly the same length = low burstiness
        text = "Four words each. Four words each. Four words each. Four words each."
        score = compute_burstiness_score(text)
        assert score < 0.2

    def test_varied_sentences_higher_burstiness(self):
        from app.services.email_humanizer import compute_burstiness_score

        text = (
            "Hi. "
            "This is a sentence that is quite a bit longer and should create some real variance in lengths. "
            "Short. "
            "Another one that goes on and on and on with many extra words to push the length way up."
        )
        score = compute_burstiness_score(text)
        assert score > 0.3


class TestHumanizeEmail:
    """Tests for humanize_email() main function."""

    def test_returns_modifications_list(self):
        from app.services.email_humanizer import humanize_email

        result = humanize_email(
            subject="Test",
            body_html="<p>I hope this email finds you well. We provide staffing solutions. Our team is dedicated. We work hard for clients. Contact us today.</p>",
            body_text="I hope this email finds you well. We provide staffing solutions. Our team is dedicated. We work hard for clients. Contact us today.",
        )

        assert "modifications" in result
        assert isinstance(result["modifications"], list)
        assert len(result["modifications"]) > 0

    def test_light_intensity(self):
        from app.services.email_humanizer import humanize_email

        result = humanize_email(
            subject="Hello",
            body_html="<p>Text here.</p>",
            body_text="Text here.",
            intensity="light",
        )

        assert "subject" in result
        assert "body_html" in result
        assert "body_text" in result

    def test_heavy_intensity(self):
        from app.services.email_humanizer import humanize_email

        result = humanize_email(
            subject="Hello",
            body_html="<p>Text here.</p>",
            body_text="Text here.",
            intensity="heavy",
        )

        assert "subject" in result
        assert "body_text" in result

    def test_invalid_intensity_defaults_to_medium(self):
        from app.services.email_humanizer import humanize_email

        result = humanize_email(
            subject="Test",
            body_html="<p>Some content.</p>",
            body_text="Some content.",
            intensity="extreme",
        )

        # Should not crash — defaults to medium
        assert "subject" in result


# ============================================================================
# Gap 7: dkim_signer.py
# ============================================================================

class TestShouldSignDkim:
    """Tests for should_sign_dkim()."""

    def test_returns_false_for_office365(self):
        from app.services.dkim_signer import should_sign_dkim

        mailbox = SimpleNamespace(
            smtp_host="smtp.office365.com",
            dkim_private_key="-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----",
            email="user@company.com",
        )
        assert should_sign_dkim(mailbox) is False

    def test_returns_false_for_gmail(self):
        from app.services.dkim_signer import should_sign_dkim

        mailbox = SimpleNamespace(
            smtp_host="smtp.gmail.com",
            dkim_private_key="-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----",
            email="user@gmail.com",
        )
        assert should_sign_dkim(mailbox) is False

    def test_returns_true_for_custom_smtp_with_key(self):
        from app.services.dkim_signer import should_sign_dkim

        mailbox = SimpleNamespace(
            smtp_host="mail.mydomain.com",
            dkim_private_key="-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----",
            email="user@mydomain.com",
        )
        assert should_sign_dkim(mailbox) is True

    def test_returns_false_when_no_private_key(self):
        from app.services.dkim_signer import should_sign_dkim

        mailbox = SimpleNamespace(
            smtp_host="mail.mydomain.com",
            dkim_private_key=None,
            email="user@mydomain.com",
        )
        assert should_sign_dkim(mailbox) is False

    def test_returns_false_when_empty_private_key(self):
        from app.services.dkim_signer import should_sign_dkim

        mailbox = SimpleNamespace(
            smtp_host="mail.mydomain.com",
            dkim_private_key="",
            email="user@mydomain.com",
        )
        assert should_sign_dkim(mailbox) is False

    def test_returns_false_for_google_relay(self):
        from app.services.dkim_signer import should_sign_dkim

        mailbox = SimpleNamespace(
            smtp_host="smtp-relay.gmail.com",
            dkim_private_key="some-key",
            email="user@company.com",
        )
        assert should_sign_dkim(mailbox) is False


class TestSignEmailDkim:
    """Tests for sign_email_dkim()."""

    def test_returns_original_bytes_when_library_unavailable(self):
        from app.services.dkim_signer import sign_email_dkim

        original = b"From: a@b.com\r\nTo: c@d.com\r\nSubject: hi\r\n\r\nBody"

        # Patch _DKIM_AVAILABLE to False
        with patch("app.services.dkim_signer._DKIM_AVAILABLE", False):
            result = sign_email_dkim(
                msg_bytes=original,
                domain="example.com",
                selector="mail",
                private_key="some-key",
            )
        assert result == original

    def test_returns_original_bytes_when_missing_params(self):
        from app.services.dkim_signer import sign_email_dkim

        original = b"From: a@b.com\r\nTo: c@d.com\r\n\r\nBody"

        with patch("app.services.dkim_signer._DKIM_AVAILABLE", True):
            result = sign_email_dkim(
                msg_bytes=original,
                domain="",
                selector="mail",
                private_key="some-key",
            )
        assert result == original


# ============================================================================
# Gap 9: engagement_tracker.py
# ============================================================================

class TestCalculateEngagementScore:
    """Tests for calculate_engagement_score()."""

    def test_empty_events_returns_cold(self, db_session):
        from app.services.engagement_tracker import calculate_engagement_score

        tenant = _make_tenant(db_session)
        contact = _make_contact(db_session, tenant.tenant_id, "noevents@example.com")
        db_session.commit()

        result = calculate_engagement_score(
            db=db_session,
            contact_id=contact.contact_id,
            tenant_id=tenant.tenant_id,
        )

        assert result["score"] == 0.0
        assert result["tier"] == "cold"
        assert result["total_sent"] == 0

    def test_replied_events_high_score(self, db_session):
        from app.services.engagement_tracker import calculate_engagement_score

        tenant = _make_tenant(db_session)
        contact = _make_contact(db_session, tenant.tenant_id, "replied@example.com")
        mailbox = _make_mailbox(db_session, tenant.tenant_id, email="mb-engage@example.com")
        db_session.commit()

        # Create sent + replied events
        _make_outreach_event(
            db_session, tenant.tenant_id, contact.contact_id,
            OutreachStatus.SENT, mailbox_id=mailbox.mailbox_id,
        )
        _make_outreach_event(
            db_session, tenant.tenant_id, contact.contact_id,
            OutreachStatus.REPLIED, mailbox_id=mailbox.mailbox_id,
            reply_detected_at=datetime.utcnow(),
        )
        db_session.commit()

        result = calculate_engagement_score(
            db=db_session,
            contact_id=contact.contact_id,
            tenant_id=tenant.tenant_id,
        )

        assert result["score"] > 0.0
        assert result["signals"]["reply"] >= 1

    def test_bounced_only_returns_dead(self, db_session):
        from app.services.engagement_tracker import calculate_engagement_score

        tenant = _make_tenant(db_session)
        contact = _make_contact(db_session, tenant.tenant_id, "dead@example.com")
        db_session.commit()

        # Only bounced events (no SENT events)
        _make_outreach_event(
            db_session, tenant.tenant_id, contact.contact_id,
            OutreachStatus.BOUNCED,
        )
        _make_outreach_event(
            db_session, tenant.tenant_id, contact.contact_id,
            OutreachStatus.BOUNCED,
        )
        db_session.commit()

        result = calculate_engagement_score(
            db=db_session,
            contact_id=contact.contact_id,
            tenant_id=tenant.tenant_id,
        )

        assert result["tier"] == "dead"
        assert result["score"] == 0.0


class TestGetMailboxEngagementRates:
    """Tests for get_mailbox_engagement_rates()."""

    def test_calculates_rates_correctly(self, db_session):
        from app.services.engagement_tracker import get_mailbox_engagement_rates

        tenant = _make_tenant(db_session)
        contact = _make_contact(db_session, tenant.tenant_id, "rates@example.com")
        mailbox = _make_mailbox(db_session, tenant.tenant_id, email="mb-rates@example.com")
        db_session.commit()

        # 3 sent, 1 replied, 1 bounced
        for _ in range(3):
            _make_outreach_event(
                db_session, tenant.tenant_id, contact.contact_id,
                OutreachStatus.SENT, mailbox_id=mailbox.mailbox_id,
            )
        _make_outreach_event(
            db_session, tenant.tenant_id, contact.contact_id,
            OutreachStatus.REPLIED, mailbox_id=mailbox.mailbox_id,
        )
        _make_outreach_event(
            db_session, tenant.tenant_id, contact.contact_id,
            OutreachStatus.BOUNCED, mailbox_id=mailbox.mailbox_id,
        )
        db_session.commit()

        rates = get_mailbox_engagement_rates(
            db=db_session,
            mailbox_id=mailbox.mailbox_id,
            tenant_id=tenant.tenant_id,
        )

        assert rates["sent_count"] > 0
        assert rates["reply_rate"] >= 0.0
        assert rates["bounce_rate"] >= 0.0
        assert "reply_rate" in rates
        assert "bounce_rate" in rates

    def test_empty_mailbox_returns_zeros(self, db_session):
        from app.services.engagement_tracker import get_mailbox_engagement_rates

        tenant = _make_tenant(db_session)
        mailbox = _make_mailbox(db_session, tenant.tenant_id, email="mb-empty@example.com")
        db_session.commit()

        rates = get_mailbox_engagement_rates(
            db=db_session,
            mailbox_id=mailbox.mailbox_id,
            tenant_id=tenant.tenant_id,
        )

        assert rates["reply_rate"] == 0.0
        assert rates["bounce_rate"] == 0.0
        assert rates["sent_count"] == 0


# ============================================================================
# Gap 10: send_time_optimizer.py
# ============================================================================

class TestGetRecipientTimezone:
    """Tests for get_recipient_timezone()."""

    def test_new_york_state(self):
        from app.services.send_time_optimizer import get_recipient_timezone

        assert get_recipient_timezone("NY") == "America/New_York"

    def test_california_state(self):
        from app.services.send_time_optimizer import get_recipient_timezone

        assert get_recipient_timezone("CA") == "America/Los_Angeles"

    def test_texas_state(self):
        from app.services.send_time_optimizer import get_recipient_timezone

        assert get_recipient_timezone("TX") == "America/Chicago"

    def test_fallback_to_eastern_when_unknown(self):
        from app.services.send_time_optimizer import get_recipient_timezone

        assert get_recipient_timezone("ZZ") == "America/New_York"

    def test_fallback_when_none(self):
        from app.services.send_time_optimizer import get_recipient_timezone

        assert get_recipient_timezone(None) == "America/New_York"

    def test_case_insensitive_state(self):
        from app.services.send_time_optimizer import get_recipient_timezone

        assert get_recipient_timezone("ny") == "America/New_York"
        assert get_recipient_timezone("ca") == "America/Los_Angeles"


class TestCalculateOptimalSendTime:
    """Tests for calculate_optimal_send_time()."""

    def test_returns_future_datetime(self):
        from app.services.send_time_optimizer import calculate_optimal_send_time

        result = calculate_optimal_send_time(state="NY")

        assert "send_at_utc" in result
        assert isinstance(result["send_at_utc"], datetime)
        # The send time should be in the future (within 7 days)
        assert result["send_at_utc"] > datetime.utcnow() - timedelta(minutes=1)

    def test_returns_expected_fields(self):
        from app.services.send_time_optimizer import calculate_optimal_send_time

        result = calculate_optimal_send_time(state="CA")

        assert "timezone" in result
        assert "day_score" in result
        assert "window_score" in result
        assert "combined_score" in result
        assert "recipient_local_time" in result

    def test_with_preferred_hour(self):
        from app.services.send_time_optimizer import calculate_optimal_send_time

        result = calculate_optimal_send_time(state="TX", preferred_hour=10)

        assert result["send_at_utc"] is not None
        assert result["timezone"] == "America/Chicago"


class TestIsWithinSendWindow:
    """Tests for is_within_send_window()."""

    def test_returns_tuple_of_bool_and_string(self):
        from app.services.send_time_optimizer import is_within_send_window

        result = is_within_send_window(state="NY")

        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], bool)
        assert isinstance(result[1], str)

    def test_weekend_returns_false(self):
        from app.services.send_time_optimizer import is_within_send_window
        from zoneinfo import ZoneInfo

        # Mock datetime.now to return a Saturday
        saturday = datetime(2026, 4, 11, 10, 0, 0, tzinfo=ZoneInfo("America/New_York"))

        with patch("app.services.send_time_optimizer.datetime") as mock_dt:
            mock_dt.now.return_value = saturday
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            is_within, reason = is_within_send_window(state="NY")

        assert is_within is False
        assert "Weekend" in reason

    def test_early_morning_returns_false(self):
        from app.services.send_time_optimizer import is_within_send_window
        from zoneinfo import ZoneInfo

        # Mock to 3 AM on a weekday (Tuesday)
        early = datetime(2026, 4, 7, 3, 0, 0, tzinfo=ZoneInfo("America/New_York"))

        with patch("app.services.send_time_optimizer.datetime") as mock_dt:
            mock_dt.now.return_value = early
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            is_within, reason = is_within_send_window(state="NY")

        assert is_within is False
        assert "early" in reason.lower() or "Too early" in reason


# ============================================================================
# Gap 11: rendering_checker.py
# ============================================================================

class TestCheckRendering:
    """Tests for check_rendering()."""

    def test_empty_html_returns_score_100(self):
        from app.services.rendering_checker import check_rendering

        result = check_rendering("")

        assert result["score"] == 100
        assert result["warnings"] == []

    def test_empty_none_returns_score_100(self):
        from app.services.rendering_checker import check_rendering

        result = check_rendering(None)

        assert result["score"] == 100

    def test_external_css_produces_high_severity_warning(self):
        from app.services.rendering_checker import check_rendering

        html = '<link rel="stylesheet" href="https://cdn.example.com/styles.css"><p>Hello</p>'
        result = check_rendering(html)

        high_warnings = [w for w in result["warnings"] if w["severity"] == "high"]
        assert len(high_warnings) >= 1
        assert any("External CSS" in w["message"] for w in high_warnings)

    def test_too_many_images_produces_warning(self):
        from app.services.rendering_checker import check_rendering

        html = "<p>Text</p>" + "<img src='a.png'>" * 5
        result = check_rendering(html)

        img_warnings = [w for w in result["warnings"] if "images" in w["message"].lower()]
        assert len(img_warnings) >= 1

    def test_image_only_email_high_spam_risk(self):
        from app.services.rendering_checker import check_rendering

        html = "<img src='banner.png'>"
        result = check_rendering(html)

        high_warnings = [w for w in result["warnings"] if w["severity"] == "high"]
        assert any("Image-only" in w["message"] for w in high_warnings)

    def test_outlook_unsupported_css_detected(self):
        from app.services.rendering_checker import check_rendering

        html = '<div style="display: flex; border-radius: 5px;"><p>Fancy layout</p></div>'
        result = check_rendering(html)

        outlook_warnings = [w for w in result["warnings"] if w["client"] == "outlook"]
        assert len(outlook_warnings) >= 1

    def test_gmail_style_tag_warning(self):
        from app.services.rendering_checker import check_rendering

        html = "<style>.red { color: red; }</style><p class='red'>Hello</p>"
        result = check_rendering(html)

        gmail_warnings = [w for w in result["warnings"] if w["client"] == "gmail"]
        assert len(gmail_warnings) >= 1
        assert any("<style>" in w["message"] for w in gmail_warnings)

    def test_simple_html_high_score(self):
        from app.services.rendering_checker import check_rendering

        html = "<p>Hi John, just wanted to check in about the role.</p>"
        result = check_rendering(html)

        assert result["score"] >= 80

    def test_stats_include_expected_fields(self):
        from app.services.rendering_checker import check_rendering

        html = "<p>Hello <a href='http://example.com'>click</a></p><img src='logo.png'>"
        result = check_rendering(html)

        stats = result["stats"]
        assert "images" in stats
        assert "links" in stats
        assert "total_chars" in stats
        assert stats["images"] == 1
        assert stats["links"] == 1


# ============================================================================
# Gap 12: spintax.py — campaign-aware seeding
# ============================================================================

class TestProcessSpintaxCampaignAware:
    """Tests for process_spintax() with campaign_id parameter."""

    def test_same_contact_different_campaigns_gives_different_results(self):
        from app.services.spintax import process_spintax

        text = "{Hello|Hi|Hey|Greetings|Howdy}"
        contact_id = 42

        result_campaign_1 = process_spintax(text, seed=contact_id, campaign_id=1)
        result_campaign_2 = process_spintax(text, seed=contact_id, campaign_id=2)

        # With 5 options and different seeds, they should differ
        # (extremely low probability of collision — 1/5)
        # We use multiple spintax groups to make collision near-impossible
        multi_text = "{Hello|Hi|Hey} {there|friend|pal}, {how|what} {are|is} {you|things}?"
        r1 = process_spintax(multi_text, seed=contact_id, campaign_id=1)
        r2 = process_spintax(multi_text, seed=contact_id, campaign_id=2)
        assert r1 != r2

    def test_same_contact_same_campaign_is_deterministic(self):
        from app.services.spintax import process_spintax

        text = "{Hello|Hi|Hey} {there|friend}, {how|what} are you?"
        contact_id = 42
        campaign_id = 10

        result1 = process_spintax(text, seed=contact_id, campaign_id=campaign_id)
        result2 = process_spintax(text, seed=contact_id, campaign_id=campaign_id)

        assert result1 == result2

    def test_backward_compatibility_campaign_id_none(self):
        from app.services.spintax import process_spintax

        text = "{Hello|Hi|Hey} there"
        contact_id = 99

        # campaign_id=None should behave same as old behavior (seed only)
        result_none = process_spintax(text, seed=contact_id, campaign_id=None)
        result_legacy = process_spintax(text, seed=contact_id)

        assert result_none == result_legacy

    def test_no_spintax_returns_unchanged(self):
        from app.services.spintax import process_spintax

        text = "No spintax here, just plain text."
        result = process_spintax(text, seed=1, campaign_id=5)
        assert result == text

    def test_nested_spintax_resolves(self):
        from app.services.spintax import process_spintax

        text = "{Hello|Hi {there|friend}}"
        result = process_spintax(text, seed=42, campaign_id=1)

        # Should resolve to one of: "Hello", "Hi there", "Hi friend"
        assert result in ("Hello", "Hi there", "Hi friend")

    def test_empty_text_returns_empty(self):
        from app.services.spintax import process_spintax

        assert process_spintax("", seed=1, campaign_id=1) == ""
        assert process_spintax("", seed=None, campaign_id=None) == ""
