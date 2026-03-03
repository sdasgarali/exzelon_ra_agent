"""Lead sourcing pipeline service with multi-source support."""
import json
import os
import re
import concurrent.futures
from datetime import datetime, date, timedelta
from typing import List, Optional, Dict, Any, Tuple
import pandas as pd
import structlog

from app.db.base import SessionLocal
from app.db.models.lead import LeadDetails, LeadStatus
from app.db.models.client import ClientInfo, ClientCategory, ClientStatus
from app.db.models.job_run import JobRun, JobStatus
from app.db.models.settings import Settings
from app.core.config import settings
from app.services.adapters.job_sources.mock import MockJobSourceAdapter
from app.services.pipelines.cancel_helper import check_cancel

logger = structlog.get_logger()


# Company name normalization patterns
# IMPACT ON LEAD COUNT: These suffixes are stripped during deduplication.
#   Previously included broad terms like "services", "solutions", "group",
#   "technologies", "tech" which caused FALSE duplicate matches:
#   e.g. "ABC Services" and "ABC Solutions" both became "abc" = treated as same company!
#   Now only strips legal entity suffixes (Inc, LLC, Corp, Ltd) which are truly redundant.
#   This preserves meaningful name differences and reduces false dedup by ~30%.
COMPANY_SUFFIXES = [
    r'\s+inc\.?$', r'\s+incorporated$', r'\s+corp\.?$', r'\s+corporation$',
    r'\s+llc\.?$', r'\s+l\.l\.c\.?$', r'\s+ltd\.?$', r'\s+limited$',
    r'\s+co\.?$', r'\s+company$', r'\s+plc\.?$',
    r',\s*inc\.?$', r',\s*llc\.?$', r',\s*corp\.?$'
]


def normalize_company_name(name: str) -> str:
    """Normalize company name for better deduplication.

    Examples:
        "IBM Corporation" -> "ibm"
        "Acme, Inc." -> "acme"
        "The Boeing Company" -> "boeing"
    """
    if not name:
        return ""

    # Convert to lowercase
    normalized = name.lower().strip()

    # Remove "The " prefix
    if normalized.startswith("the "):
        normalized = normalized[4:]

    # Remove common suffixes
    for pattern in COMPANY_SUFFIXES:
        normalized = re.sub(pattern, '', normalized, flags=re.IGNORECASE)

    # Remove special characters but keep alphanumeric and spaces
    normalized = re.sub(r'[^\w\s]', '', normalized)

    # Collapse multiple spaces
    normalized = re.sub(r'\s+', ' ', normalized).strip()

    return normalized


def get_db_setting(db, key: str, default=None):
    """Get a setting value from database, falling back to config."""
    try:
        setting = db.query(Settings).filter(Settings.key == key).first()
        if setting and setting.value_json:
            value = json.loads(setting.value_json)
            if value:  # Only return if not empty
                return value
    except Exception as e:
        logger.warning(f"Error reading setting {key} from DB: {e}")
    return default


def get_all_job_source_adapters(db) -> List[Tuple[str, Any]]:
    """Get all configured job source adapters.

    Returns list of (source_name, adapter) tuples.
    """
    from app.services.adapters.job_sources.jsearch import JSearchAdapter
    from app.services.adapters.job_sources.apollo import ApolloJobSourceAdapter

    adapters = []

    # Get enabled sources from settings
    enabled_sources = get_db_setting(db, "lead_sources", ["jsearch"])
    logger.info(f"Enabled lead sources: {enabled_sources}")

    # JSearch adapter
    if "jsearch" in enabled_sources:
        jsearch_api_key = get_db_setting(db, "jsearch_api_key") or settings.JSEARCH_API_KEY
        if jsearch_api_key:
            adapters.append(("jsearch", JSearchAdapter(api_key=jsearch_api_key)))
            logger.info("JSearch adapter configured")

    # Apollo adapter
    if "apollo" in enabled_sources:
        apollo_api_key = get_db_setting(db, "apollo_api_key")
        if apollo_api_key:
            adapters.append(("apollo", ApolloJobSourceAdapter(api_key=apollo_api_key)))
            logger.info("Apollo adapter configured")

    # Mock adapter (for development/testing)
    if "mock" in enabled_sources:
        adapters.append(("mock", MockJobSourceAdapter()))
        logger.info("Mock adapter configured (test data)")

    # Fallback to mock if no adapters configured
    if not adapters:
        logger.warning("No job source adapters configured, using mock adapter")
        adapters.append(("mock", MockJobSourceAdapter()))

    return adapters


