"""Tests for the Centralized Send Gate — unified safety enforcement."""
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from app.services.send_gate import (
    unified_send_gate,
    SendGateResult,
    GateCheckResult,
)
from app.db.models.contact import ContactDetails, OutreachStatus as ContactOutreachStatus
from app.db.models.outreach import OutreachEvent, OutreachStatus, OutreachChannel
from app.db.models.lead import LeadDetails, LeadStatus
from app.db.models.email_validation import EmailValidationResult, ValidationStatus
from app.db.models.suppression import SuppressionList
from app.db.models.campaign import Campaign, CampaignStatus
from app.db.models.inbox_message import InboxMessage, MessageDirection


pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_contact(db, tenant_id, email="test@company.com", client_name="Test Co",
                  first_name="Test", validation="valid", outreach_status=None):
    """Create a ContactDetails row."""
    c = ContactDetails(
        tenant_id=tenant_id,
        email=email,
        first_name=first_name,
        last_name="User",
        client_name=client_name,
        validation_status=validation,
    )
    if outreach_status:
        c.outreach_status = outreach_status
    db.add(c)
    db.flush()
    return c


def _make_lead(db, tenant_id, job_title="Engineer"):
    """Create a LeadDetails row."""
    lead = LeadDetails(
        tenant_id=tenant_id,
        job_title=job_title,
        client_name="Test Co",
        lead_status=LeadStatus.OPEN,
    )
    db.add(lead)
    db.flush()
    return lead


def _make_sent_event(db, tenant_id, contact_id, lead_id=None, sent_at=None):
    """Create a SENT OutreachEvent."""
    event = OutreachEvent(
        tenant_id=tenant_id,
        contact_id=contact_id,
        lead_id=lead_id,
        channel=OutreachChannel.SMTP,
        status=OutreachStatus.SENT,
        sent_at=sent_at or datetime.utcnow(),
    )
    db.add(event)
    db.flush()
    return event


def _make_suppression(db, tenant_id, email, reason="manual"):
    """Create a SuppressionList entry."""
    s = SuppressionList(
        tenant_id=tenant_id,
        email=email.lower(),
        reason=reason,
    )
    db.add(s)
    db.flush()
    return s


# ---------------------------------------------------------------------------
# Check 1: Contact Status
# ---------------------------------------------------------------------------

class TestContactStatus:
    """Check 1 — unsubscribed / inactive contacts are blocked."""

    def test_unsubscribed_blocked(self, db_session, test_tenant):
        contact = _make_contact(
            db_session, test_tenant.tenant_id,
            outreach_status=ContactOutreachStatus.UNSUBSCRIBED,
        )
        result = unified_send_gate(db_session, contact, test_tenant.tenant_id)
        assert not result.allowed
        assert result.reason_code == "UNSUBSCRIBED"

    def test_inactive_blocked(self, db_session, test_tenant):
        contact = _make_contact(
            db_session, test_tenant.tenant_id,
            outreach_status=ContactOutreachStatus.INACTIVE,
        )
        result = unified_send_gate(db_session, contact, test_tenant.tenant_id)
        assert not result.allowed
        assert result.reason_code == "INACTIVE"

    def test_active_passes(self, db_session, test_tenant):
        contact = _make_contact(
            db_session, test_tenant.tenant_id,
            outreach_status=ContactOutreachStatus.ACTIVE,
        )
        result = unified_send_gate(db_session, contact, test_tenant.tenant_id)
        # Active status alone won't block (need to pass other checks too)
        status_check = next(c for c in result.checks if c.name == "contact_status")
        assert status_check.passed


# ---------------------------------------------------------------------------
# Check 2: Suppression List
# ---------------------------------------------------------------------------

