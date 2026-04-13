"""Contact enrichment pipeline service."""
import json
import re
from datetime import datetime
from typing import Dict, Any, Optional
from urllib.parse import urlparse
import structlog

from app.db.base import SessionLocal
from app.db.models.lead import LeadDetails, LeadStatus, CLOSED_STATUSES
from app.db.models.contact import ContactDetails
from app.db.models.lead_contact import LeadContactAssociation
from app.db.models.client import ClientInfo
from app.db.models.job_run import JobRun, JobStatus
from app.core.config import settings
from app.core.settings_resolver import get_tenant_setting
from app.services.adapters.contact_discovery.mock import MockContactDiscoveryAdapter
from app.services.adapters.base import CreditsExhaustedError
from app.services.adapters.contact_discovery.apollo import ApolloAdapter, ApolloCreditsExhaustedError
from app.services.adapters.contact_discovery.seamless import SeamlessAdapter
from app.services.pipelines.cancel_helper import check_cancel

logger = structlog.get_logger()


def get_contact_discovery_adapters(db=None, tenant_id=None):
    """Get all configured contact discovery adapters with DB-stored API keys."""
    from app.services.adapters.contact_discovery.hunter_contact import HunterContactAdapter
    from app.services.adapters.contact_discovery.snovio import SnovioAdapter
    from app.services.adapters.contact_discovery.rocketreach import RocketReachAdapter
    from app.services.adapters.contact_discovery.pdl import PDLAdapter
    from app.services.adapters.contact_discovery.proxycurl import ProxycurlAdapter

    adapters = []

    providers = [settings.CONTACT_PROVIDER]
    if db:
        db_providers = get_tenant_setting(db, "contact_providers", tenant_id=tenant_id)
        if db_providers and isinstance(db_providers, list) and len(db_providers) > 0:
            providers = db_providers

    apollo_key = settings.APOLLO_API_KEY
    seamless_key = settings.SEAMLESS_API_KEY
    if db:
        db_apollo_key = get_tenant_setting(db, "apollo_api_key", tenant_id=tenant_id, default="")
        db_seamless_key = get_tenant_setting(db, "seamless_api_key", tenant_id=tenant_id, default="")
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
        elif p == "hunter_contact":
            key = get_tenant_setting(db, "hunter_contact_api_key", tenant_id=tenant_id, default="") if db else ""
            if not key:
                logger.error("Hunter.io selected but no API key configured in Settings")
                continue
            adapters.append(("hunter_contact", HunterContactAdapter(api_key=key)))
            logger.info("Hunter.io contact adapter configured")
        elif p == "snovio":
            client_id = get_tenant_setting(db, "snovio_client_id", tenant_id=tenant_id, default="") if db else ""
            client_secret = get_tenant_setting(db, "snovio_client_secret", tenant_id=tenant_id, default="") if db else ""
            if not client_id or not client_secret:
                logger.error("Snov.io selected but credentials not configured in Settings")
                continue
            adapters.append(("snovio", SnovioAdapter(client_id=client_id, client_secret=client_secret)))
            logger.info("Snov.io adapter configured")
        elif p == "rocketreach":
            key = get_tenant_setting(db, "rocketreach_api_key", tenant_id=tenant_id, default="") if db else ""
            if not key:
                logger.error("RocketReach selected but no API key configured in Settings")
                continue
            adapters.append(("rocketreach", RocketReachAdapter(api_key=key)))
            logger.info("RocketReach adapter configured")
        elif p == "pdl":
            key = get_tenant_setting(db, "pdl_api_key", tenant_id=tenant_id, default="") if db else ""
            if not key:
                logger.error("PDL selected but no API key configured in Settings")
                continue
            adapters.append(("pdl", PDLAdapter(api_key=key)))
            logger.info("People Data Labs adapter configured")
        elif p == "proxycurl":
            key = get_tenant_setting(db, "proxycurl_api_key", tenant_id=tenant_id, default="") if db else ""
            if not key:
                logger.error("Proxycurl selected but no API key configured in Settings")
                continue
            adapters.append(("proxycurl", ProxycurlAdapter(api_key=key)))
            logger.info("Proxycurl adapter configured")
        elif p == "mock":
            adapters.append(("mock", MockContactDiscoveryAdapter()))

    if not adapters:
        logger.error("No contact discovery adapters could be configured! Check API keys in Settings.")

    logger.info(f"Contact discovery providers: {[a[0] for a in adapters]}")
    return adapters