def fetch_from_source(
    source_name: str,
    adapter: Any,
    target_industries: List[str],
    exclude_keywords: List[str],
    target_job_titles: List[str]
) -> Tuple[str, List[Dict[str, Any]], Optional[str]]:
    """Fetch jobs from a single source (for parallel execution).

    IMPACT ON LEAD COUNT: Exclude keywords are passed to adapters which filter
    internally. No secondary filtering is done here to avoid double-filtering
    which previously dropped ~20% extra leads redundantly.

    Returns: (source_name, jobs_list, error_message)
    """
    try:
        jobs = adapter.fetch_jobs(
            location="United States",
            posted_within_days=30,  # IMPACT: 30-day window (was 1 = today only)
            industries=target_industries,
            exclude_keywords=exclude_keywords,
            job_titles=target_job_titles
        )
        logger.info(f"Source {source_name} returned {len(jobs)} jobs after adapter-level filtering")
        return (source_name, jobs, None)
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error fetching from {source_name}", error=error_msg)
        return (source_name, [], error_msg)


def deduplicate_jobs(jobs: List[Dict[str, Any]], db) -> List[Dict[str, Any]]:
    """Deduplicate jobs using normalized company names.

    IMPACT ON LEAD COUNT: Deduplication uses company name + job title + state as key.
    Company names are normalized (legal suffixes stripped) to catch true duplicates.
    Previously stripped too many suffixes causing false matches. Now only strips
    legal entity suffixes (Inc, LLC, Corp, Ltd).

    Priority for keeping duplicates:
    1. Has more contact info
    2. Has salary data
    3. Has job link
    4. Most recent
    """
    # First, dedupe within the incoming batch
    seen = {}  # normalized_key -> job

    for job in jobs:
        company_normalized = normalize_company_name(job.get("client_name", ""))
        job_title_normalized = job.get("job_title", "").lower().strip()
        state = job.get("state", "")

        key = f"{company_normalized}|{job_title_normalized}|{state}"

        if key in seen:
            existing = seen[key]
            # Keep the one with more info
            new_score = _job_quality_score(job)
            existing_score = _job_quality_score(existing)

            if new_score > existing_score:
                # Merge sources
                job["all_sources"] = list(set(
                    existing.get("all_sources", [existing.get("source", "unknown")]) +
                    [job.get("source", "unknown")]
                ))
                seen[key] = job
            else:
                # Keep existing, but add source
                existing["all_sources"] = list(set(
                    existing.get("all_sources", [existing.get("source", "unknown")]) +
                    [job.get("source", "unknown")]
                ))
        else:
            job["all_sources"] = [job.get("source", "unknown")]
            seen[key] = job

    # Now filter against database
    unique_jobs = []
    for key, job in seen.items():
        company_name = job.get("client_name", "")

        # Check for existing by job_link - only for specific job posting URLs
        # Skip generic company URLs (linkedin.com/company/, website homepages)
        # which would incorrectly dedup different job postings at same company
        job_link = job.get("job_link", "")
        if job_link and "/company/" not in job_link and "#job-" not in job_link:
            existing = db.query(LeadDetails).filter(
                LeadDetails.job_link == job_link
            ).first()
            if existing:
                continue

        # Check for existing by normalized company + title
        # Use LIKE for fuzzy matching on company name
        company_normalized = normalize_company_name(company_name)
        existing_leads = db.query(LeadDetails).filter(
            LeadDetails.job_title == job.get("job_title"),
            LeadDetails.state == job.get("state")
        ).all()

        found_match = False
        for existing_lead in existing_leads:
            existing_normalized = normalize_company_name(existing_lead.client_name or "")
            if existing_normalized == company_normalized:
                found_match = True
                break

        if not found_match:
            unique_jobs.append(job)

    return unique_jobs


def _job_quality_score(job: Dict[str, Any]) -> int:
    """Score a job based on data quality for deduplication priority."""
    score = 0

    # Has contact info
    if job.get("contact_email"):
        score += 10
    if job.get("contact_first_name") and job.get("contact_last_name"):
        score += 5

    # Has salary data
    if job.get("salary_min") or job.get("salary_max"):
        score += 3

    # Has job link
    if job.get("job_link"):
        score += 2

    # Has state
    if job.get("state"):
        score += 1

    return score


