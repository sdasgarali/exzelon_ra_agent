"""Preview draft generation must only ever use the tenant's own sender mailboxes."""
from unittest.mock import patch

import pytest

from app.db.models.contact import ContactDetails
from app.db.models.sender_mailbox import SenderMailbox, WarmupStatus
from app.db.models.tenant import Tenant

pytestmark = pytest.mark.unit


def _ready_mailbox(db, tenant_id, email):
    mb = SenderMailbox(
        tenant_id=tenant_id, email=email, display_name="Sender", password="x",
        warmup_status=WarmupStatus.COLD_READY, is_active=True,
        connection_status="successful", daily_send_limit=30, emails_sent_today=0,
    )
    db.add(mb)
    db.commit()
    return mb


def test_drafts_never_use_another_tenants_mailbox(db_session, test_tenant):
    from app.services.email_preview_service import generate_pipeline_drafts

    other = Tenant(name="Other Co", slug="other-co-mbx", plan="free")
    db_session.add(other)
    db_session.commit()
    # Only the OTHER tenant has a ready mailbox.
    foreign = _ready_mailbox(db_session, other.tenant_id, "foreign@other.example")

    db_session.add(ContactDetails(
        tenant_id=test_tenant.tenant_id, client_name="Acme", first_name="Ann",
        last_name="Lee", email="ann@acme.example", validation_status="valid",
    ))
    db_session.commit()

    with patch("app.services.pipelines.outreach.check_send_eligibility", return_value=(True, "")):
        result = generate_pipeline_drafts(tenant_id=test_tenant.tenant_id, limit=5, db=db_session)

    from app.db.models.outreach_draft import OutreachDraft
    used = db_session.query(OutreachDraft).filter(OutreachDraft.mailbox_id == foreign.mailbox_id).count()
    assert used == 0
    assert result.get("drafts_created", 0) == 0


def test_drafts_use_own_mailbox(db_session, test_tenant):
    from app.services.email_preview_service import generate_pipeline_drafts

    own = _ready_mailbox(db_session, test_tenant.tenant_id, "own@test.example")
    db_session.add(ContactDetails(
        tenant_id=test_tenant.tenant_id, client_name="Acme", first_name="Bo",
        last_name="Ray", email="bo@acme.example", validation_status="valid",
    ))
    db_session.commit()

    with patch("app.services.pipelines.outreach.check_send_eligibility", return_value=(True, "")), \
         patch("app.services.outreach_draft_service.draft_outreach_email", return_value=None):
        generate_pipeline_drafts(tenant_id=test_tenant.tenant_id, limit=5, db=db_session)

    from app.db.models.outreach_draft import OutreachDraft
    mailboxes = {d.mailbox_id for d in db_session.query(OutreachDraft).all()}
    assert mailboxes <= {own.mailbox_id}