def _extract_domain(url: str | None) -> str | None:
    """Extract bare domain from a URL or domain string.

    Examples:
        "https://www.cognizant.com/us" -> "cognizant.com"
        "www.cognizant.com" -> "cognizant.com"
        "cognizant.com" -> "cognizant.com"
        None -> None
    """
    if not url or not url.strip():
        return None
    url = url.strip()
    # Add scheme if missing so urlparse works
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        host = urlparse(url).hostname
        if not host:
            return None
        # Strip www. prefix
        if host.startswith("www."):
            host = host[4:]
        # Basic validation: must contain a dot
        if "." not in host:
            return None
        return host.lower()
    except Exception:
        return None


def _resolve_domain(db, lead) -> str | None:
    """Resolve company domain from lead's employer_website or ClientInfo.domain."""
    # 1. Try lead's employer_website first (most specific)
    domain = _extract_domain(getattr(lead, "employer_website", None))
    if domain:
        return domain
    # 2. Fall back to ClientInfo.domain or website
    if lead.client_name:
        client = db.query(ClientInfo).filter(
            ClientInfo.client_name == lead.client_name
        ).first()
        if client:
            if client.domain:
                return _extract_domain(client.domain) or client.domain.lower().strip()
            if client.website:
                return _extract_domain(client.website)
    return None