class TestSuppression:
    """Check 2 — suppressed contacts are blocked."""

    def test_suppressed_blocked(self, db_session, test_tenant):
        contact = _make_contact(db_session, test_tenant.tenant_id, email="suppressed@co.com")
        _make_suppression(db_session, test_tenant.tenant_id, "suppressed@co.com", "bounced")
        db_session.commit()

        result = unified_send_gate(db_session, contact, test_tenant.tenant_id)
        assert not result.allowed
        assert result.reason_code == "SUPPRESSED"
        assert "bounced" in result.reason_message

    def test_expired_suppression_passes(self, db_session, test_tenant):
        contact = _make_contact(db_session, test_tenant.tenant_id, email="expired@co.com")
        s = SuppressionList(
            tenant_id=test_tenant.tenant_id,
            email="expired@co.com",
            reason="temp",
            expires_at=datetime.utcnow() - timedelta(days=1),
        )
        db_session.add(s)
        db_session.commit()

        result = unified_send_gate(db_session, contact, test_tenant.tenant_id)
        suppression_check = next(c for c in result.checks if c.name == "suppression")
        assert suppression_check.passed


# ---------------------------------------------------------------------------
# Check 3: Email Validation
# ---------------------------------------------------------------------------

class TestEmailValidation:
    """Check 3 — invalid emails are blocked."""

    def test_valid_status_passes(self, db_session, test_tenant):
        contact = _make_contact(db_session, test_tenant.tenant_id, validation="valid")
        result = unified_send_gate(db_session, contact, test_tenant.tenant_id)
        validation_check = next(c for c in result.checks if c.name == "email_validation")
        assert validation_check.passed

    def test_invalid_status_no_fallback_blocked(self, db_session, test_tenant):
        contact = _make_contact(db_session, test_tenant.tenant_id, validation="unknown")
        db_session.commit()

        result = unified_send_gate(db_session, contact, test_tenant.tenant_id)
        assert not result.allowed
        assert result.reason_code == "INVALID_EMAIL"

    def test_invalid_status_with_valid_validation_record_passes(self, db_session, test_tenant):
        contact = _make_contact(
            db_session, test_tenant.tenant_id,
            email="fb@co.com", validation="unknown",
        )
        vr = EmailValidationResult(
            email="fb@co.com",
            provider="test",
            status=ValidationStatus.VALID,
            validated_at=datetime.utcnow(),
        )
        db_session.add(vr)
        db_session.commit()

        result = unified_send_gate(db_session, contact, test_tenant.tenant_id)
        validation_check = next(c for c in result.checks if c.name == "email_validation")
        assert validation_check.passed


# ---------------------------------------------------------------------------
# Check 4: Contact + Lead Cooldown (cross-channel)
# ---------------------------------------------------------------------------

class TestContactLeadCooldown:
    """Check 4 — blocks sending to the same contact+lead within cooldown."""

    @patch("app.services.send_gate._resolve_cooldown_days", return_value=10)
    def test_recent_send_for_same_lead_blocked(self, mock_cd, db_session, test_tenant):
        contact = _make_contact(db_session, test_tenant.tenant_id)
        lead = _make_lead(db_session, test_tenant.tenant_id)
        _make_sent_event(
            db_session, test_tenant.tenant_id, contact.contact_id,
            lead_id=lead.lead_id, sent_at=datetime.utcnow() - timedelta(days=2),
        )
        db_session.commit()

        result = unified_send_gate(
            db_session, contact, test_tenant.tenant_id, lead=lead,
        )
        assert not result.allowed
        assert result.reason_code == "CONTACT_LEAD_COOLDOWN"

    @patch("app.services.send_gate._resolve_cooldown_days", return_value=10)
    def test_old_send_for_same_lead_passes(self, mock_cd, db_session, test_tenant):
        contact = _make_contact(db_session, test_tenant.tenant_id)
        lead = _make_lead(db_session, test_tenant.tenant_id)
        _make_sent_event(
            db_session, test_tenant.tenant_id, contact.contact_id,
            lead_id=lead.lead_id, sent_at=datetime.utcnow() - timedelta(days=15),
        )
        db_session.commit()

        result = unified_send_gate(
            db_session, contact, test_tenant.tenant_id, lead=lead,
        )
        cl_check = next(c for c in result.checks if c.name == "contact_lead_cooldown")
        assert cl_check.passed

    @patch("app.services.send_gate._resolve_cooldown_days", return_value=10)
    def test_send_for_different_lead_still_triggers_contact_cooldown(self, mock_cd, db_session, test_tenant):
        contact = _make_contact(db_session, test_tenant.tenant_id)
        lead_a = _make_lead(db_session, test_tenant.tenant_id)
        lead_b = _make_lead(db_session, test_tenant.tenant_id)
        _make_sent_event(
            db_session, test_tenant.tenant_id, contact.contact_id,
            lead_id=lead_a.lead_id, sent_at=datetime.utcnow() - timedelta(days=2),
        )
        db_session.commit()

        result = unified_send_gate(
            db_session, contact, test_tenant.tenant_id, lead=lead_b,
        )
        # Contact+Lead cooldown passes (different lead), but contact-level cooldown blocks
        assert not result.allowed
        assert result.reason_code == "CONTACT_COOLDOWN"


