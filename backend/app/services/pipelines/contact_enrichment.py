"""Contact enrichment pipeline service."""
import json
from datetime import datetime
from typing import Dict, Any
import structlog

from app.db.base import SessionLocal
from app.db.models.lead import LeadDetails, LeadStatus, CLOSED_STATUSES
from app.db.models.contact import ContactDetails
from app.db.models.lead_contact import LeadContactAssociation
from app.db.models.client import ClientInfo
from app.db.models.job_run import JobRun, JobStatus
from app.core.config import settings
from app.services.adapters.contact_discovery.mock import MockContactDiscoveryAdapter
from app.services.adapters.contact_discovery.apollo import ApolloAdapter, ApolloCreditsExhaustedError
from app.services.adapters.contact_discovery.seamless import SeamlessAdapter

logger = structlog.get_logger()


def _get_db_setting(db, key, default=None):
    """Read a setting value from the DB settings table."""
    import json as _json
    from app.db.models.settings import Settings
    try:
        setting = db.query(Settings).filter(Settings.key == key).first()
        if setting and setting.value_json:
            val = _json.loads(setting.value_json)
            return val
    except Exception as e:
        logger.warning(f"Error reading setting {key}: {e}")
    return default


def get_contact_discovery_adapters(db=None):
    """Get all configured contact discovery adapters with DB-stored API keys."""
    import json as _json
    adapters = []

    providers = [settings.CONTACT_PROVIDER]
    if db:
        db_providers = _get_db_setting(db, "contact_providers")
        if db_providers and isinstance(db_providers, list) and len(db_providers) > 0:
            providers = db_providers

    apollo_key = settings.APOLLO_API_KEY
    seamless_key = settings.SEAMLESS_API_KEY
    if db:
        db_apollo_key = _get_db_setting(db, "apollo_api_key", "")
        db_seamless_key = _get_db_setting(db, "seamless_api_key", "")
        if db_apollo_key:
            apollo_key = db_apollo_key
        if db_seamless_key:
            seamless_key = db_seamless_key

    for p in providers:
        if p == "apollo":
            if not apollo_key:
                logger.error("Apollo selected but no API key configured in Settings")
                continue
            adapters.append(("apollo", ApolloAdapter(api_key=apollo_key)))
            logger.info("Apollo adapter configured", has_key=bool(apollo_key))
        elif p == "seamless":
            if not seamless_key:
                logger.error("Seamless selected but no API key configured in Settings")
                continue
            adapters.append(("seamless", SeamlessAdapter(api_key=seamless_key)))
            logger.info("Seamless adapter configured", has_key=bool(seamless_key))
        elif p == "mock":
            adapters.append(("mock", MockContactDiscoveryAdapter()))

    if not adapters:
        logger.error("No contact discovery adapters could be configured! Check API keys in Settings.")

    logger.info(f"Contact discovery providers: {[a[0] for a in adapters]}")
    return adapters


def _reuse_existing_contacts(db, lead, max_contacts: int) -> int:
    """
    Check DB for contacts at the same company NOT already linked to this lead.
    Associate them via LeadContactAssociation. Return count reused.
    """
    existing_cids = set()
    for row in db.query(LeadContactAssociation.contact_id).filter(
        LeadContactAssociation.lead_id == lead.lead_id
    ).all():
        existing_cids.add(row[0])
    for c in db.query(ContactDetails.contact_id).filter(
        ContactDetails.lead_id == lead.lead_id
    ).all():
        existing_cids.add(c[0])

    existing_count = len(existing_cids)
    needed = max_contacts - existing_count
    if needed <= 0:
        return 0

    query = db.query(ContactDetails).filter(
        ContactDetails.client_name == lead.client_name
    )
    if existing_cids:
        query = query.filter(~ContactDetails.contact_id.in_(list(existing_cids)))
    reusable = query.limit(needed).all()

    reused = 0
    for contact in reusable:
        try:
            assoc = LeadContactAssociation(
                lead_id=lead.lead_id,
                contact_id=contact.contact_id
            )
            db.add(assoc)
            db.flush()
            reused += 1
        except Exception:
            db.rollback()
    return reused


def _update_lead_from_contacts(db, lead):
    """Update lead denormalized fields from its linked contacts."""
    contact = db.query(ContactDetails).filter(
        ContactDetails.lead_id == lead.lead_id
    ).first()
    if not contact:
        row = db.query(LeadContactAssociation.contact_id).filter(
            LeadContactAssociation.lead_id == lead.lead_id
        ).first()
        if row:
            contact = db.query(ContactDetails).filter(
                ContactDetails.contact_id == row[0]
            ).first()
    if contact:
        lead.first_name = contact.first_name
        lead.last_name = contact.last_name
        lead.contact_title = contact.title
        lead.contact_email = contact.email
        lead.contact_phone = contact.phone
        lead.contact_source = contact.source
        lead.lead_status = LeadStatus.ENRICHED