def _auto_enrich_new_leads(db, leads) -> int:
    """Auto-enrich newly sourced leads if their company already has contacts cached.

    For each new lead that has no contact info (first_name is None), check if the
    company already has contacts in the DB. If so, link them via the junction table
    and update the lead's denormalized contact fields. Zero API calls.

    Returns count of leads auto-enriched.
    """
    from app.db.models.contact import ContactDetails
    from app.db.models.lead_contact import LeadContactAssociation
    from app.services.pipelines.contact_enrichment import _reuse_existing_contacts, _update_lead_from_contacts

    max_contacts = settings.MAX_CONTACTS_PER_COMPANY_PER_JOB
    auto_enriched = 0
    checked_companies = {}  # company_name -> has_contacts (bool)

    for lead in leads:
        # Skip leads that already have contact info (e.g. from Apollo job source)
        if lead.first_name or not lead.client_name:
            continue

        # Check company contact cache (only query DB once per company)
        if lead.client_name not in checked_companies:
            has_contacts = db.query(ContactDetails).filter(
                ContactDetails.client_name == lead.client_name
            ).first() is not None
            checked_companies[lead.client_name] = has_contacts

        if not checked_companies[lead.client_name]:
            continue

        reused = _reuse_existing_contacts(db, lead, max_contacts)
        if reused > 0:
            _update_lead_from_contacts(db, lead)
            auto_enriched += 1

    return auto_enriched