# ---------------------------------------------------------------------------
# Check 5: Contact-Level Cooldown
# ---------------------------------------------------------------------------

class TestContactCooldown:
    """Check 5 — blocks sending to any recently-contacted contact."""

    @patch("app.services.send_gate._resolve_cooldown_days", return_value=10)
    def test_recent_send_blocked(self, mock_cd, db_session, test_tenant):
        contact = _make_contact(db_session, test_tenant.tenant_id)
        _make_sent_event(
            db_session, test_tenant.tenant_id, contact.contact_id,
            sent_at=datetime.utcnow() - timedelta(days=3),
        )
        db_session.commit()

        result = unified_send_gate(db_session, contact, test_tenant.tenant_id)
        assert not result.allowed
        assert result.reason_code == "CONTACT_COOLDOWN"

    @patch("app.services.send_gate._resolve_cooldown_days", return_value=10)
    def test_old_send_passes(self, mock_cd, db_session, test_tenant):
        contact = _make_contact(db_session, test_tenant.tenant_id)
        _make_sent_event(
            db_session, test_tenant.tenant_id, contact.contact_id,
            sent_at=datetime.utcnow() - timedelta(days=20),
        )
        db_session.commit()

        result = unified_send_gate(db_session, contact, test_tenant.tenant_id)
        cooldown_check = next(c for c in result.checks if c.name == "contact_cooldown")
        assert cooldown_check.passed


# ---------------------------------------------------------------------------
# Check 8: Sequence Fatigue (mocked)
# ---------------------------------------------------------------------------

class TestSequenceFatigue:
    """Check 8 — fatigued contacts are blocked."""

    @patch("app.services.send_gate._resolve_cooldown_days", return_value=10)
    def test_fatigue_blocks_and_sets_code(self, mock_cd, db_session, test_tenant):
        contact = _make_contact(db_session, test_tenant.tenant_id)
        # Create 6 sent events in the last 90 days (exceeds default 5)
        for i in range(6):
            _make_sent_event(
                db_session, test_tenant.tenant_id, contact.contact_id,
                sent_at=datetime.utcnow() - timedelta(days=90 - i * 10),
            )
        db_session.commit()

        result = unified_send_gate(db_session, contact, test_tenant.tenant_id)
        # Should be blocked by either cooldown (most recent send) or fatigue
        assert not result.allowed


# ---------------------------------------------------------------------------
# is_reply skip logic
# ---------------------------------------------------------------------------

