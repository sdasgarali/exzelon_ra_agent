"""Plan feature gating (Phase 3.1/3.2) and the monthly send quota (Phase 3.3)."""
import pytest
from fastapi import HTTPException

from app.api.deps.features import FEATURE_GATE_CODE, ensure_feature, has_feature
from app.core.plans import (
    BASE_FEATURES, MAX_FEATURES, PLAN_MATRIX, PRO_FEATURES,
    feature_label, minimum_plan_for,
)
from app.db.models.tenant import Tenant, TenantPlan

pytestmark = pytest.mark.unit


def _tenant(db, plan, slug):
    t = Tenant(name=f"{slug} co", slug=slug, plan=plan)
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


# ---------------------------------------------------------------------------
# The matrix itself
# ---------------------------------------------------------------------------

def test_tiers_are_strictly_cumulative():
    """Upgrading must never take a feature away."""
    free = PLAN_MATRIX["free"].features
    pro = PLAN_MATRIX["pro"].features
    mx = PLAN_MATRIX["max"].features
    assert free < pro < mx


def test_minimum_plan_is_derived_not_hardcoded():
    assert minimum_plan_for("leads") == "free"
    assert minimum_plan_for("warmup") == "pro"
    assert minimum_plan_for("visitors") == "max"
    assert minimum_plan_for("not_a_real_feature") is None


def test_every_gated_feature_has_a_human_label():
    """The 402 body shows this to a paying customer — no raw snake_case."""
    for feature in PRO_FEATURES | MAX_FEATURES:
        assert feature_label(feature) != feature, feature


def test_the_core_loop_is_free():
    """Free has to prove the product works end to end, or it converts nobody."""
    for feature in ("leads", "contacts", "campaigns", "inbox", "mailboxes",
                    "pipeline_lead_sourcing", "pipeline_contact_enrichment",
                    "pipeline_email_validation", "ai_personalization"):
        assert feature in BASE_FEATURES, feature


def test_warmup_is_not_free():
    """The shared peer pool is the one real abuse vector on a free plan."""
    assert "warmup" not in PLAN_MATRIX["free"].features
    assert "warmup" in PLAN_MATRIX["pro"].features


# ---------------------------------------------------------------------------
# has_feature / ensure_feature
# ---------------------------------------------------------------------------

def test_free_tenant_is_blocked_from_pro_features(db_session):
    t = _tenant(db_session, TenantPlan.FREE, "fg-free")
    assert has_feature(db_session, t.tenant_id, "leads") is True
    assert has_feature(db_session, t.tenant_id, "warmup") is False

    with pytest.raises(HTTPException) as exc:
        ensure_feature(db_session, t.tenant_id, "warmup")
    assert exc.value.status_code == 402


def test_pro_tenant_is_blocked_only_from_max_features(db_session):
    t = _tenant(db_session, TenantPlan.PRO, "fg-pro")
    ensure_feature(db_session, t.tenant_id, "warmup")  # no raise
    with pytest.raises(HTTPException):
        ensure_feature(db_session, t.tenant_id, "visitors")


def test_max_tenant_passes_everything(db_session):
    t = _tenant(db_session, TenantPlan.MAX, "fg-max")
    for feature in BASE_FEATURES | PRO_FEATURES | MAX_FEATURES:
        ensure_feature(db_session, t.tenant_id, feature)


def test_custom_tenant_gets_the_max_feature_set(db_session):
    t = _tenant(db_session, TenantPlan.CUSTOM, "fg-custom")
    for feature in MAX_FEATURES:
        ensure_feature(db_session, t.tenant_id, feature)


def test_super_admin_bypasses_the_gate(db_session):
    assert has_feature(db_session, None, "visitors") is True
    ensure_feature(db_session, None, "visitors")  # no raise


def test_402_body_is_structured_for_the_frontend(db_session):
    """A generic string forces the UI to guess; a code lets it show the right CTA.

    In particular this must be distinguishable from an exhausted credit balance,
    which is also a 402.
    """
    t = _tenant(db_session, TenantPlan.FREE, "fg-body")
    with pytest.raises(HTTPException) as exc:
        ensure_feature(db_session, t.tenant_id, "visitors")

    detail = exc.value.detail
    assert isinstance(detail, dict)
    assert detail["code"] == FEATURE_GATE_CODE
    assert detail["feature"] == "visitors"
    assert detail["feature_label"] == "Website Visitors"
    assert detail["plan"] == "free"
    assert detail["required_plan"] == "max"
    assert "Max" in detail["message"]


def test_legacy_plan_names_still_resolve(db_session):
    """A tenant row written before the rename must not lose its features."""
    t = _tenant(db_session, TenantPlan.ENTERPRISE, "fg-legacy")  # alias of MAX
    ensure_feature(db_session, t.tenant_id, "visitors")


# ---------------------------------------------------------------------------
# Send quota (Phase 3.3)
# ---------------------------------------------------------------------------

def _add_send(db, tenant_id, email, status=None):
    from app.db.models.contact import ContactDetails
    from app.db.models.outreach import OutreachChannel, OutreachEvent, OutreachStatus

    contact = ContactDetails(
        tenant_id=tenant_id, client_name="C", first_name="F", last_name="L", email=email,
    )
    db.add(contact)
    db.flush()
    db.add(OutreachEvent(
        tenant_id=tenant_id,
        contact_id=contact.contact_id,
        channel=OutreachChannel.SMTP,
        status=status or OutreachStatus.SENT,
    ))
    db.commit()