def _reuse_existing_contacts(db, lead, max_contacts: int, lead_domain: str | None = None) -> int:
    """
    Check DB for contacts at the same company NOT already linked to this lead.
    Associate them via LeadContactAssociation. Return count reused.

    Uses domain-based matching (email domain) as primary strategy to handle
    company name variations (e.g. "Cognizant" vs "Cognizant Technologies" vs "CTS").
    Falls back to exact client_name match when domain is unavailable.
    """
    existing_cids = set()
    for row in db.query(LeadContactAssociation).filter(
        LeadContactAssociation.lead_id == lead.lead_id
    ).with_entities(LeadContactAssociation.contact_id).all():
        existing_cids.add(row[0])
    for c in db.query(ContactDetails).filter(
        ContactDetails.lead_id == lead.lead_id
    ).with_entities(ContactDetails.contact_id).all():
        existing_cids.add(c[0])

    existing_count = len(existing_cids)
    needed = max_contacts - existing_count
    if needed <= 0:
        return 0

    from sqlalchemy import or_
    conditions = []
    # Primary: match by email domain (handles name variations like Cognizant/CTS)
    if lead_domain:
        conditions.append(ContactDetails.email.like(f"%@{lead_domain}"))
    # Fallback: exact client_name match (covers cases where domain is unavailable)
    if lead.client_name:
        conditions.append(ContactDetails.client_name == lead.client_name)

    if not conditions:
        return 0

    query = db.query(ContactDetails).filter(or_(*conditions))
    if existing_cids:
        query = query.filter(~ContactDetails.contact_id.in_(list(existing_cids)))
    reusable = query.limit(needed).all()

    reused = 0
    for contact in reusable:
        try:
            assoc = LeadContactAssociation(
                lead_id=lead.lead_id,
                contact_id=contact.contact_id,
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
        row = db.query(LeadContactAssociation).filter(
            LeadContactAssociation.lead_id == lead.lead_id
        ).with_entities(LeadContactAssociation.contact_id).first()
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


def _auto_enrich_company_siblings(db, client_name, batch_lead_ids, max_contacts, lead_results, counters, lead_domain: str | None = None):
    """Find all unenriched leads at the same company and auto-link cached contacts.

    Uses domain-based matching (employer_website) in addition to exact client_name
    to catch leads for the same company under different name variations.
    """
    from sqlalchemy import or_
    conditions = [LeadDetails.client_name == client_name]
    # Also find siblings whose employer_website resolves to the same domain
    if lead_domain:
        conditions.append(LeadDetails.employer_website.like(f"%{lead_domain}%"))

    sibling_leads = db.query(LeadDetails).filter(
        or_(*conditions),
        LeadDetails.first_name.is_(None),
        ~LeadDetails.lead_status.in_(CLOSED_STATUSES),
        LeadDetails.is_archived == False,
        ~LeadDetails.lead_id.in_(list(batch_lead_ids))
    ).all()

    for sibling in sibling_leads:
        sibling_domain = lead_domain or _resolve_domain(db, sibling)
        reused = _reuse_existing_contacts(db, sibling, max_contacts, lead_domain=sibling_domain)
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
    run_id: int | None = None,
    tenant_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Run the contact enrichment pipeline.

    Steps:
    1. Select leads with blank contact info
    2. Search for decision-makers using provider
    3. Store contacts with priority levels
    4. Update lead records
    5. Insert into junction table for many-to-many support

    Args:
        triggered_by: Who triggered the pipeline
        lead_ids: Optional list of specific lead IDs to enrich
        run_id: Optional pre-created job run ID
    """
    db = SessionLocal()
    counters = {"contacts_found": 0, "leads_enriched": 0, "skipped": 0, "errors": 0, "contacts_reused": 0, "api_calls_saved": 0, "auto_enriched_leads": 0, "waterfall_skipped": 0}
    lead_results = []
    auto_enriched_companies = set()  # tracks client_name AND domain to avoid re-processing
    adapter_stats: Dict[str, Dict[str, int]] = {}  # per-adapter call/result tracking
    adapter_errors: Dict[str, str] = {}  # last error per adapter

    # Reuse pre-created job run or create a new one
    if run_id:
        job_run = db.query(JobRun).filter(JobRun.run_id == run_id).first()
        if job_run:
            job_run.status = JobStatus.RUNNING
            job_run.started_at = datetime.utcnow()
            db.commit()
        else:
            job_run = JobRun(tenant_id=tenant_id or 1, pipeline_name="contact_enrichment", status=JobStatus.RUNNING, triggered_by=triggered_by)
            db.add(job_run)
            db.commit()
    else:
        job_run = JobRun(tenant_id=tenant_id or 1, pipeline_name="contact_enrichment", status=JobStatus.RUNNING, triggered_by=triggered_by)
        db.add(job_run)
        db.commit()

    try:
        logger.info("Starting contact enrichment pipeline")

        adapters = get_contact_discovery_adapters(db, tenant_id=tenant_id)
        if not adapters:
            raise RuntimeError("No contact discovery adapters configured. Add API keys in Settings page.")

        from app.core.settings_resolver import get_tenant_setting
        _mc = get_tenant_setting(db, "max_contacts_per_company_job", tenant_id=tenant_id, default=None)
        max_contacts_per_job = int(_mc) if _mc is not None else settings.MAX_CONTACTS_PER_COMPANY_PER_JOB

        if lead_ids:
            q = db.query(LeadDetails).filter(
                LeadDetails.lead_id.in_(lead_ids),
                ~LeadDetails.lead_status.in_(CLOSED_STATUSES),
                LeadDetails.is_archived == False
            )
            if tenant_id is not None:
                q = q.filter(LeadDetails.tenant_id == tenant_id)
            leads = q.all()
        else:
            q = db.query(LeadDetails).filter(
                LeadDetails.first_name.is_(None),
                LeadDetails.lead_status == LeadStatus.NEW,
                LeadDetails.is_archived == False
            )
            if tenant_id is not None:
                q = q.filter(LeadDetails.tenant_id == tenant_id)
            leads = q.limit(100).all()

        logger.info(f"Found {len(leads)} leads to enrich")
        batch_lead_ids = {l.lead_id for l in leads}
        total_leads = len(leads)

        for idx, lead in enumerate(leads):
            # Cancel check
            if check_cancel(job_run.run_id, db):
                logger.info("Contact enrichment cancelled by user", processed=idx)
                break

            # Update progress every 5 items
            if total_leads > 0 and idx % 5 == 0:
                job_run.progress_pct = int((idx / total_leads) * 100)
                db.commit()
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

                lead_domain = _resolve_domain(db, lead)

                reused = _reuse_existing_contacts(db, lead, max_contacts_per_job, lead_domain=lead_domain)
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
                    company_key = lead_domain or lead.client_name
                    if company_key and company_key not in auto_enriched_companies:
                        auto_enriched_companies.add(company_key)
                        if lead.client_name:
                            auto_enriched_companies.add(lead.client_name)
                        _auto_enrich_company_siblings(db, lead.client_name, batch_lead_ids, max_contacts_per_job, lead_results, counters, lead_domain=lead_domain)
                    continue

                needed = max_contacts_per_job - existing_count
                contacts = []
                adapters_used_for_lead = []
                for adapter_name, adapter in adapters:
                    if adapter_name not in adapter_stats:
                        adapter_stats[adapter_name] = {"calls": 0, "contacts_returned": 0, "no_results": 0, "errors": 0, "waterfall_skipped": 0}
                    # Waterfall: skip remaining adapters once we have enough
                    remaining_needed = needed - len(contacts)
                    if remaining_needed <= 0:
                        adapter_stats[adapter_name]["waterfall_skipped"] = adapter_stats[adapter_name].get("waterfall_skipped", 0) + 1
                        counters["waterfall_skipped"] += 1
                        continue
                    try:
                        adapter_stats[adapter_name]["calls"] += 1
                        adapters_used_for_lead.append(adapter_name)
                        result = adapter.search_contacts(
                            company_name=lead.client_name,
                            job_title=lead.job_title,
                            state=lead.state,
                            limit=remaining_needed,
                            domain=lead_domain,
                        )
                        for c in result:
                            c["source"] = c.get("source", adapter_name)
                        contacts.extend(result)
                        adapter_stats[adapter_name]["contacts_returned"] += len(result)
                        if len(result) == 0:
                            adapter_stats[adapter_name]["no_results"] += 1
                        logger.debug(f"Adapter {adapter_name} returned {len(result)} contacts for {lead.client_name}")
                    except ApolloCreditsExhaustedError:
                        adapter_stats[adapter_name]["errors"] += 1
                        adapter_errors[adapter_name] = "Apollo credits exhausted"
                        raise
                    except CreditsExhaustedError as e:
                        logger.warning(f"Adapter {adapter_name} credits exhausted, skipping to next: {e}")
                        adapter_stats[adapter_name]["errors"] += 1
                        adapter_errors[adapter_name] = str(e)[:200]
                        continue
                    except Exception as e:
                        logger.error(f"Adapter {adapter_name} failed for {lead.client_name}: {e}")
                        adapter_stats[adapter_name]["errors"] += 1
                        adapter_errors[adapter_name] = str(e)[:200]
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
                    adapter_names = ", ".join(adapters_used_for_lead) if adapters_used_for_lead else ", ".join(a[0] for a in adapters)
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

                        # Defensive: skip contacts missing required fields
                    c_first = contact_data.get("first_name") or ""
                    c_last = contact_data.get("last_name") or ""
                    c_email = contact_data.get("email")
                    if not c_email:
                        continue
                    # Ensure at least one name part exists
                    if not c_first and not c_last:
                        c_first = c_email.split("@")[0].capitalize()

                    contact = ContactDetails(
                        tenant_id=tenant_id or lead.tenant_id or 1,
                        lead_id=lead.lead_id,
                        client_name=lead.client_name,
                        first_name=c_first,
                        last_name=c_last,
                        title=contact_data.get("title"),
                        email=c_email,
                        location_state=contact_data.get("location_state") or lead.state,
                        phone=contact_data.get("phone"),
                        source=contact_source,
                        priority_level=contact_data.get("priority_level"),
                        validation_status=val_status,
                    )
                    db.add(contact)
                    db.flush()

                    assoc = LeadContactAssociation(
                        lead_id=lead.lead_id,
                        contact_id=contact.contact_id,
                    )
                    db.add(assoc)

                    counters["contacts_found"] += 1
                    contacts_added += 1

                if contacts:
                    first_contact = contacts[0]
                    lead.first_name = first_contact.get("first_name") or first_contact.get("email", "").split("@")[0].capitalize()
                    lead.last_name = first_contact.get("last_name") or ""
                    lead.contact_title = first_contact.get("title")
                    lead.contact_email = first_contact.get("email")
                    lead.contact_phone = first_contact.get("phone")
                    lead.contact_source = first_contact.get("source")
                    lead.lead_status = LeadStatus.ENRICHED
                    counters["leads_enriched"] += 1

                adapter_names = ", ".join(adapters_used_for_lead) if adapters_used_for_lead else ", ".join(a[0] for a in adapters)
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

                company_key = lead_domain or lead.client_name
                if company_key and company_key not in auto_enriched_companies:
                    auto_enriched_companies.add(company_key)
                    if lead.client_name:
                        auto_enriched_companies.add(lead.client_name)
                    _auto_enrich_company_siblings(db, lead.client_name, batch_lead_ids, max_contacts_per_job, lead_results, counters, lead_domain=lead_domain)

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
                db.rollback()  # Rollback dirty session state from failed flush/insert
                logger.error("Error enriching lead", error=str(e), lead_id=lead.lead_id)
                counters["errors"] += 1
                lead_results.append({
                    "lead_id": lead.lead_id, "client_name": lead.client_name,
                    "status": "error", "contacts_found": 0, "contacts_reused": 0,
                    "adapter_used": None, "reason": str(e)[:200]
                })

        db.commit()

        db.refresh(job_run)
        if job_run.is_cancel_requested == 1:
            job_run.status = JobStatus.CANCELLED
        else:
            job_run.status = JobStatus.COMPLETED
        job_run.progress_pct = 100
        job_run.ended_at = datetime.utcnow()
        # Build api_diagnostics from adapter_stats
        api_diag = []
        for aname, astats in adapter_stats.items():
            diag_status = "success"
            diag_error_type = None
            diag_error_msg = None
            if astats["errors"] > 0:
                diag_status = "error"
                err_msg = adapter_errors.get(aname, "Unknown error")
                if "credits" in err_msg.lower() or "exhausted" in err_msg.lower():
                    diag_error_type = "credits_exhausted"
                elif "401" in err_msg or "unauthorized" in err_msg.lower():
                    diag_error_type = "api_key_invalid"
                else:
                    diag_error_type = "unknown"
                diag_error_msg = err_msg
            elif astats["no_results"] > astats["calls"] * 0.5:
                diag_status = "warning"
                diag_error_type = "low_results"
            api_diag.append({
                "adapter": aname,
                "status": diag_status,
                "total_calls": astats["calls"],
                "contacts_returned": astats["contacts_returned"],
                "error_type": diag_error_type,
                "error_message": diag_error_msg,
            })

        counters["adapter_stats"] = adapter_stats
        counters["api_diagnostics"] = api_diag
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
        # Still save adapter stats even on failure
        counters["adapter_stats"] = adapter_stats
        api_diag = []
        for aname, astats in adapter_stats.items():
            err_msg = adapter_errors.get(aname)
            api_diag.append({
                "adapter": aname, "status": "error" if astats["errors"] > 0 else "success",
                "total_calls": astats["calls"], "contacts_returned": astats["contacts_returned"],
                "error_type": "credits_exhausted" if err_msg and "credits" in err_msg.lower() else None,
                "error_message": err_msg,
            })
        counters["api_diagnostics"] = api_diag
        job_run.counters_json = json.dumps(counters)
        job_run.lead_results_json = json.dumps(lead_results)
        db.commit()
        raise
    finally:
        db.close()