class TestReplySkipLogic:
    """AI reply mode skips cooldown, fatigue, company cap, AI orchestrator."""

    @patch("app.services.send_gate._resolve_cooldown_days", return_value=10)
    def test_reply_skips_cooldown(self, mock_cd, db_session, test_tenant):
        contact = _make_contact(db_session, test_tenant.tenant_id)
        _make_sent_event(
            db_session, test_tenant.tenant_id, contact.contact_id,
            sent_at=datetime.utcnow() - timedelta(days=1),
        )
        db_session.commit()

        result = unified_send_gate(
            db_session, contact, test_tenant.tenant_id, is_reply=True,
        )
        # Cooldown skipped for replies — only domain throttle might block
        cooldown_check = next(c for c in result.checks if c.name == "contact_cooldown")
        assert "skipped" in cooldown_check.reason

    def test_reply_still_blocks_unsubscribed(self, db_session, test_tenant):
        contact = _make_contact(
            db_session, test_tenant.tenant_id,
            outreach_status=ContactOutreachStatus.UNSUBSCRIBED,
        )
        result = unified_send_gate(
            db_session, contact, test_tenant.tenant_id, is_reply=True,
        )
        assert not result.allowed
        assert result.reason_code == "UNSUBSCRIBED"

    def test_reply_still_blocks_suppressed(self, db_session, test_tenant):
        contact = _make_contact(db_session, test_tenant.tenant_id, email="sup@co.com")
        _make_suppression(db_session, test_tenant.tenant_id, "sup@co.com")
        db_session.commit()

        result = unified_send_gate(
            db_session, contact, test_tenant.tenant_id, is_reply=True,
        )
        assert not result.allowed
        assert result.reason_code == "SUPPRESSED"

    def test_reply_still_blocks_invalid_email(self, db_session, test_tenant):
        contact = _make_contact(
            db_session, test_tenant.tenant_id, validation="unknown",
        )
        db_session.commit()

        result = unified_send_gate(
            db_session, contact, test_tenant.tenant_id, is_reply=True,
        )
        assert not result.allowed
        assert result.reason_code == "INVALID_EMAIL"


# ---------------------------------------------------------------------------
# dry_run skip logic
# ---------------------------------------------------------------------------

class TestDryRunSkipLogic:
    """Dry run mode skips domain throttle and AI orchestrator."""

    def test_dry_run_skips_domain_throttle(self, db_session, test_tenant):
        contact = _make_contact(db_session, test_tenant.tenant_id)
        db_session.commit()

        result = unified_send_gate(
            db_session, contact, test_tenant.tenant_id, dry_run=True,
        )
        throttle_check = next(c for c in result.checks if c.name == "domain_throttle")
        assert "skipped" in throttle_check.reason

    def test_dry_run_skips_ai_orchestrator(self, db_session, test_tenant):
        contact = _make_contact(db_session, test_tenant.tenant_id)
        db_session.commit()

        result = unified_send_gate(
            db_session, contact, test_tenant.tenant_id, dry_run=True,
        )
        ai_check = next(c for c in result.checks if c.name == "ai_orchestrator")
        assert "skipped" in ai_check.reason


# ---------------------------------------------------------------------------
# Domain throttle (mocked)
# ---------------------------------------------------------------------------

class TestDomainThrottle:
    """Check 9 — domain throttle integration."""

    @patch("app.services.send_gate._resolve_cooldown_days", return_value=10)
    @patch("app.services.domain_throttle.check_domain_throttle", return_value=(False, "50/50 today"))
    def test_domain_throttle_blocks(self, mock_dt, mock_cd, db_session, test_tenant):
        contact = _make_contact(db_session, test_tenant.tenant_id)
        db_session.commit()

        result = unified_send_gate(db_session, contact, test_tenant.tenant_id)
        assert not result.allowed
        assert result.reason_code == "DOMAIN_THROTTLE"

    @patch("app.services.send_gate._resolve_cooldown_days", return_value=10)
    @patch("app.services.domain_throttle.check_domain_throttle", return_value=(True, ""))
    def test_domain_throttle_passes(self, mock_dt, mock_cd, db_session, test_tenant):
        contact = _make_contact(db_session, test_tenant.tenant_id)
        db_session.commit()

        result = unified_send_gate(db_session, contact, test_tenant.tenant_id)
        throttle_check = next(c for c in result.checks if c.name == "domain_throttle")
        assert throttle_check.passed