def _auto_enrich_company_siblings(db, client_name, batch_lead_ids, max_contacts, lead_results, counters):
    """Find all unenriched leads at the same company and auto-link cached contacts."""
    sibling_leads = db.query(LeadDetails).filter(
        LeadDetails.client_name == client_name,
        LeadDetails.first_name.is_(None),
        ~LeadDetails.lead_status.in_(CLOSED_STATUSES),
        LeadDetails.is_archived == False,
        ~LeadDetails.lead_id.in_(list(batch_lead_ids))
    ).all()

    for sibling in sibling_leads:
        reused = _reuse_existing_contacts(db, sibling, max_contacts)
        if reused > 0:
            _update_lead_from_contacts(db, sibling)
            counters["auto_enriched_leads"] += 1
            counters["contacts_found"] += reused
            counters["leads_enriched"] += 1
            lead_results.append({
                "lead_id": sibling.lead_id, "client_name": sibling.client_name,
                "status": "auto_enriched", "contacts_found": 0,
                "contacts_reused": reused, "adapter_used": None,
                "reason": f"Auto-linked {reused} contact(s) from company cache"
            })


def run_contact_enrichment_pipeline(
    triggered_by: str = "system",
    lead_ids: list | None = None,
    run_id: int | None = None
) -> Dict[str, Any]:
    """
    Run the contact enrichment pipeline.

    Steps:
    1. Select leads with blank contact info
    2. Search for decision-makers using provider
    3. Store contacts with priority levels
    4. Update lead records
    5. Insert into junction table for many-to-many support
    """
    db = SessionLocal()
    counters = {"contacts_found": 0, "leads_enriched": 0, "skipped": 0, "errors": 0, "contacts_reused": 0, "api_calls_saved": 0, "auto_enriched_leads": 0}
    lead_results = []
    auto_enriched_companies = set()

    # Reuse pre-created job run or create a new one
    if run_id:
        job_run = db.query(JobRun).filter(JobRun.run_id == run_id).first()
        if job_run:
            job_run.status = JobStatus.RUNNING
            job_run.started_at = datetime.utcnow()
            db.commit()
        else:
            job_run = JobRun(pipeline_name="contact_enrichment", status=JobStatus.RUNNING, triggered_by=triggered_by)
            db.add(job_run)
            db.commit()
    else:
        job_run = JobRun(pipeline_name="contact_enrichment", status=JobStatus.RUNNING, triggered_by=triggered_by)
        db.add(job_run)
        db.commit()

    try:
        logger.info("Starting contact enrichment pipeline")

        adapters = get_contact_discovery_adapters(db)
        if not adapters:
            raise RuntimeError("No contact discovery adapters configured. Add API keys in Settings page.")

        max_contacts_per_job = settings.MAX_CONTACTS_PER_COMPANY_PER_JOB

        if lead_ids:
            leads = db.query(LeadDetails).filter(
                LeadDetails.lead_id.in_(lead_ids),
                ~LeadDetails.lead_status.in_(CLOSED_STATUSES),
                LeadDetails.is_archived == False
            ).all()
        else:
            leads = db.query(LeadDetails).filter(
                LeadDetails.first_name.is_(None),
                LeadDetails.lead_status == LeadStatus.NEW,
                LeadDetails.is_archived == False
            ).limit(100).all()

        logger.info(f"Found {len(leads)} leads to enrich")
        batch_lead_ids = {l.lead_id for l in leads}

        for lead in leads:
            try:
                existing_count = db.query(ContactDetails).filter(
                    ContactDetails.lead_id == lead.lead_id
                ).count()

                if existing_count >= max_contacts_per_job:
                    counters["skipped"] += 1
                    lead_results.append({
                        "lead_id": lead.lead_id, "client_name": lead.client_name,
                        "status": "skipped", "contacts_found": 0, "contacts_reused": 0,
                        "adapter_used": None,
                        "reason": f"Already at max contacts ({existing_count}/{max_contacts_per_job})"
                    })
                    logger.debug("Lead already has max contacts", lead_id=lead.lead_id, count=existing_count)
                    continue

                reused = _reuse_existing_contacts(db, lead, max_contacts_per_job)
                counters["contacts_reused"] += reused
                counters["contacts_found"] += reused

                existing_count += reused
                if existing_count >= max_contacts_per_job:
                    counters["api_calls_saved"] += 1
                    if not lead.first_name:
                        _update_lead_from_contacts(db, lead)
                    counters["leads_enriched"] += 1
                    lead_results.append({
                        "lead_id": lead.lead_id, "client_name": lead.client_name,
                        "status": "cache_only", "contacts_found": 0, "contacts_reused": reused,
                        "adapter_used": None, "reason": "Fully satisfied from cache"
                    })
                    if lead.client_name and lead.client_name not in auto_enriched_companies:
                        auto_enriched_companies.add(lead.client_name)
                        _auto_enrich_company_siblings(db, lead.client_name, batch_lead_ids, max_contacts_per_job, lead_results, counters)
                    continue

                needed = max_contacts_per_job - existing_count
                contacts = []
                for adapter_name, adapter in adapters:
                    try:
                        result = adapter.search_contacts(
                            company_name=lead.client_name,
                            job_title=lead.job_title,
                            state=lead.state,
                            limit=needed
                        )
                        for c in result:
                            c["source"] = c.get("source", adapter_name)
                        contacts.extend(result)
                        logger.debug(f"Adapter {adapter_name} returned {len(result)} contacts for {lead.client_name}")
                    except ApolloCreditsExhaustedError:
                        raise
                    except Exception as e:
                        logger.error(f"Adapter {adapter_name} failed for {lead.client_name}: {e}")
                        counters["errors"] += 1

                seen_emails = set()
                unique_contacts = []
                for c in contacts:
                    if c["email"] not in seen_emails:
                        seen_emails.add(c["email"])
                        unique_contacts.append(c)
                contacts = unique_contacts[:needed]

                if not contacts:
                    counters["skipped"] += 1
                    adapter_names = ", ".join(a[0] for a in adapters)
                    lead_results.append({
                        "lead_id": lead.lead_id, "client_name": lead.client_name,
                        "status": "skipped", "contacts_found": 0, "contacts_reused": reused,
                        "adapter_used": adapter_names, "reason": "No results from API"
                    })
                    continue

                contacts_added = 0
                for contact_data in contacts:
                    existing = db.query(ContactDetails).filter(
                        ContactDetails.lead_id == lead.lead_id,
                        ContactDetails.email == contact_data["email"]
                    ).first()

                    if existing:
                        continue

                    contact_source = contact_data.get("source")
                    if contact_source in ("apollo", "seamless"):
                        val_status = "valid"
                    else:
                        val_status = "pending"

                    contact = ContactDetails(
                        lead_id=lead.lead_id,
                        client_name=lead.client_name,
                        first_name=contact_data["first_name"],
                        last_name=contact_data["last_name"],
                        title=contact_data.get("title"),
                        email=contact_data["email"],
                        location_state=contact_data.get("location_state") or lead.state,
                        phone=contact_data.get("phone"),
                        source=contact_source,
                        priority_level=contact_data.get("priority_level"),
                        validation_status=val_status
                    )
                    db.add(contact)
                    db.flush()

                    assoc = LeadContactAssociation(
                        lead_id=lead.lead_id,
                        contact_id=contact.contact_id
                    )
                    db.add(assoc)

                    counters["contacts_found"] += 1
                    contacts_added += 1

                if contacts:
                    first_contact = contacts[0]
                    lead.first_name = first_contact["first_name"]
                    lead.last_name = first_contact["last_name"]
                    lead.contact_title = first_contact.get("title")
                    lead.contact_email = first_contact["email"]
                    lead.contact_phone = first_contact.get("phone")
                    lead.contact_source = first_contact.get("source")
                    lead.lead_status = LeadStatus.ENRICHED
                    counters["leads_enriched"] += 1

                adapter_names = ", ".join(a[0] for a in adapters)
                lead_results.append({
                    "lead_id": lead.lead_id, "client_name": lead.client_name,
                    "status": "enriched", "contacts_found": contacts_added,
                    "contacts_reused": reused, "adapter_used": adapter_names,
                    "reason": None
                })

                logger.info("Enriched lead with contacts",
                           lead_id=lead.lead_id,
                           client=lead.client_name,
                           contacts_added=contacts_added)

                if lead.client_name and lead.client_name not in auto_enriched_companies:
                    auto_enriched_companies.add(lead.client_name)
                    _auto_enrich_company_siblings(db, lead.client_name, batch_lead_ids, max_contacts_per_job, lead_results, counters)

            except ApolloCreditsExhaustedError:
                logger.error("Apollo credits exhausted - stopping pipeline early. Upgrade at https://app.apollo.io/#/settings/plans/upgrade")
                counters["errors"] += 1
                lead_results.append({
                    "lead_id": lead.lead_id, "client_name": lead.client_name,
                    "status": "error", "contacts_found": 0, "contacts_reused": 0,
                    "adapter_used": "apollo", "reason": "Apollo credits exhausted"
                })
                break
            except Exception as e:
                logger.error("Error enriching lead", error=str(e), lead_id=lead.lead_id)
                counters["errors"] += 1
                lead_results.append({
                    "lead_id": lead.lead_id, "client_name": lead.client_name,
                    "status": "error", "contacts_found": 0, "contacts_reused": 0,
                    "adapter_used": None, "reason": str(e)[:200]
                })

        db.commit()

        job_run.status = JobStatus.COMPLETED
        job_run.ended_at = datetime.utcnow()
        job_run.counters_json = json.dumps(counters)
        job_run.lead_results_json = json.dumps(lead_results)
        db.commit()

        logger.info("Contact enrichment completed", counters=counters)
        return counters

    except Exception as e:
        logger.error("Contact enrichment pipeline failed", error=str(e))
        job_run.status = JobStatus.FAILED
        job_run.error_message = str(e)
        job_run.ended_at = datetime.utcnow()
        job_run.lead_results_json = json.dumps(lead_results)
        db.commit()
        raise
    finally:
        db.close()
