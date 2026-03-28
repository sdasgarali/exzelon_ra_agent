"""Auto-forward interested inbox replies to CRM as contacts/notes."""
import structlog
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.db.models.inbox_message import InboxMessage
from app.db.models.contact import ContactDetails
from app.db.models.automation_event import AutomationEvent

logger = structlog.get_logger()


def auto_forward_to_crm(inbox_message: InboxMessage, db: Session, tenant_id: Optional[int] = None) -> Optional[str]:
    """Forward an interested reply to CRM.

    Called by inbox_syncer after AI classifies a reply as 'interested'.

    1. Check if contact exists in CRM (crm_id field)
    2. If not, create contact in HubSpot/Salesforce
    3. Create note/activity with email body
    4. Log automation_event

    Returns:
        CRM type used ("hubspot"/"salesforce") or None if no CRM configured.
    """
    from app.core.settings_resolver import get_tenant_setting

    if not inbox_message or inbox_message.category != "interested":
        return None

    # Check if auto-forward is enabled
    auto_forward_enabled = get_tenant_setting(db, "crm_auto_forward_interested", tenant_id=tenant_id, default=False)
    if not auto_forward_enabled:
        return None

    # Get the contact
    contact = db.query(ContactDetails).filter(
        ContactDetails.contact_id == inbox_message.contact_id
    ).first() if inbox_message.contact_id else None

    if not contact:
        logger.debug("No contact found for inbox message", message_id=inbox_message.message_id)
        return None

    # Determine which CRM to use
    hubspot_key = get_tenant_setting(db, "hubspot_api_key", tenant_id=tenant_id, default="")
    salesforce_id = get_tenant_setting(db, "salesforce_client_id", tenant_id=tenant_id, default="")

    crm_type = None
    if hubspot_key:
        crm_type = "hubspot"
    elif salesforce_id:
        crm_type = "salesforce"

    if not crm_type:
        return None

    try:
        if crm_type == "hubspot":
            _forward_to_hubspot(contact, inbox_message, db)
        elif crm_type == "salesforce":
            _forward_to_salesforce(contact, inbox_message, db)

        # Log automation event
        event = AutomationEvent(
            tenant_id=getattr(contact, 'tenant_id', None) or 1,
            event_type="crm_auto_forward",
            description=f"Auto-forwarded interested reply from {contact.email} to {crm_type}",
            details_json=f'{{"contact_id": {contact.contact_id}, "crm": "{crm_type}", "category": "interested"}}',
        )
        db.add(event)
        db.commit()

        logger.info("Auto-forwarded interested reply to CRM",
                     contact_email=contact.email, crm=crm_type)
        return crm_type

    except Exception as e:
        logger.error("CRM auto-forward failed",
                     contact_id=contact.contact_id, crm=crm_type, error=str(e))
        # Log failure as automation event
        event = AutomationEvent(
            tenant_id=getattr(contact, 'tenant_id', None) or 1,
            event_type="crm_auto_forward",
            description=f"Failed to forward reply from {contact.email} to {crm_type}: {str(e)[:200]}",
            status="error",
        )
        db.add(event)
        db.commit()
        return None


def _forward_to_hubspot(contact: ContactDetails, message: InboxMessage, db: Session):
    """Create/update contact and add note in HubSpot."""
    try:
        from app.services.adapters.crm.hubspot import HubSpotCRMAdapter
        adapter = HubSpotCRMAdapter(db)

        # Create or find contact
        if not contact.hubspot_id:
            crm_contact = adapter.create_contact({
                "email": contact.email,
                "first_name": contact.first_name or "",
                "last_name": contact.last_name or "",
                "title": contact.title or "",
                "company": contact.client_name or "",
            })
            if crm_contact and crm_contact.get("id"):
                contact.hubspot_id = str(crm_contact["id"])

        # Add note with email content
        if contact.hubspot_id:
            adapter.create_note(
                contact_id=contact.hubspot_id,
                body=f"[Interested Reply] Subject: {message.subject or 'N/A'}\n\n{message.body_text or message.body_html or ''}",
            )
    except Exception as e:
        raise e


def _forward_to_salesforce(contact: ContactDetails, message: InboxMessage, db: Session):
    """Create/update contact and add note in Salesforce."""
    try:
        from app.services.adapters.crm.salesforce import SalesforceCRMAdapter
        adapter = SalesforceCRMAdapter(db)

        if not contact.salesforce_id:
            crm_contact = adapter.create_contact({
                "email": contact.email,
                "first_name": contact.first_name or "",
                "last_name": contact.last_name or "",
                "title": contact.title or "",
                "company": contact.client_name or "",
            })
            if crm_contact and crm_contact.get("id"):
                contact.salesforce_id = str(crm_contact["id"])

        if contact.salesforce_id:
            adapter.create_note(
                contact_id=contact.salesforce_id,
                body=f"[Interested Reply] Subject: {message.subject or 'N/A'}\n\n{message.body_text or message.body_html or ''}",
            )
    except Exception as e:
        raise e