# ---------------------------------------------------------------------------
# AI Orchestrator (mocked)
# ---------------------------------------------------------------------------

class TestAIOrchestrator:
    """Check 10 — AI orchestrator integration."""

    @patch("app.services.send_gate._resolve_cooldown_days", return_value=10)
    @patch("app.services.domain_throttle.check_domain_throttle", return_value=(True, ""))
    @patch("app.services.ai_sales_agent.orchestrator.orchestrate_send",
           return_value={"should_send": False, "reason_codes": ["LOW_SCORE"]})
    def test_ai_blocks_with_campaign(self, mock_ai, mock_dt, mock_cd, db_session, test_tenant):
        contact = _make_contact(db_session, test_tenant.tenant_id)
        campaign = Campaign(
            tenant_id=test_tenant.tenant_id,
            name="Test",
            status=CampaignStatus.ACTIVE,
        )
        db_session.add(campaign)
        db_session.commit()

        result = unified_send_gate(
            db_session, contact, test_tenant.tenant_id, campaign=campaign,
        )
        assert not result.allowed
        assert result.reason_code == "AI_BLOCKED"
        assert "LOW_SCORE" in result.reason_message

    @patch("app.services.send_gate._resolve_cooldown_days", return_value=10)
    @patch("app.services.domain_throttle.check_domain_throttle", return_value=(True, ""))
    def test_ai_skipped_without_campaign(self, mock_dt, mock_cd, db_session, test_tenant):
        contact = _make_contact(db_session, test_tenant.tenant_id)
        db_session.commit()

        result = unified_send_gate(db_session, contact, test_tenant.tenant_id)
        ai_check = next(c for c in result.checks if c.name == "ai_orchestrator")
        assert ai_check.passed
        assert "no campaign" in ai_check.reason


# ---------------------------------------------------------------------------
# Full pass-through (all checks pass)
# ---------------------------------------------------------------------------

class TestAllChecksPass:
    """Verify the happy path — all checks pass."""

    @patch("app.services.send_gate._resolve_cooldown_days", return_value=10)
    @patch("app.services.domain_throttle.check_domain_throttle", return_value=(True, ""))
    def test_clean_contact_passes_all(self, mock_dt, mock_cd, db_session, test_tenant):
        contact = _make_contact(db_session, test_tenant.tenant_id)
        db_session.commit()

        result = unified_send_gate(db_session, contact, test_tenant.tenant_id)
        assert result.allowed
        assert result.reason_code == ""
        assert len(result.checks) > 0
        assert all(c.passed for c in result.checks)


# ---------------------------------------------------------------------------
# Result structure
# ---------------------------------------------------------------------------

class TestResultStructure:
    """Verify result dataclass properties."""

    def test_blocked_result_has_all_fields(self, db_session, test_tenant):
        contact = _make_contact(
            db_session, test_tenant.tenant_id,
            outreach_status=ContactOutreachStatus.UNSUBSCRIBED,
        )
        result = unified_send_gate(db_session, contact, test_tenant.tenant_id)
        assert isinstance(result, SendGateResult)
        assert not result.allowed
        assert result.reason_code == "UNSUBSCRIBED"
        assert len(result.reason_message) > 0
        assert len(result.checks) > 0
        assert isinstance(result.checks[0], GateCheckResult)

    @patch("app.services.send_gate._resolve_cooldown_days", return_value=10)
    @patch("app.services.domain_throttle.check_domain_throttle", return_value=(True, ""))
    def test_allowed_result_has_empty_reason(self, mock_dt, mock_cd, db_session, test_tenant):
        contact = _make_contact(db_session, test_tenant.tenant_id)
        db_session.commit()

        result = unified_send_gate(db_session, contact, test_tenant.tenant_id)
        assert result.allowed
        assert result.reason_code == ""
        assert result.reason_message == ""
