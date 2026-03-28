"""Bidirectional CRM sync engine — pull contacts from CRM, push deals to CRM."""
import json
from datetime import datetime
from typing import Dict, Any, Optional
import structlog

from sqlalchemy.orm import Session

from app.db.models.contact import ContactDetails
from app.db.models.deal import Deal
from app.db.models.crm_sync_log import CRMSyncLog

logger = structlog.get_logger()


def sync_contacts_from_crm(crm_type: str, db: Session) -> Dict[str, Any]:
    """Pull contacts from HubSpot/Salesforce and create/update in Exzelon.

    Returns: {synced: int, skipped: int, errors: int}
    """
    log = CRMSyncLog(
        tenant_id=1,
        crm_type=crm_type,
        direction="pull",
        entity_type="contacts",
        started_at=datetime.utcnow(),
    )
    db.add(log)
    db.flush()

    result = {"synced": 0, "skipped": 0, "errors": 0}

    try:
        if crm_type == "hubspot":
            contacts = _pull_hubspot_contacts(db)
        elif crm_type == "salesforce":
            contacts = _pull_salesforce_contacts(db)
        else:
            raise ValueError(f"Unknown CRM type: {crm_type}")

        for crm_contact in contacts:
            try:
                email = crm_contact.get("email", "").lower().strip()
                if not email:
                    result["skipped"] += 1
                    continue

                existing = db.query(ContactDetails).filter(
                    ContactDetails.email == email
                ).first()

                if existing:
                    # Update CRM ID
                    if crm_type == "hubspot" and crm_contact.get("id"):
                        existing.hubspot_id = str(crm_contact["id"])
                    elif crm_type == "salesforce" and crm_contact.get("id"):
                        existing.salesforce_id = str(crm_contact["id"])
                    result["skipped"] += 1
                else:
                    new_contact = ContactDetails(
                        email=email,
                        first_name=crm_contact.get("first_name", ""),
                        last_name=crm_contact.get("last_name", ""),
                        title=crm_contact.get("title", ""),
                        client_name=crm_contact.get("company", ""),
                        source=crm_type,
                        hubspot_id=str(crm_contact["id"]) if crm_type == "hubspot" and crm_contact.get("id") else None,
                        salesforce_id=str(crm_contact["id"]) if crm_type == "salesforce" and crm_contact.get("id") else None,
                    )
                    db.add(new_contact)
                    result["synced"] += 1
            except Exception as e:
                logger.warning("Error syncing CRM contact", error=str(e))
                result["errors"] += 1

        db.commit()

    except Exception as e:
        logger.error("CRM contact sync failed", crm=crm_type, error=str(e))
        log.errors = str(e)[:1000]
        result["errors"] += 1

    log.records_synced = result["synced"]
    log.completed_at = datetime.utcnow()
    if result["errors"] > 0 and not log.errors:
        log.errors = f"{result['errors']} individual contact errors"
    db.commit()

    return result


def sync_deals_to_crm(crm_type: str, db: Session) -> Dict[str, Any]:
    """Push new/updated deals to CRM.

    Returns: {synced: int, skipped: int, errors: int}
    """
    log = CRMSyncLog(
        tenant_id=1,
        crm_type=crm_type,
        direction="push",
        entity_type="deals",
        started_at=datetime.utcnow(),
    )
    db.add(log)
    db.flush()

    result = {"synced": 0, "skipped": 0, "errors": 0}

    try:
        deals = db.query(Deal).filter(
            Deal.is_archived == False,
        ).all()

        for deal in deals:
            try:
                deal_data = {
                    "name": deal.name,
                    "value": float(deal.value) if deal.value else 0,
                    "probability": deal.probability,
                    "contact_id": deal.contact_id,
                }

                if crm_type == "hubspot":
                    _push_deal_to_hubspot(deal_data, db)
                elif crm_type == "salesforce":
                    _push_deal_to_salesforce(deal_data, db)

                result["synced"] += 1
            except Exception as e:
                logger.warning("Error pushing deal to CRM", deal_id=deal.deal_id, error=str(e))
                result["errors"] += 1

    except Exception as e:
        logger.error("CRM deal sync failed", crm=crm_type, error=str(e))
        log.errors = str(e)[:1000]

    log.records_synced = result["synced"]
    log.completed_at = datetime.utcnow()
    db.commit()

    return result


def run_crm_sync(db: Session, tenant_id: Optional[int] = None) -> Dict[str, Any]:
    """Run full bidirectional CRM sync. Called by scheduler."""
    from app.core.settings_resolver import get_tenant_setting

    results = {}

    # Check which CRMs are configured
    hubspot_key = get_tenant_setting(db, "hubspot_api_key", tenant_id=tenant_id, default="")
    salesforce_id = get_tenant_setting(db, "salesforce_client_id", tenant_id=tenant_id, default="")

    if hubspot_key:
        logger.info("Running HubSpot sync")
        results["hubspot_pull"] = sync_contacts_from_crm("hubspot", db)
        results["hubspot_push"] = sync_deals_to_crm("hubspot", db)

    if salesforce_id:
        logger.info("Running Salesforce sync")
        results["salesforce_pull"] = sync_contacts_from_crm("salesforce", db)
        results["salesforce_push"] = sync_deals_to_crm("salesforce", db)

    if not hubspot_key and not salesforce_id:
        results["status"] = "no_crm_configured"

    return results


def _pull_hubspot_contacts(db: Session):
    """Pull contacts from HubSpot API."""
    try:
        from app.services.adapters.crm.hubspot import HubSpotCRMAdapter
        adapter = HubSpotCRMAdapter(db)
        return adapter.list_contacts(limit=100)
    except Exception as e:
        logger.error("HubSpot contact pull failed", error=str(e))
        return []


def _pull_salesforce_contacts(db: Session):
    """Pull contacts from Salesforce API."""
    try:
        from app.services.adapters.crm.salesforce import SalesforceCRMAdapter
        adapter = SalesforceCRMAdapter(db)
        return adapter.list_contacts(limit=100)
    except Exception as e:
        logger.error("Salesforce contact pull failed", error=str(e))
        return []


def _push_deal_to_hubspot(deal_data: dict, db: Session):
    """Push a deal to HubSpot."""
    try:
        from app.services.adapters.crm.hubspot import HubSpotCRMAdapter
        adapter = HubSpotCRMAdapter(db)
        adapter.create_deal(deal_data)
    except Exception as e:
        raise e


def _push_deal_to_salesforce(deal_data: dict, db: Session):
    """Push a deal to Salesforce."""
    try:
        from app.services.adapters.crm.salesforce import SalesforceCRMAdapter
        adapter = SalesforceCRMAdapter(db)
        adapter.create_deal(deal_data)
    except Exception as e:
        raise e