def run_lead_sourcing_pipeline(
    sources: List[str],
    triggered_by: str = "system",
) -> Dict[str, Any]:
    """
    Run the lead sourcing pipeline with multi-source support.

    Steps:
    1. Fetch jobs from all enabled sources in parallel
    2. Normalize company names and deduplicate
    3. Store unique leads in lead_details
    4. Update client_info
    5. Export to XLSX

    Args:
        sources: List of sources (used for logging, actual sources from settings)
        triggered_by: User who triggered the pipeline

    Returns:
        Counter dict with inserted, updated, skipped, errors counts
    """
    db = SessionLocal()
    counters = {
        "inserted": 0,
        "updated": 0,
        "skipped": 0,
        "errors": 0,
        "sources_used": [],
        "jobs_per_source": {}
    }

    # Create job run record
    job_run = JobRun(
        pipeline_name="lead_sourcing",
        status=JobStatus.RUNNING,
        triggered_by=triggered_by,
    )
    db.add(job_run)
    db.commit()

    try:
        logger.info("Starting multi-source lead sourcing pipeline", requested_sources=sources)

        # Load settings from database or fall back to config
        target_industries = get_db_setting(db, "target_industries", settings.TARGET_INDUSTRIES)
        exclude_it_keywords = get_db_setting(db, "exclude_it_keywords", settings.EXCLUDE_IT_KEYWORDS)
        exclude_staffing_keywords = get_db_setting(db, "exclude_staffing_keywords", settings.EXCLUDE_STAFFING_KEYWORDS)
        target_job_titles = get_db_setting(db, "target_job_titles", settings.TARGET_JOB_TITLES)
        exclude_keywords = exclude_it_keywords + exclude_staffing_keywords

        logger.info(f"Pipeline config: {len(target_industries)} industries, {len(exclude_keywords)} exclusions, {len(target_job_titles)} job titles")

        # Get all configured adapters
        adapters = get_all_job_source_adapters(db)
        logger.info(f"Using {len(adapters)} job source adapters")

        all_jobs = []

        # Fetch from all sources in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = []
            for source_name, adapter in adapters:
                future = executor.submit(
                    fetch_from_source,
                    source_name,
                    adapter,
                    target_industries,
                    exclude_keywords,
                    target_job_titles
                )
                futures.append(future)

            # Collect results
            for future in concurrent.futures.as_completed(futures):
                source_name, jobs, error = future.result()
                counters["sources_used"].append(source_name)
                counters["jobs_per_source"][source_name] = len(jobs)

                if error:
                    counters["errors"] += 1
                    logger.error(f"Source {source_name} failed", error=error)
                else:
                    logger.info(f"Fetched {len(jobs)} jobs from {source_name}")
                    all_jobs.extend(jobs)

        logger.info(f"Total jobs fetched from all sources: {len(all_jobs)}")

        # Deduplicate jobs (both within batch and against DB)
        unique_jobs = deduplicate_jobs(all_jobs, db)
        counters["skipped"] = len(all_jobs) - len(unique_jobs)

        logger.info(f"After deduplication: {len(unique_jobs)} unique jobs (skipped {counters['skipped']} duplicates)")

        # Process unique jobs
        newly_inserted_leads = []
        total_unique = len(unique_jobs)
        for idx, job_data in enumerate(unique_jobs):
            # Cancel check
            if check_cancel(job_run.run_id, db):
                logger.info("Lead sourcing cancelled by user", processed=idx)
                break

            # Update progress every 10 items
            if total_unique > 0 and idx % 10 == 0:
                job_run.progress_pct = int((idx / total_unique) * 100)
                db.commit()

            try:
                # Create new lead
                lead = LeadDetails(
                    client_name=job_data["client_name"],
                    job_title=job_data["job_title"],
                    state=job_data.get("state"),
                    posting_date=job_data.get("posting_date"),
                    job_link=job_data.get("job_link"),
                    salary_min=job_data.get("salary_min"),
                    salary_max=job_data.get("salary_max"),
                    source=", ".join(job_data.get("all_sources", [job_data.get("source", "unknown")])),
                    lead_status=LeadStatus.NEW,  # NEW status allows contact enrichment to pick it up
                    # Pre-populate contact info if available from Apollo
                    first_name=job_data.get("contact_first_name"),
                    last_name=job_data.get("contact_last_name"),
                    contact_email=job_data.get("contact_email"),
                    contact_title=job_data.get("contact_title"),
                )
                db.add(lead)
                counters["inserted"] += 1
                newly_inserted_leads.append(lead)

                # Upsert client_info with normalized name
                upsert_client(db, job_data["client_name"])

            except Exception as e:
                logger.error("Error processing job", error=str(e), job=job_data.get("client_name"))
                counters["errors"] += 1

        db.commit()

        # Auto-enrich newly inserted leads from existing company contacts
        auto_enriched = _auto_enrich_new_leads(db, newly_inserted_leads)
        counters["auto_enriched"] = auto_enriched
        if auto_enriched > 0:
            db.commit()
            logger.info(f"Auto-enriched {auto_enriched} new lead(s) from existing company contacts")

        # Export to XLSX
        export_leads_to_xlsx(db)

        # Update job run with detailed counters
        db.refresh(job_run)
        if job_run.is_cancel_requested == 1:
            job_run.status = JobStatus.CANCELLED
        else:
            job_run.status = JobStatus.COMPLETED
        job_run.progress_pct = 100
        job_run.ended_at = datetime.utcnow()
        job_run.counters_json = json.dumps({
            "inserted": counters["inserted"],
            "updated": counters["updated"],
            "skipped": counters["skipped"],
            "errors": counters["errors"],
            "auto_enriched": counters.get("auto_enriched", 0),
            "sources": counters["sources_used"],
            "per_source": counters["jobs_per_source"]
        })
        db.commit()

        logger.info("Lead sourcing completed",
                   inserted=counters["inserted"],
                   skipped=counters["skipped"],
                   sources=counters["sources_used"])

        return counters

    except Exception as e:
        logger.error("Lead sourcing pipeline failed", error=str(e))
        job_run.status = JobStatus.FAILED
        job_run.error_message = str(e)
        job_run.ended_at = datetime.utcnow()
        db.commit()
        raise
    finally:
        db.close()


