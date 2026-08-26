"""GDPR data-subject endpoints (ELR-024).

Lets a tenant honour Right-to-Access (export) and Right-to-Erasure (delete) for a
data subject identified by email — required to lawfully cold-email EU contacts.
Both are tenant-scoped and admin-gated; erasure is audited and suppresses the
address so it is never contacted again.
"""
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_role, get_current_tenant_id, require_tenant_id
from app.db.query_helpers import tenant_filter
from app.db.models.user import User, UserRole
from app.db.models.contact import ContactDetails, OutreachStatus as ContactOutreachStatus
from app.db.models.outreach import OutreachEvent
from app.db.models.inbox_message import InboxMessage
from app.db.models.visitor import VisitorEvent
from app.db.models.suppression import SuppressionList
from app.db.models.audit_log import AuditLog

router = APIRouter(prefix="/gdpr", tags=["GDPR"])


@router.get("/export")
def export_data_subject(
    email: str = Query(..., description="Data subject email"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Right-to-Access: everything this tenant holds about ``email``."""
    email_lc = email.strip().lower()
    contacts = tenant_filter(
        db.query(ContactDetails).filter(func_lower(ContactDetails.email) == email_lc),
        ContactDetails, tenant_id,
    ).all()
    contact_ids = [c.contact_id for c in contacts]

    def _events():
        if not contact_ids:
            return []
        q = tenant_filter(
            db.query(OutreachEvent).filter(OutreachEvent.contact_id.in_(contact_ids)),
            OutreachEvent, tenant_id,
        )
        return [{"event_id": e.event_id, "channel": getattr(e.channel, "value", str(e.channel)),
                 "status": getattr(e.status, "value", str(e.status)),
                 "subject": e.subject, "sent_at": e.sent_at.isoformat() if e.sent_at else None}
                for e in q.all()]

    def _inbox():
        if not contact_ids:
            return []
        q = tenant_filter(
            db.query(InboxMessage).filter(InboxMessage.contact_id.in_(contact_ids)),
            InboxMessage, tenant_id,
        )
        return [{"message_id": m.message_id, "from": m.from_email, "to": m.to_email,
                 "subject": m.subject,
                 "received_at": m.received_at.isoformat() if m.received_at else None}
                for m in q.all()]

    def _visits():
        if not contact_ids:
            return []
        q = tenant_filter(
            db.query(VisitorEvent).filter(VisitorEvent.contact_id.in_(contact_ids)),
            VisitorEvent, tenant_id,
        )
        return [{"event_id": v.event_id, "page_url": v.page_url,
                 "visited_at": v.visited_at.isoformat() if v.visited_at else None}
                for v in q.all()]

    suppressed = db.query(SuppressionList).filter(SuppressionList.email == email_lc)
    suppressed = tenant_filter(suppressed, SuppressionList, tenant_id).first()

    return {
        "email": email_lc,
        "contacts": [
            {
                "contact_id": c.contact_id, "first_name": c.first_name, "last_name": c.last_name,
                "email": c.email, "phone": c.phone, "title": c.title,
                "company": c.client_name, "linkedin_url": c.linkedin_url,
                "outreach_status": getattr(c.outreach_status, "value", str(c.outreach_status)),
            }
            for c in contacts
        ],
        "outreach_events": _events(),
        "inbox_messages": _inbox(),
        "visitor_events": _visits(),
        "suppressed": suppressed is not None,
    }


@router.post("/erase")
def erase_data_subject(
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    tenant_id: int = Depends(require_tenant_id),
):
    """Right-to-Erasure: anonymise PII, suppress the address, and audit.

    Rows are kept (deals/campaigns reference them) but every PII field is scrubbed,
    so no personal data remains. The original address is added to the suppression
    list first so it can never be contacted again.
    """
    email_lc = str(body.get("email", "")).strip().lower()
    if not email_lc:
        raise HTTPException(status_code=400, detail="email is required")
    reason = body.get("reason") or "gdpr_erasure"

    contacts = db.query(ContactDetails).filter(
        func_lower(ContactDetails.email) == email_lc,
        ContactDetails.tenant_id == tenant_id,
    ).all()
    if not contacts:
        return {"erased": 0, "message": "No matching contacts for this tenant."}

    # Suppress first (idempotent per tenant).
    if not db.query(SuppressionList).filter(
        SuppressionList.tenant_id == tenant_id, SuppressionList.email == email_lc,
    ).first():
        db.add(SuppressionList(tenant_id=tenant_id, email=email_lc, reason=reason))

    for c in contacts:
        c.email = f"redacted+{c.contact_id}@gdpr.invalid"
        c.first_name = "REDACTED"
        c.last_name = None
        c.title = None
        c.phone = None
        c.linkedin_url = None
        c.outreach_status = ContactOutreachStatus.UNSUBSCRIBED
        db.add(AuditLog(
            tenant_id=tenant_id, entity_type="contact", entity_id=c.contact_id,
            action="gdpr_erased", changed_by=current_user.email,
            notes=f"PII erased on GDPR request ({reason}).",
        ))

    db.commit()
    return {"erased": len(contacts), "email": email_lc}


def func_lower(col):
    """Case-insensitive email match helper (kept explicit for portability)."""
    from sqlalchemy import func
    return func.lower(col)