def test_quota_counts_sent_replied_and_bounced_but_not_skipped(db_session):
    from app.db.models.outreach import OutreachStatus
    from app.services.send_quota import sends_this_month

    t = _tenant(db_session, TenantPlan.FREE, "sq-count")
    _add_send(db_session, t.tenant_id, "a@x.com", OutreachStatus.SENT)
    _add_send(db_session, t.tenant_id, "b@x.com", OutreachStatus.REPLIED)
    # A bounce still consumed a send — we handed it to a mail server.
    _add_send(db_session, t.tenant_id, "c@x.com", OutreachStatus.BOUNCED)
    # A skip never left the building.
    _add_send(db_session, t.tenant_id, "d@x.com", OutreachStatus.SKIPPED)

    assert sends_this_month(db_session, t.tenant_id) == 3


def test_quota_is_tenant_scoped(db_session):
    from app.services.send_quota import sends_this_month
    t1 = _tenant(db_session, TenantPlan.FREE, "sq-t1")
    t2 = _tenant(db_session, TenantPlan.FREE, "sq-t2")
    _add_send(db_session, t1.tenant_id, "a@x.com")
    assert sends_this_month(db_session, t2.tenant_id) == 0


def test_quota_status_reports_the_plan_limit(db_session):
    from app.services.send_quota import quota_status
    t = _tenant(db_session, TenantPlan.FREE, "sq-status")
    status = quota_status(db_session, t.tenant_id)
    assert status["limit"] == PLAN_MATRIX["free"].send_quota_per_month == 500
    assert status["used"] == 0
    assert status["exhausted"] is False


def test_quota_blocks_once_exhausted(db_session, monkeypatch):
    from app.services import send_quota
    t = _tenant(db_session, TenantPlan.FREE, "sq-block")
    monkeypatch.setattr(send_quota, "sends_this_month", lambda db, tid: 500)

    allowed, status = send_quota.has_send_quota(db_session, t.tenant_id)
    assert allowed is False
    assert status["remaining"] == 0


def test_super_admin_has_no_send_quota(db_session):
    from app.services.send_quota import has_send_quota
    allowed, status = has_send_quota(db_session, None)
    assert allowed is True
    assert status["metered"] is False


def test_send_gate_blocks_when_quota_is_gone(db_session, monkeypatch):
    """The quota check runs FIRST, so an exhausted tenant never reaches the LLM call."""
    from app.db.models.contact import ContactDetails
    from app.services import send_quota
    from app.services.send_gate import unified_send_gate

    t = _tenant(db_session, TenantPlan.FREE, "sq-gate")
    contact = ContactDetails(
        tenant_id=t.tenant_id, client_name="C", first_name="F", last_name="L",
        email="gate@x.com", validation_status="valid",
    )
    db_session.add(contact)
    db_session.commit()

    monkeypatch.setattr(send_quota, "sends_this_month", lambda db, tid: 9_999)
    result = unified_send_gate(db_session, contact, t.tenant_id)

    assert result.allowed is False
    assert result.reason_code == "SEND_QUOTA_EXCEEDED"
    # First check evaluated — nothing downstream ran.
    assert result.checks[0].name == "send_quota"


def test_send_gate_skips_quota_for_replies_and_dry_runs(db_session, monkeypatch):
    """A reply is a conversation the customer is already in, not new outbound."""
    from app.db.models.contact import ContactDetails
    from app.services import send_quota
    from app.services.send_gate import unified_send_gate

    t = _tenant(db_session, TenantPlan.FREE, "sq-skip")
    contact = ContactDetails(
        tenant_id=t.tenant_id, client_name="C", first_name="F", last_name="L",
        email="skip@x.com", validation_status="valid",
    )
    db_session.add(contact)
    db_session.commit()
    monkeypatch.setattr(send_quota, "sends_this_month", lambda db, tid: 9_999)

    for kwargs in ({"is_reply": True}, {"dry_run": True}):
        result = unified_send_gate(db_session, contact, t.tenant_id, **kwargs)
        assert result.reason_code != "SEND_QUOTA_EXCEEDED"


def test_send_gate_fails_open_if_counting_breaks(db_session, monkeypatch):
    """A counting bug must not stop a paying customer's campaign."""
    from app.db.models.contact import ContactDetails
    from app.services import send_quota
    from app.services.send_gate import unified_send_gate

    t = _tenant(db_session, TenantPlan.MAX, "sq-open")
    contact = ContactDetails(
        tenant_id=t.tenant_id, client_name="C", first_name="F", last_name="L",
        email="open@x.com", validation_status="valid",
    )
    db_session.add(contact)
    db_session.commit()

    def _boom(db, tid):
        raise RuntimeError("index missing")

    monkeypatch.setattr(send_quota, "sends_this_month", _boom)
    result = unified_send_gate(db_session, contact, t.tenant_id)
    assert result.reason_code != "SEND_QUOTA_EXCEEDED"
    assert result.checks[0].passed is True