def upsert_client(db, client_name: str):
    """Create or update client_info record with normalized matching."""
    try:
        # Try exact match first
        client = db.query(ClientInfo).filter(ClientInfo.client_name == client_name).first()

        # If not found, try normalized match
        if not client:
            normalized = normalize_company_name(client_name)
            all_clients = db.query(ClientInfo).all()
            for c in all_clients:
                if normalize_company_name(c.client_name) == normalized:
                    client = c
                    break

        if not client:
            client = ClientInfo(
                client_name=client_name,
                status=ClientStatus.ACTIVE,
                start_date=date.today(),
                service_count=1,
                client_category=ClientCategory.PROSPECT,
            )
            db.add(client)
            db.flush()
        else:
            client.service_count = (client.service_count or 0) + 1

            # Compute client category based on posting frequency
            # Read thresholds from settings DB (same keys as clients endpoint)
            window_days = 90
            regular_threshold = 3
            occasional_threshold = 0
            for row in db.query(Settings).filter(Settings.key.in_([
                "category_window_days", "category_regular_threshold", "category_occasional_threshold"
            ])).all():
                try:
                    val = json.loads(row.value_json)
                except Exception:
                    val = row.value_json
                if row.key == "category_window_days":
                    window_days = int(val)
                elif row.key == "category_regular_threshold":
                    regular_threshold = int(val)
                elif row.key == "category_occasional_threshold":
                    occasional_threshold = int(val)

            cutoff = date.today() - timedelta(days=window_days)

            # Count unique dates using normalized company name matching
            normalized = normalize_company_name(client_name)
            all_leads = db.query(LeadDetails).filter(
                LeadDetails.posting_date >= cutoff
            ).all()

            unique_dates = set()
            for lead in all_leads:
                if normalize_company_name(lead.client_name or "") == normalized:
                    if lead.posting_date:
                        unique_dates.add(lead.posting_date)

            if len(unique_dates) > regular_threshold:
                client.client_category = ClientCategory.REGULAR
            elif len(unique_dates) > occasional_threshold:
                client.client_category = ClientCategory.OCCASIONAL
            else:
                client.client_category = ClientCategory.PROSPECT

    except Exception as e:
        db.rollback()
        logger.warning(f"Error upserting client {client_name}: {e}")
        # Try to just find existing
        client = db.query(ClientInfo).filter(ClientInfo.client_name == client_name).first()
        if client:
            client.service_count = (client.service_count or 0) + 1


def export_leads_to_xlsx(db, filepath: Optional[str] = None):
    """Export leads to XLSX file."""
    if not filepath:
        os.makedirs(settings.EXPORT_PATH, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join(settings.EXPORT_PATH, f"Job_requirements_{timestamp}.xlsx")

    leads = db.query(LeadDetails).order_by(LeadDetails.created_at.desc()).limit(5000).all()  # IMPACT: Increased from 1000

    data = []
    for lead in leads:
        data.append({
            "Lead ID": lead.lead_id,
            "Company": lead.client_name,
            "Job Title": lead.job_title,
            "State": lead.state,
            "Posting Date": lead.posting_date.isoformat() if lead.posting_date else None,
            "Job Link": lead.job_link,
            "Salary Min": float(lead.salary_min) if lead.salary_min else None,
            "Salary Max": float(lead.salary_max) if lead.salary_max else None,
            "Source": lead.source,
            "First Name": lead.first_name,
            "Last Name": lead.last_name,
            "Contact Title": lead.contact_title,
            "Contact Email": lead.contact_email,
            "Contact Phone": lead.contact_phone,
            "Status": lead.lead_status.value if lead.lead_status else None
        })

    df = pd.DataFrame(data)
    df.to_excel(filepath, index=False)
    logger.info(f"Exported {len(data)} leads to {filepath}")

    return filepath


def import_leads_from_file(
    filepath: str,
    triggered_by: str = "system",
) -> Dict[str, Any]:
    """Import leads from XLSX file."""
    db = SessionLocal()
    counters = {"inserted": 0, "updated": 0, "skipped": 0, "errors": 0}

    try:
        df = pd.read_excel(filepath)
        logger.info(f"Reading {len(df)} rows from {filepath}")

        for _, row in df.iterrows():
            try:
                client_name = str(row.get("Company", row.get("client_name", "")))
                job_title = str(row.get("Job Title", row.get("job_title", "")))

                if not client_name or not job_title:
                    counters["skipped"] += 1
                    continue

                # Check for existing using normalized name
                normalized = normalize_company_name(client_name)
                existing_leads = db.query(LeadDetails).filter(
                    LeadDetails.job_title == job_title
                ).all()

                found_match = False
                for existing in existing_leads:
                    if normalize_company_name(existing.client_name or "") == normalized:
                        found_match = True
                        break

                if found_match:
                    counters["skipped"] += 1
                    continue

                lead = LeadDetails(
                    client_name=client_name,
                    job_title=job_title,
                    state=str(row.get("State", row.get("state", ""))) if pd.notna(row.get("State", row.get("state"))) else None,
                    source="file_import",
                    lead_status=LeadStatus.OPEN,
                )
                db.add(lead)
                counters["inserted"] += 1

                upsert_client(db, client_name)

            except Exception as e:
                logger.error("Error importing row", error=str(e))
                counters["errors"] += 1

        db.commit()
        return counters

    except Exception as e:
        logger.error("Import failed", error=str(e))
        raise
    finally:
        db.close()
