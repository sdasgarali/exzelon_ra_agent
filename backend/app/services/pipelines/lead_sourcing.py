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
from app.core.settings_resolver import get_tenant_setting
from app.services.adapters.base import RateLimitError
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


# Job title abbreviation map for normalization
# Only includes common business/staffing titles to reduce false negatives
TITLE_ABBREVIATIONS = {
    r'\bhr\b': 'human resources',
    r'\bmgr\b': 'manager',
    r'\bsr\b': 'senior',
    r'\bjr\b': 'junior',
    r'\bvp\b': 'vice president',
    r'\bsvp\b': 'senior vice president',
    r'\bevp\b': 'executive vice president',
    r'\bdir\b': 'director',
    r'\basst\b': 'assistant',
    r'\badmin\b': 'administrator',
    r'\bcoord\b': 'coordinator',
    r'\bsupr\b': 'supervisor',
    r'\bsupv\b': 'supervisor',
    r'\bmfg\b': 'manufacturing',
    r'\beng\b': 'engineering',
    r'\bops\b': 'operations',
    r'\bmaint\b': 'maintenance',
    r'\bqa\b': 'quality assurance',
    r'\bqc\b': 'quality control',
}


def normalize_job_title(title: str) -> str:
    """Normalize job title for deduplication: expand abbreviations, lowercase, strip punctuation.

    Examples:
        "HR Manager" -> "human resources manager"
        "Sr. VP of Ops" -> "senior vice president of operations"
        "QA Mgr" -> "quality assurance manager"
    """
    if not title:
        return ""
    normalized = title.lower().strip()
    # Remove common punctuation but keep spaces
    normalized = re.sub(r'[,\.\-/\\()&]', ' ', normalized)
    # Expand abbreviations (word-boundary aware)
    for abbrev, full in TITLE_ABBREVIATIONS.items():
        normalized = re.sub(abbrev, full, normalized)
    # Collapse spaces
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    return normalized


# =============================================================================
# Source optimization — overlap groups + coverage tiers
#
# Goal: stop paying multiple providers for the SAME job posting. Several APIs
# share an underlying index (SerpAPI and SearchAPI are both Google Jobs; Google
# Jobs + JSearch both surface LinkedIn/Indeed). Running them all in parallel
# means duplicate postings = duplicate API spend. These structures drive a
# tiered waterfall that runs cheap/unique sources first and only calls the
# expensive/overlapping ones to fill a gap toward a per-run target.
# =============================================================================

# Providers that share the same underlying index. Only the highest-priority
# enabled member of each group is run. Order = priority (first wins).
SOURCE_OVERLAP_GROUPS: Dict[str, List[str]] = {
    # SerpAPI and SearchAPI both call engine=google_jobs — identical results.
    # SearchAPI preferred (cheaper $40/mo flat); SerpAPI is the disabled fallback.
    "google_jobs": ["searchapi", "serpapi"],
}

# Coverage tier per source. Tier 1 = free / cheap / unique broad coverage
# (always run). Tier 2 = expensive or heavily-overlapping fill-ins (run only to
# fill a gap toward the per-run target). Unlisted sources default to tier 1.
SOURCE_TIERS: Dict[str, int] = {
    "usajobs": 1, "jooble": 1, "jsearch": 1, "adzuna": 1, "theirstack": 1, "mock": 1,
    "searchapi": 2, "serpapi": 2, "jobdatafeeds": 2, "coresignal": 2,
}

# Run order (lower = cheaper, runs first). Spends the cheapest fill-in API first
# and stops as soon as the per-run target is met.
SOURCE_COST_RANK: Dict[str, int] = {
    "usajobs": 0, "jooble": 0, "mock": 0,
    "adzuna": 1, "jsearch": 2, "theirstack": 3,
    "searchapi": 5, "serpapi": 6, "jobdatafeeds": 8, "coresignal": 9,
}


def _filter_overlap_groups(
    adapters: List[Tuple[str, Any]],
    groups: Dict[str, List[str]],
) -> Tuple[List[Tuple[str, Any]], List[str]]:
    """Keep only the highest-priority enabled adapter in each overlap group.

    Returns (kept_adapters, skipped_source_names). A group with 0 or 1 enabled
    member is left untouched (the single fallback still runs).
    """
    present = {name for name, _ in adapters}
    drop: set = set()
    for _group, priority in (groups or {}).items():
        members = [p for p in priority if p in present]
        for loser in members[1:]:  # keep members[0], drop the rest
            drop.add(loser)
    kept = [(n, a) for n, a in adapters if n not in drop]
    return kept, sorted(drop)


def _partition_tiers(
    adapters: List[Tuple[str, Any]],
    tier_map: Dict[str, int],
) -> Tuple[List[Tuple[str, Any]], List[Tuple[str, Any]]]:
    """Split adapters into (tier1, tier2). Tier 2 is sorted cheapest-first."""
    tier1 = [(n, a) for n, a in adapters if int(tier_map.get(n, 1)) <= 1]
    tier2 = sorted(
        [(n, a) for n, a in adapters if int(tier_map.get(n, 1)) >= 2],
        key=lambda x: int(SOURCE_COST_RANK.get(x[0], 5)),
    )
    return tier1, tier2


def get_all_job_source_adapters(db, tenant_id: Optional[int] = None) -> List[Tuple[str, Any]]:
    """Get all configured job source adapters.

    Returns list of (source_name, adapter) tuples.
    """
    from app.services.adapters.job_sources.jsearch import JSearchAdapter
    from app.services.adapters.job_sources.theirstack import TheirStackAdapter
    from app.services.adapters.job_sources.serpapi import SerpAPIAdapter
    from app.services.adapters.job_sources.adzuna import AdzunaAdapter

    adapters = []

    # Get enabled sources from settings
    enabled_sources = get_tenant_setting(db, "lead_sources", tenant_id=tenant_id, default=["jsearch"])
    logger.info(f"Enabled lead sources: {enabled_sources}")

    # JSearch adapter
    if "jsearch" in enabled_sources:
        jsearch_api_key = get_tenant_setting(db, "jsearch_api_key", tenant_id=tenant_id) or settings.JSEARCH_API_KEY
        if jsearch_api_key:
            adapters.append(("jsearch", JSearchAdapter(api_key=jsearch_api_key)))
            logger.info("JSearch adapter configured")

    # Apollo is NOT a job source (it's a contact enrichment platform).
    # It was removed from job sourcing because it generates synthetic leads
    # with fake LinkedIn search URLs, not real job postings.
    # Apollo remains available for Contact Enrichment (Pipeline Stage 2).

    # TheirStack adapter
    if "theirstack" in enabled_sources:
        theirstack_key = get_tenant_setting(db, "theirstack_api_key", tenant_id=tenant_id)
        if theirstack_key:
            adapters.append(("theirstack", TheirStackAdapter(api_key=theirstack_key)))
            logger.info("TheirStack adapter configured")

    # SerpAPI adapter
    if "serpapi" in enabled_sources:
        serpapi_key = get_tenant_setting(db, "serpapi_api_key", tenant_id=tenant_id)
        if serpapi_key:
            adapters.append(("serpapi", SerpAPIAdapter(api_key=serpapi_key)))
            logger.info("SerpAPI adapter configured")

    # Adzuna adapter
    if "adzuna" in enabled_sources:
        adzuna_app_id = get_tenant_setting(db, "adzuna_app_id", tenant_id=tenant_id)
        adzuna_api_key = get_tenant_setting(db, "adzuna_api_key", tenant_id=tenant_id)
        if adzuna_app_id and adzuna_api_key:
            adapters.append(("adzuna", AdzunaAdapter(app_id=adzuna_app_id, api_key=adzuna_api_key)))
            logger.info("Adzuna adapter configured")

    # SearchAPI adapter
    if "searchapi" in enabled_sources:
        from app.services.adapters.job_sources.searchapi import SearchAPIAdapter
        searchapi_key = get_tenant_setting(db, "searchapi_api_key", tenant_id=tenant_id)
        if searchapi_key:
            adapters.append(("searchapi", SearchAPIAdapter(api_key=searchapi_key)))
            logger.info("SearchAPI adapter configured")

    # USAJOBS adapter
    if "usajobs" in enabled_sources:
        from app.services.adapters.job_sources.usajobs import USAJobsAdapter
        usajobs_key = get_tenant_setting(db, "usajobs_api_key", tenant_id=tenant_id)
        usajobs_email = get_tenant_setting(db, "usajobs_email", tenant_id=tenant_id)
        if usajobs_key:
            adapters.append(("usajobs", USAJobsAdapter(api_key=usajobs_key, email=usajobs_email)))
            logger.info("USAJOBS adapter configured")

    # Jooble adapter
    if "jooble" in enabled_sources:
        from app.services.adapters.job_sources.jooble import JoobleAdapter
        jooble_key = get_tenant_setting(db, "jooble_api_key", tenant_id=tenant_id)
        if jooble_key:
            adapters.append(("jooble", JoobleAdapter(api_key=jooble_key)))
            logger.info("Jooble adapter configured")

    # JobDataFeeds adapter
    if "jobdatafeeds" in enabled_sources:
        from app.services.adapters.job_sources.jobdatafeeds import JobDataFeedsAdapter
        jdf_key = get_tenant_setting(db, "jobdatafeeds_api_key", tenant_id=tenant_id)
        if jdf_key:
            adapters.append(("jobdatafeeds", JobDataFeedsAdapter(api_key=jdf_key)))
            logger.info("JobDataFeeds adapter configured")

    # Coresignal adapter (jobs + recruiter contacts)
    if "coresignal" in enabled_sources:
        from app.services.adapters.job_sources.coresignal import CoresignalAdapter
        cs_key = get_tenant_setting(db, "coresignal_api_key", tenant_id=tenant_id)
        if cs_key:
            adapters.append(("coresignal", CoresignalAdapter(api_key=cs_key)))
            logger.info("Coresignal adapter configured")

    # Mock adapter (for development/testing)
    if "mock" in enabled_sources:
        adapters.append(("mock", MockJobSourceAdapter()))
        logger.info("Mock adapter configured (test data)")

    # Fallback to mock if no adapters configured
    if not adapters:
        logger.warning("No job source adapters configured, using mock adapter")
        adapters.append(("mock", MockJobSourceAdapter()))

    return adapters


def get_lob_lead_source_adapters(
    db, tenant_id: Optional[int] = None, lob_id: Optional[int] = None
) -> List[Tuple[str, Any]]:
    """Get LOB-specific lead source adapters based on LOB configuration.

    Reads the LOB's lead_source_config JSON to determine which non-job-board
    adapters to use (NPI, Google Business, Crunchbase, BuiltWith, PageSpeed, GitHub).

    Returns list of (source_name, adapter) tuples.
    """
    from app.services.adapters.lead_sources.npi_registry import NPIRegistryAdapter
    from app.services.adapters.lead_sources.google_business import GoogleBusinessAdapter
    from app.services.adapters.lead_sources.crunchbase import CrunchbaseAdapter
    from app.services.adapters.lead_sources.builtwith import BuiltWithAdapter
    from app.services.adapters.lead_sources.pagespeed import PageSpeedAdapter
    from app.services.adapters.lead_sources.github_org import GitHubOrgAdapter
    from app.services.adapters.lead_sources.hiring_signal import HiringSignalAdapter
    from app.services.adapters.lead_sources.news_signal import NewsSignalAdapter
    from app.core.settings_resolver import get_lob_config

    adapters = []

    if lob_id is None:
        return adapters

    # Get LOB lead source config
    lob_sources_config = get_lob_config(db, lob_id, "lead_source_config") or {}
    enabled_sources = lob_sources_config.get("enabled_sources", [])

    if not enabled_sources:
        # Infer default sources from LOB type
        from app.db.models.line_of_business import LineOfBusiness
        lob = db.query(LineOfBusiness).filter(LineOfBusiness.lob_id == lob_id).first()
        if lob:
            enabled_sources = _default_sources_for_lob_type(lob.lob_type)

    logger.info(f"LOB lead sources enabled: {enabled_sources}", lob_id=lob_id)

    # NPI Registry (free, no key)
    if "npi_registry" in enabled_sources:
        adapters.append(("npi_registry", NPIRegistryAdapter()))
        logger.info("NPI Registry adapter configured for LOB", lob_id=lob_id)

    # Google Business (needs API key)
    if "google_business" in enabled_sources:
        api_key = get_tenant_setting(db, "google_places_api_key", tenant_id=tenant_id) or settings.GOOGLE_PLACES_API_KEY
        if api_key:
            adapters.append(("google_business", GoogleBusinessAdapter(api_key=api_key)))
            logger.info("Google Business adapter configured for LOB", lob_id=lob_id)

    # Crunchbase (needs API key)
    if "crunchbase" in enabled_sources:
        api_key = get_tenant_setting(db, "crunchbase_api_key", tenant_id=tenant_id) or settings.CRUNCHBASE_API_KEY
        if api_key:
            adapters.append(("crunchbase", CrunchbaseAdapter(api_key=api_key)))
            logger.info("Crunchbase adapter configured for LOB", lob_id=lob_id)

    # BuiltWith (needs API key)
    if "builtwith" in enabled_sources:
        api_key = get_tenant_setting(db, "builtwith_api_key", tenant_id=tenant_id) or settings.BUILTWITH_API_KEY
        if api_key:
            adapters.append(("builtwith", BuiltWithAdapter(api_key=api_key)))
            logger.info("BuiltWith adapter configured for LOB", lob_id=lob_id)

    # PageSpeed (free, key optional)
    if "pagespeed" in enabled_sources:
        api_key = get_tenant_setting(db, "google_places_api_key", tenant_id=tenant_id) or settings.GOOGLE_PLACES_API_KEY
        adapters.append(("pagespeed", PageSpeedAdapter(api_key=api_key)))
        logger.info("PageSpeed adapter configured for LOB", lob_id=lob_id)

    # GitHub Org (free, token optional)
    if "github_org" in enabled_sources:
        token = get_tenant_setting(db, "github_token", tenant_id=tenant_id) or settings.GITHUB_TOKEN
        adapters.append(("github_org", GitHubOrgAdapter(token=token)))
        logger.info("GitHub Org adapter configured for LOB", lob_id=lob_id)

    # Hiring Signal (internal, zero API calls)
    if "hiring_signal" in enabled_sources:
        adapters.append(("hiring_signal", HiringSignalAdapter(db=db, tenant_id=tenant_id)))
        logger.info("Hiring Signal adapter configured for LOB", lob_id=lob_id)

    # News Signal (Google News RSS, free)
    if "news_signal" in enabled_sources:
        adapters.append(("news_signal", NewsSignalAdapter()))
        logger.info("News Signal adapter configured for LOB", lob_id=lob_id)

    return adapters


def _default_sources_for_lob_type(lob_type: str) -> List[str]:
    """Return default lead source adapters for a LOB type."""
    defaults = {
        "staffing": [],  # Uses job board adapters, not LOB lead sources
        "rcm": ["npi_registry", "google_business", "hiring_signal", "news_signal"],
        "software_dev": ["crunchbase", "builtwith", "github_org", "hiring_signal", "news_signal"],
        "ai_services": ["crunchbase", "github_org", "hiring_signal", "news_signal"],
        "digital_marketing": ["google_business", "pagespeed", "builtwith", "hiring_signal", "news_signal"],
        "custom": [],
    }
    return defaults.get(lob_type, [])


def fetch_from_lob_source(
    source_name: str,
    adapter: Any,
    query: str = "",
    location: str = "United States",
    limit: int = 100,
    extra_params: Optional[Dict[str, Any]] = None,
) -> Tuple[str, List[Dict[str, Any]], Optional[str], Dict[str, Any]]:
    """Fetch leads from a LOB-specific source (for parallel execution).

    Similar to fetch_from_source() but uses LeadSourceAdapter.fetch_leads().
    Returns: (source_name, leads_list, error_message, diagnostics)
    """
    diagnostics: Dict[str, Any] = {
        "status": "success",
        "jobs_returned": 0,
        "error_type": None,
        "error_message": None,
    }
    try:
        kwargs = extra_params or {}
        leads = adapter.fetch_leads(
            query=query,
            location=location,
            limit=limit,
            **kwargs,
        )
        diagnostics["jobs_returned"] = len(leads)
        if len(leads) == 0:
            diagnostics["status"] = "warning"
            diagnostics["error_type"] = "no_match"
        logger.info(f"LOB source {source_name} returned {len(leads)} leads")
        return (source_name, leads, None, diagnostics)
    except RateLimitError as e:
        partial = e.partial_results or []
        diagnostics["status"] = "error"
        diagnostics["error_type"] = "rate_limited"
        diagnostics["error_message"] = str(e)[:300]
        diagnostics["jobs_returned"] = len(partial)
        return (source_name, partial, str(e), diagnostics)
    except Exception as e:
        diagnostics["status"] = "error"
        diagnostics["error_type"] = "unknown"
        diagnostics["error_message"] = str(e)[:300]
        logger.error(f"Error fetching from LOB source {source_name}", error=str(e))
        return (source_name, [], str(e), diagnostics)


def fetch_from_source(
    source_name: str,
    adapter: Any,
    target_industries: List[str],
    exclude_keywords: List[str],
    target_job_titles: List[str],
    exclude_company_keywords: Optional[List[str]] = None,
    exclude_title_keywords: Optional[List[str]] = None,
    match_mode: str = "word_boundary",
    location: str = "United States",
    location_diversification: bool = False,
    target_states: Optional[List[str]] = None,
    tuning: Optional[Dict[str, Any]] = None,
    adapter_limit: int = 1000,
    posted_within_days: int = 7,
    push_negatives: bool = True,
) -> Tuple[str, List[Dict[str, Any]], Optional[str], Dict[str, Any]]:
    """Fetch jobs from a single source (for parallel execution).

    IMPACT ON LEAD COUNT: Exclude keywords are passed to adapters which filter
    internally. No secondary filtering is done here to avoid double-filtering
    which previously dropped ~20% extra leads redundantly.

    IMPACT ON API COST: When ``push_negatives`` is True, exclusion keywords are
    also pushed into the upstream query (where the source supports it: JSearch,
    SerpAPI, Adzuna), so excluded postings are filtered server-side rather than
    fetched-then-discarded. The local filter still runs as a backstop.

    Returns: (source_name, jobs_list, error_message, diagnostics)
    """
    # Set split exclusion attributes on the adapter instance
    adapter._exclude_company = exclude_company_keywords
    adapter._exclude_title = exclude_title_keywords
    adapter._match_mode = match_mode
    adapter._push_negatives = push_negatives

    diagnostics: Dict[str, Any] = {
        "status": "success",
        "jobs_returned": 0,
        "error_type": None,
        "error_message": None,
    }
    try:
        # Location diversification: search per-state instead of nationwide
        if location_diversification and target_states:
            jobs = []
            for state in target_states:
                state_jobs = adapter.fetch_jobs(
                    location=state,
                    posted_within_days=posted_within_days,
                    industries=target_industries,
                    exclude_keywords=exclude_keywords,
                    job_titles=target_job_titles,
                    limit=adapter_limit,
                    tuning=tuning,
                )
                jobs.extend(state_jobs)
        else:
            jobs = adapter.fetch_jobs(
                location=location,
                posted_within_days=posted_within_days,
                industries=target_industries,
                exclude_keywords=exclude_keywords,
                job_titles=target_job_titles,
                limit=adapter_limit,
                tuning=tuning,
            )
        diagnostics["jobs_returned"] = len(jobs)
        if len(jobs) == 0:
            diagnostics["status"] = "warning"
            diagnostics["error_type"] = "no_match"
        logger.info(f"Source {source_name} returned {len(jobs)} jobs after adapter-level filtering")
        return (source_name, jobs, None, diagnostics)
    except RateLimitError as e:
        partial = e.partial_results or []
        diagnostics["status"] = "error"
        diagnostics["error_type"] = "rate_limited"
        diagnostics["error_message"] = str(e)[:300]
        diagnostics["jobs_returned"] = len(partial)
        logger.warning(
            f"Source {source_name} hit rate limit",
            partial_results=len(partial),
            error=str(e),
        )
        return (source_name, partial, str(e), diagnostics)
    except Exception as e:
        error_msg = str(e)
        error_lower = error_msg.lower()
        # Classify error type
        if "401" in error_msg or "unauthorized" in error_lower or "invalid" in error_lower and "key" in error_lower:
            diagnostics["error_type"] = "api_key_invalid"
        elif "credit" in error_lower or "quota" in error_lower or "exhausted" in error_lower \
                or "402" in error_msg or "payment required" in error_lower:
            diagnostics["error_type"] = "credits_exhausted"
        elif "403" in error_msg or "premium functionality" in error_lower or "plan allows" in error_lower or "forbidden" in error_lower:
            diagnostics["error_type"] = "plan_limit"
        elif "429" in error_msg or "rate" in error_lower and "limit" in error_lower:
            diagnostics["error_type"] = "rate_limited"
        elif "timeout" in error_lower or "connection" in error_lower:
            diagnostics["error_type"] = "connection_error"
        else:
            diagnostics["error_type"] = "unknown"
        diagnostics["status"] = "error"
        diagnostics["error_message"] = error_msg[:300]
        logger.error(f"Error fetching from {source_name}", error=error_msg)
        return (source_name, [], error_msg, diagnostics)


def deduplicate_jobs(jobs: List[Dict[str, Any]], db, tenant_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Deduplicate jobs using a 3-layer strategy for maximum accuracy.

    Layer 1: external_job_id (JSearch job_id) — 100% accurate for same posting
    Layer 2: employer_linkedin_url + normalized title — near-100% company identity
    Layer 3: normalized company + normalized title + state + city — enhanced rule-based

    IMPACT ON LEAD COUNT: Deduplication uses company name + job title + state + city as key.
    Company names are normalized (legal suffixes stripped). Job titles are normalized
    (abbreviations expanded: HR→Human Resources, Mgr→Manager, etc.).
    Previously used state-only granularity; now includes city to avoid merging
    different locations (e.g., Walmart Houston vs Walmart Dallas).

    Priority for keeping duplicates:
    1. Has more contact info
    2. Has salary data
    3. Has job link
    4. Most recent
    """
    # First, dedupe within the incoming batch using 3-layer keys
    seen_by_ext_id = {}  # external_job_id -> job
    seen_by_linkedin = {}  # employer_linkedin + normalized_title -> job
    seen = {}  # normalized company|title|state|city -> job

    def _merge_sources(winner, loser):
        """Merge source lists from two duplicate jobs."""
        winner["all_sources"] = list(set(
            winner.get("all_sources", [winner.get("source", "unknown")]) +
            loser.get("all_sources", [loser.get("source", "unknown")])
        ))

    def _try_merge(existing, job):
        """Keep the higher quality job, merge sources."""
        new_score = _job_quality_score(job)
        existing_score = _job_quality_score(existing)
        if new_score > existing_score:
            _merge_sources(job, existing)
            return job  # new wins
        else:
            _merge_sources(existing, job)
            return existing  # existing wins

    for job in jobs:
        ext_id = job.get("external_job_id") or ""
        emp_linkedin = job.get("employer_linkedin_url") or ""
        company_normalized = normalize_company_name(job.get("client_name") or "")
        title_normalized = normalize_job_title(job.get("job_title") or "")
        state = job.get("state") or ""
        city = (job.get("city") or "").lower().strip()

        matched = False

        # Layer 1: external_job_id (exact match, highest confidence)
        if ext_id:
            if ext_id in seen_by_ext_id:
                winner = _try_merge(seen_by_ext_id[ext_id], job)
                seen_by_ext_id[ext_id] = winner
                matched = True

        # Layer 2: employer_linkedin + normalized title (company identity match)
        if not matched and emp_linkedin and title_normalized:
            linkedin_key = f"{emp_linkedin}|{title_normalized}"
            if linkedin_key in seen_by_linkedin:
                winner = _try_merge(seen_by_linkedin[linkedin_key], job)
                seen_by_linkedin[linkedin_key] = winner
                matched = True

        # Layer 3: normalized company + title + state + city (rule-based)
        if not matched:
            key = f"{company_normalized}|{title_normalized}|{state}|{city}"
            if key in seen:
                winner = _try_merge(seen[key], job)
                seen[key] = winner
                matched = True

        if not matched:
            job["all_sources"] = [job.get("source", "unknown")]
            # Register in all applicable indexes
            if ext_id:
                seen_by_ext_id[ext_id] = job
            if emp_linkedin and title_normalized:
                seen_by_linkedin[f"{emp_linkedin}|{title_normalized}"] = job
            key = f"{company_normalized}|{title_normalized}|{state}|{city}"
            seen[key] = job

    # Collect all unique jobs (dedupe across the three maps)
    all_unique = {}  # id(job) -> job
    for job in seen_by_ext_id.values():
        all_unique[id(job)] = job
    for job in seen_by_linkedin.values():
        all_unique[id(job)] = job
    for job in seen.values():
        all_unique[id(job)] = job
    batch_unique = list(all_unique.values())

    # Now filter against database
    unique_jobs = []
    for job in batch_unique:
        company_name = job.get("client_name") or ""

        # DB Layer 1: Check external_job_id
        ext_id = job.get("external_job_id") or ""
        if ext_id:
            q = db.query(LeadDetails).filter(LeadDetails.external_job_id == ext_id)
            if tenant_id is not None:
                q = q.filter(LeadDetails.tenant_id == tenant_id)
            existing = q.first()
            if existing:
                continue

        # DB Layer 2: Check job_link (only for real posting URLs)
        job_link = job.get("job_link") or ""
        if job_link and "/company/" not in job_link and "#job-" not in job_link:
            q = db.query(LeadDetails).filter(LeadDetails.job_link == job_link)
            if tenant_id is not None:
                q = q.filter(LeadDetails.tenant_id == tenant_id)
            existing = q.first()
            if existing:
                continue

        # DB Layer 3: Check normalized company + normalized title + state
        # Only check leads from the last 30 days to allow re-discovery of refreshed postings
        company_normalized = normalize_company_name(company_name)
        title_normalized = normalize_job_title(job.get("job_title") or "")
        dedup_cutoff = datetime.utcnow() - timedelta(days=30)
        q = db.query(LeadDetails).filter(
            LeadDetails.state == (job.get("state") or ""),
            LeadDetails.created_at >= dedup_cutoff
        )
        if tenant_id is not None:
            q = q.filter(LeadDetails.tenant_id == tenant_id)
        existing_leads = q.all()

        found_match = False
        for existing_lead in existing_leads:
            existing_company = normalize_company_name(existing_lead.client_name or "")
            existing_title = normalize_job_title(existing_lead.job_title or "")
            if existing_company == company_normalized and existing_title == title_normalized:
                # Additional city check: if both have city, must match
                existing_city = (existing_lead.city or "").lower().strip()
                new_city = (job.get("city") or "").lower().strip()
                if existing_city and new_city and existing_city != new_city:
                    continue  # Different cities → not a duplicate
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


def _auto_enrich_new_leads(db, leads, tenant_id=None) -> int:
    """Auto-enrich newly sourced leads if their company already has contacts cached.

    For each new lead that has no contact info (first_name is None), check if the
    company already has contacts in the DB. If so, link them via the junction table
    and update the lead's denormalized contact fields. Zero API calls.

    Returns count of leads auto-enriched.
    """
    from app.db.models.contact import ContactDetails
    from app.services.pipelines.contact_enrichment import _reuse_existing_contacts, _update_lead_from_contacts
    from app.core.settings_resolver import get_tenant_setting

    _mc = get_tenant_setting(db, "max_contacts_per_company_job", tenant_id=tenant_id, default=None)
    max_contacts = int(_mc) if _mc is not None else settings.MAX_CONTACTS_PER_COMPANY_PER_JOB
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
    tenant_id: Optional[int] = None,
    lob_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Run the lead sourcing pipeline with multi-source support.

    Steps:
    1. Fetch jobs from all enabled sources in parallel
    1b. If lob_id is set, also fetch from LOB-specific lead sources
    2. Normalize company names and deduplicate
    3. Store unique leads in lead_details
    4. Update client_info
    5. Export to XLSX

    Args:
        sources: List of sources (used for logging, actual sources from settings)
        triggered_by: User who triggered the pipeline
        tenant_id: Tenant context
        lob_id: Optional LOB to scope lead sources

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
        "jobs_per_source": {},
    }
    per_source_detail: Dict[str, Dict[str, int]] = {}
    per_sub_source_detail: Dict[str, Dict[str, int]] = {}  # linkedin, indeed, glassdoor, etc.
    api_diagnostics_list: List[Dict[str, Any]] = []

    # Concurrency guard — prevent multiple simultaneous pipeline runs
    existing_run = db.query(JobRun).filter(
        JobRun.pipeline_name == "lead_sourcing",
        JobRun.status == JobStatus.RUNNING,
    ).first()
    if existing_run:
        logger.warning(
            "Lead sourcing skipped — another run is already in progress",
            existing_run_id=existing_run.run_id,
            existing_triggered_by=existing_run.triggered_by,
        )
        db.close()
        return {
            "skipped": True,
            "reason": f"Another lead sourcing run (#{existing_run.run_id}) is already in progress",
            "inserted": 0, "updated": 0, "errors": 0,
        }

    # Create job run record
    job_run = JobRun(
        tenant_id=tenant_id or 1,
        pipeline_name="lead_sourcing",
        status=JobStatus.RUNNING,
        triggered_by=triggered_by,
    )
    db.add(job_run)
    db.commit()

    try:
        logger.info("Starting multi-source lead sourcing pipeline", requested_sources=sources)

        # Load settings from database or fall back to config
        target_industries = get_tenant_setting(db, "target_industries", tenant_id=tenant_id, default=settings.TARGET_INDUSTRIES)
        exclude_it_keywords = get_tenant_setting(db, "exclude_it_keywords", tenant_id=tenant_id, default=settings.EXCLUDE_IT_KEYWORDS)
        exclude_staffing_keywords = get_tenant_setting(db, "exclude_staffing_keywords", tenant_id=tenant_id, default=settings.EXCLUDE_STAFFING_KEYWORDS)
        target_job_titles = get_tenant_setting(db, "target_job_titles", tenant_id=tenant_id, default=settings.TARGET_JOB_TITLES)
        exclude_keywords = exclude_it_keywords + exclude_staffing_keywords

        # Split exclusion lists (P1-C)
        exclude_company_keywords = get_tenant_setting(db, "exclude_company_keywords", tenant_id=tenant_id, default=settings.EXCLUDE_COMPANY_KEYWORDS)
        exclude_title_keywords = get_tenant_setting(db, "exclude_title_keywords", tenant_id=tenant_id, default=settings.EXCLUDE_TITLE_KEYWORDS)
        match_mode = get_tenant_setting(db, "exclude_match_mode", tenant_id=tenant_id, default="word_boundary")
        # When True, exclusion keywords are pushed into upstream queries to cut
        # wasted API result volume (sources that support it). Default on.
        push_exclusions_to_query = bool(get_tenant_setting(db, "push_exclusions_to_query", tenant_id=tenant_id, default=True))

        # Company size/industry gate (drops big / IT / staffing / government /
        # confidential companies that keyword filters can't catch by name alone).
        max_employee_count = int(get_tenant_setting(db, "lead_sourcing_max_employee_count", tenant_id=tenant_id, default=settings.LEAD_SOURCING_MAX_EMPLOYEE_COUNT))
        min_employee_count = int(get_tenant_setting(db, "lead_sourcing_min_employee_count", tenant_id=tenant_id, default=settings.LEAD_SOURCING_MIN_EMPLOYEE_COUNT))
        drop_confidential = bool(get_tenant_setting(db, "lead_sourcing_drop_confidential", tenant_id=tenant_id, default=settings.LEAD_SOURCING_DROP_CONFIDENTIAL))
        excluded_industries = get_tenant_setting(db, "lead_sourcing_excluded_industries", tenant_id=tenant_id, default=settings.EXCLUDED_INDUSTRY_KEYWORDS)
        if not isinstance(excluded_industries, list) or not excluded_industries:
            from app.services.company_filters import DEFAULT_EXCLUDED_INDUSTRY_KEYWORDS
            excluded_industries = DEFAULT_EXCLUDED_INDUSTRY_KEYWORDS
        enrich_company_at_source = bool(get_tenant_setting(db, "lead_sourcing_enrich_company_at_source", tenant_id=tenant_id, default=settings.LEAD_SOURCING_ENRICH_COMPANY_AT_SOURCE))
        enrich_max_companies = int(get_tenant_setting(db, "lead_sourcing_enrich_max_companies", tenant_id=tenant_id, default=settings.LEAD_SOURCING_ENRICH_MAX_COMPANIES))
        min_salary_threshold = int(get_tenant_setting(db, "min_salary_threshold", tenant_id=tenant_id, default=settings.MIN_SALARY_THRESHOLD))

        # Location diversification (P2-F)
        location_diversification = get_tenant_setting(db, "location_diversification", tenant_id=tenant_id, default=False)
        target_states = get_tenant_setting(db, "target_states", tenant_id=tenant_id, default=["CA", "TX", "FL", "NY", "IL", "PA", "OH", "GA", "NC", "MI"])

        # Source tuning — per-adapter performance parameters
        job_source_tuning = get_tenant_setting(db, "job_source_tuning", tenant_id=tenant_id, default={})
        if not isinstance(job_source_tuning, dict):
            job_source_tuning = {}
        pipeline_adapter_limit = int(get_tenant_setting(db, "pipeline_adapter_limit", tenant_id=tenant_id, default=1000))
        pipeline_max_workers = int(get_tenant_setting(db, "pipeline_max_workers", tenant_id=tenant_id, default=6))
        posted_within_days = int(get_tenant_setting(db, "posted_within_days", tenant_id=tenant_id, default=7))

        # "__ANY__" sentinel means skip filtering for that dimension
        if isinstance(target_job_titles, list) and target_job_titles == ["__ANY__"]:
            target_job_titles = settings.BROAD_SEARCH_QUERIES
            logger.info(f"Job titles set to 'Any' — using {len(settings.BROAD_SEARCH_QUERIES)} broad search terms")
        if isinstance(target_industries, list) and target_industries == ["__ANY__"]:
            target_industries = None
            logger.info("Industries set to 'Any' — no industry filtering")

        logger.info(f"Pipeline config: {len(target_industries) if target_industries else 'Any'} industries, {len(exclude_keywords)} exclusions, {len(target_job_titles) if target_job_titles else 'Any'} job titles")

        # Determine LOB type to decide which adapter category to use
        # Job board adapters (JSearch, SerpAPI, etc.) are only relevant for staffing LOBs.
        # Non-staffing LOBs (RCM, software_dev, ai_services, digital_marketing) use
        # LOB-specific lead source adapters instead (NPI, Crunchbase, PageSpeed, etc.).
        lob_type = None
        if lob_id:
            from app.db.models.line_of_business import LineOfBusiness
            lob_obj = db.query(LineOfBusiness).filter(LineOfBusiness.lob_id == lob_id).first()
            if lob_obj:
                lob_type = lob_obj.lob_type

        use_job_boards = lob_type in (None, "staffing", "custom")

        all_jobs = []

        # Reusable parallel collector — fetches a subset of job-source adapters
        # and updates the run-scoped bookkeeping (counters, diagnostics, per-source
        # detail). Closure over the pipeline config above.
        def _collect_from_adapters(adapter_subset: List[Tuple[str, Any]]) -> List[Dict[str, Any]]:
            collected: List[Dict[str, Any]] = []
            if not adapter_subset:
                return collected
            with concurrent.futures.ThreadPoolExecutor(max_workers=pipeline_max_workers) as executor:
                futures = []
                for source_name, adapter in adapter_subset:
                    adapter_tuning = job_source_tuning.get(source_name, {})
                    futures.append(executor.submit(
                        fetch_from_source,
                        source_name,
                        adapter,
                        target_industries,
                        exclude_keywords,
                        target_job_titles,
                        exclude_company_keywords=exclude_company_keywords,
                        exclude_title_keywords=exclude_title_keywords,
                        match_mode=match_mode,
                        location_diversification=location_diversification,
                        target_states=target_states,
                        tuning=adapter_tuning,
                        adapter_limit=pipeline_adapter_limit,
                        posted_within_days=posted_within_days,
                        push_negatives=push_exclusions_to_query,
                    ))
                for future in concurrent.futures.as_completed(futures):
                    source_name, jobs, error, diag = future.result()
                    counters["sources_used"].append(source_name)
                    counters["jobs_per_source"][source_name] = len(jobs)
                    per_source_detail[source_name] = {"fetched": len(jobs), "new": 0, "existing_in_db": 0, "skipped_dedup": 0}
                    api_diagnostics_list.append({
                        "adapter": source_name,
                        "status": diag["status"],
                        "jobs_returned": diag["jobs_returned"],
                        "error_type": diag["error_type"],
                        "error_message": diag["error_message"],
                    })
                    if error:
                        counters["errors"] += 1
                        logger.error(f"Source {source_name} failed", error=error)
                    else:
                        logger.info(f"Fetched {len(jobs)} jobs from {source_name}")
                        for job in jobs:
                            job["_pipeline_source"] = source_name
                            sub_src = job.get("source", "unknown")
                            job["_sub_source"] = sub_src
                            if sub_src not in per_sub_source_detail:
                                per_sub_source_detail[sub_src] = {"fetched": 0, "new": 0, "existing_in_db": 0, "skipped_dedup": 0}
                            per_sub_source_detail[sub_src]["fetched"] += 1
                        collected.extend(jobs)
            all_jobs.extend(collected)
            return collected

        # --- Job board adapters (staffing + legacy/custom only) ---
        if use_job_boards:
            adapters = get_all_job_source_adapters(db, tenant_id=tenant_id)

            # 1) Drop redundant providers that share an index (e.g. SerpAPI vs
            #    SearchAPI — both Google Jobs). Only the preferred one runs.
            overlap_groups = get_tenant_setting(db, "source_overlap_groups", tenant_id=tenant_id, default=None) or SOURCE_OVERLAP_GROUPS
            adapters, overlap_skipped = _filter_overlap_groups(adapters, overlap_groups)
            if overlap_skipped:
                logger.info(f"Overlap groups: skipping redundant providers {overlap_skipped} (share an index with a higher-priority source)")

            # 2) Split into coverage tiers (tier 1 = free/cheap/unique, tier 2 = expensive/overlapping)
            tier_map = get_tenant_setting(db, "source_tiers", tenant_id=tenant_id, default=None) or SOURCE_TIERS
            tier1, tier2 = _partition_tiers(adapters, tier_map)

            # 3) Per-run target. Tier 2 (expensive) runs only to fill a gap toward
            #    this many unique leads. 0 disables early-stop (all tiers run).
            target = int(get_tenant_setting(db, "lead_sourcing_target_per_run", tenant_id=tenant_id, default=500) or 0)
            optimization = {
                "target_per_run": target,
                "overlap_skipped": overlap_skipped,
                "tier1": [n for n, _ in tier1],
                "tier2_available": [n for n, _ in tier2],
                "tier2_ran": [],
                "tier2_skipped": [],
                "early_stopped": False,
                "unique_after_tier1": None,
            }
            logger.info(
                f"Source optimization — tier1: {optimization['tier1']}, tier2: {optimization['tier2_available']}, "
                f"target/run: {target}, overlap_skipped: {overlap_skipped}"
            )

            # 4) Always run tier 1 (parallel)
            _collect_from_adapters(tier1)

            # 5) Run tier 2 only to fill a gap, cheapest-first, stop when target met
            if tier2:
                if target > 0:
                    unique_now = deduplicate_jobs(all_jobs, db, tenant_id=tenant_id)
                    optimization["unique_after_tier1"] = len(unique_now)
                    if len(unique_now) >= target:
                        optimization["tier2_skipped"] = [n for n, _ in tier2]
                        optimization["early_stopped"] = True
                        logger.info(
                            f"Target {target} met by tier-1 ({len(unique_now)} unique) — "
                            f"skipping tier-2 entirely: {optimization['tier2_skipped']} (saved API spend)"
                        )
                    else:
                        for source_name, adapter in tier2:
                            _collect_from_adapters([(source_name, adapter)])
                            optimization["tier2_ran"].append(source_name)
                            unique_now = deduplicate_jobs(all_jobs, db, tenant_id=tenant_id)
                            if len(unique_now) >= target:
                                optimization["tier2_skipped"] = [n for n, _ in tier2 if n not in optimization["tier2_ran"]]
                                optimization["early_stopped"] = True
                                logger.info(
                                    f"Target {target} met after {source_name} ({len(unique_now)} unique) — "
                                    f"skipping remaining tier-2: {optimization['tier2_skipped']} (saved API spend)"
                                )
                                break
                else:
                    # Early-stop disabled — run all tier-2 in parallel too
                    _collect_from_adapters(tier2)
                    optimization["tier2_ran"] = [n for n, _ in tier2]

            counters["source_optimization"] = optimization
            logger.info(f"Total jobs fetched from job boards: {len(all_jobs)}")
        else:
            adapters = []
            logger.info(f"Skipping job board adapters for LOB type '{lob_type}' — using LOB-specific sources only")

        # --- LOB-specific lead sources (Phase 2) ---
        lob_adapters = get_lob_lead_source_adapters(db, tenant_id=tenant_id, lob_id=lob_id)
        if lob_adapters:
            logger.info(f"Using {len(lob_adapters)} LOB-specific lead source adapters", lob_id=lob_id)

            # Get LOB-specific query params from LOB config
            from app.core.settings_resolver import get_lob_config
            lob_source_config = get_lob_config(db, lob_id, "lead_source_config") or {} if lob_id else {}
            lob_query = lob_source_config.get("query", "")
            lob_location = lob_source_config.get("location", "United States")

            with concurrent.futures.ThreadPoolExecutor(max_workers=pipeline_max_workers) as executor:
                lob_futures = []
                for source_name, adapter in lob_adapters:
                    # Source-specific extra params from config
                    extra = lob_source_config.get(source_name, {})
                    future = executor.submit(
                        fetch_from_lob_source,
                        source_name,
                        adapter,
                        query=extra.get("query", lob_query),
                        location=extra.get("location", lob_location),
                        limit=extra.get("limit", 100),
                        extra_params={k: v for k, v in extra.items() if k not in ("query", "location", "limit")},
                    )
                    lob_futures.append(future)

                for future in concurrent.futures.as_completed(lob_futures):
                    source_name, leads, error, diag = future.result()
                    counters["sources_used"].append(source_name)
                    counters["jobs_per_source"][source_name] = len(leads)
                    per_source_detail[source_name] = {"fetched": len(leads), "new": 0, "existing_in_db": 0, "skipped_dedup": 0}
                    api_diagnostics_list.append({
                        "adapter": source_name,
                        "status": diag["status"],
                        "jobs_returned": diag["jobs_returned"],
                        "error_type": diag["error_type"],
                        "error_message": diag["error_message"],
                    })
                    if error:
                        counters["errors"] += 1
                        logger.error(f"LOB source {source_name} failed", error=error)
                    else:
                        logger.info(f"Fetched {len(leads)} leads from LOB source {source_name}")
                        for lead in leads:
                            lead["_pipeline_source"] = source_name
                            lead["_sub_source"] = lead.get("source", source_name)
                            sub_src = lead["_sub_source"]
                            if sub_src not in per_sub_source_detail:
                                per_sub_source_detail[sub_src] = {"fetched": 0, "new": 0, "existing_in_db": 0, "skipped_dedup": 0}
                            per_sub_source_detail[sub_src]["fetched"] += 1
                        all_jobs.extend(leads)

            logger.info(f"Total leads after LOB sources: {len(all_jobs)}")

        # Record cost per source
        all_adapters_for_cost = list(adapters) + list(lob_adapters if lob_adapters else [])
        try:
            from app.services.cost_tracker import record_pipeline_cost
            for source_name, adapter in all_adapters_for_cost:
                api_calls = getattr(adapter, 'api_calls_made', 0)
                results = counters["jobs_per_source"].get(source_name, 0)
                if api_calls > 0 or results > 0:
                    record_pipeline_cost(db, source_name, api_calls, results, run_id=job_run.run_id)
            db.commit()
        except Exception as e:
            logger.warning(f"Failed to record pipeline costs: {e}")

        # Deduplicate jobs (both within batch and against DB)
        unique_jobs = deduplicate_jobs(all_jobs, db, tenant_id=tenant_id)
        skipped_count = len(all_jobs) - len(unique_jobs)
        counters["skipped"] = skipped_count

        # Track per-source dedup: compare which source jobs survived
        unique_sources = {}
        unique_sub_sources = {}
        for job in unique_jobs:
            src = job.get("_pipeline_source", "unknown")
            unique_sources[src] = unique_sources.get(src, 0) + 1
            sub_src = job.get("_sub_source", job.get("source", "unknown"))
            unique_sub_sources[sub_src] = unique_sub_sources.get(sub_src, 0) + 1
        for src, detail in per_source_detail.items():
            survived = unique_sources.get(src, 0)
            detail["skipped_dedup"] = detail["fetched"] - survived
        for sub_src, detail in per_sub_source_detail.items():
            survived = unique_sub_sources.get(sub_src, 0)
            detail["skipped_dedup"] = detail["fetched"] - survived

        logger.info(f"After deduplication: {len(unique_jobs)} unique jobs (skipped {skipped_count} duplicates)")

        # --- Company exclusion filter ---
        # Load active excluded company names for this tenant (normalized)
        from app.db.models.company_exclusion import CompanyExclusion, normalize_company_for_exclusion
        excluded_companies_set = set()
        try:
            excluded_rows = db.query(CompanyExclusion.company_name_normalized).filter(
                CompanyExclusion.tenant_id == (tenant_id or 1),
                CompanyExclusion.is_active == True,
            )
            # If LOB is specified, include both LOB-specific and global (lob_id=NULL) exclusions
            if lob_id:
                excluded_rows = excluded_rows.filter(
                    (CompanyExclusion.lob_id == lob_id) | (CompanyExclusion.lob_id == None)
                )
            excluded_companies_set = {r[0] for r in excluded_rows.all()}
        except Exception as e:
            logger.warning(f"Failed to load company exclusions: {e}")

        if excluded_companies_set:
            pre_exclusion_count = len(unique_jobs)
            unique_jobs = [
                job for job in unique_jobs
                if normalize_company_for_exclusion(job.get("client_name") or "") not in excluded_companies_set
            ]
            excluded_count = pre_exclusion_count - len(unique_jobs)
            counters["excluded_companies"] = excluded_count
            logger.info(f"Company exclusion filter: removed {excluded_count} leads from {len(excluded_companies_set)} excluded companies")

        # --- Company size / industry / placeholder gate ---
        # Drops big companies (>ceiling employees), out-of-scope industries
        # (IT / staffing / government), and confidential/blank employers — cases
        # the keyword filters cannot detect from a bare brand name. Missing
        # attributes are filled by a bounded, cached LLM enrichment step first.
        unique_jobs = _apply_company_gate(
            db,
            unique_jobs,
            counters,
            tenant_id=tenant_id,
            max_employee_count=max_employee_count,
            min_employee_count=min_employee_count,
            drop_confidential=drop_confidential,
            excluded_industries=excluded_industries,
            enrich=enrich_company_at_source,
            enrich_max_companies=enrich_max_companies,
            min_salary_threshold=min_salary_threshold,
        )

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
                    tenant_id=tenant_id or 1,
                    client_name=job_data["client_name"],
                    job_title=job_data["job_title"],
                    state=job_data.get("state"),
                    posting_date=job_data.get("posting_date"),
                    job_link=job_data.get("job_link"),
                    salary_min=job_data.get("salary_min"),
                    salary_max=job_data.get("salary_max"),
                    source=", ".join(job_data.get("all_sources", [job_data.get("source", "unknown")])),
                    employment_type=job_data.get("employment_type") or None,
                    lead_status=LeadStatus.NEW,  # NEW status allows contact enrichment to pick it up
                    # Pre-populate contact info if available from Coresignal
                    first_name=job_data.get("contact_first_name"),
                    last_name=job_data.get("contact_last_name"),
                    contact_email=job_data.get("contact_email"),
                    contact_title=job_data.get("contact_title"),
                    # Enhanced dedup fields
                    external_job_id=job_data.get("external_job_id") or None,
                    city=job_data.get("city") or None,
                    employer_linkedin_url=job_data.get("employer_linkedin_url") or None,
                    employer_website=job_data.get("employer_website") or None,
                    industry=job_data.get("industry") or None,
                    company_size=str(job_data.get("company_size", "")) if job_data.get("company_size") else None,
                    run_id=job_run.run_id,
                    lob_id=lob_id,
                    metadata_json=json.dumps(job_data["metadata"]) if job_data.get("metadata") else None,
                )
                db.add(lead)
                # Flush immediately to catch IntegrityError per-lead
                # (e.g. duplicate job_link) before the session is poisoned
                db.flush()

                # Only increment counters AFTER flush succeeds
                counters["inserted"] += 1
                newly_inserted_leads.append(lead)

                # Track per-source new insertions
                job_src = job_data.get("_pipeline_source", "unknown")
                if job_src in per_source_detail:
                    per_source_detail[job_src]["new"] += 1
                # Track per-sub-source new insertions
                sub_src = job_data.get("_sub_source", job_data.get("source", "unknown"))
                if sub_src in per_sub_source_detail:
                    per_sub_source_detail[sub_src]["new"] += 1

                # Upsert client_info with normalized name + enrichment data
                upsert_client(
                    db, job_data["client_name"],
                    employer_website=job_data.get("employer_website"),
                    employer_linkedin_url=job_data.get("employer_linkedin_url"),
                    tenant_id=tenant_id,
                    industry=job_data.get("industry"),
                    company_size=str(job_data.get("company_size", "")) if job_data.get("company_size") else None,
                )

            except Exception as e:
                # Rollback to reset the session after IntegrityError or any
                # other DB error — without this, the session stays broken and
                # ALL subsequent operations fail
                db.rollback()
                logger.warning("Error processing job (rolled back)", error=str(e), job=job_data.get("client_name"))
                counters["errors"] += 1

        db.commit()

        # Auto-enrich newly inserted leads from existing company contacts
        auto_enriched = _auto_enrich_new_leads(db, newly_inserted_leads, tenant_id=tenant_id)
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
        # Compute existing_in_db for each source (fetched - new - skipped_dedup)
        for src, detail in per_source_detail.items():
            detail["existing_in_db"] = max(0, detail["fetched"] - detail["new"] - detail["skipped_dedup"])
        for sub_src, detail in per_sub_source_detail.items():
            detail["existing_in_db"] = max(0, detail["fetched"] - detail["new"] - detail["skipped_dedup"])

        job_run.counters_json = json.dumps({
            "inserted": counters["inserted"],
            "updated": counters["updated"],
            "skipped": counters["skipped"],
            "errors": counters["errors"],
            "auto_enriched": counters.get("auto_enriched", 0),
            "excluded_companies": counters.get("excluded_companies", 0),
            "excluded_confidential": counters.get("excluded_confidential", 0),
            "excluded_too_large": counters.get("excluded_too_large", 0),
            "excluded_industry": counters.get("excluded_industry", 0),
            "enriched_companies": counters.get("enriched_companies", 0),
            "sources": counters["sources_used"],
            "per_source": counters["jobs_per_source"],
            "per_source_detail": per_source_detail,
            "per_sub_source_detail": per_sub_source_detail,
            "api_diagnostics": api_diagnostics_list,
        })
        db.commit()

        logger.info("Lead sourcing completed",
                   inserted=counters["inserted"],
                   skipped=counters["skipped"],
                   sources=counters["sources_used"])

        return counters

    except Exception as e:
        logger.error("Lead sourcing pipeline failed", error=str(e))
        # Try to mark the run as FAILED so it doesn't stay as "running" forever.
        # The session may be broken (e.g. after IntegrityError), so we:
        #   1. Rollback the broken session first
        #   2. Attempt the status update
        #   3. If that still fails, use a fresh session as last resort
        try:
            db.rollback()
            job_run.status = JobStatus.FAILED
            job_run.error_message = str(e)[:500]
            job_run.ended_at = datetime.utcnow()
            db.commit()
        except Exception as inner_err:
            logger.error("Failed to mark run as FAILED via original session, trying fresh session", error=str(inner_err))
            try:
                db.close()
            except Exception:
                pass
            # Last resort: open a brand new session and do a raw UPDATE
            try:
                fresh_db = SessionLocal()
                fresh_db.query(JobRun).filter(JobRun.run_id == job_run.run_id).update({
                    "status": JobStatus.FAILED,
                    "error_message": str(e)[:500],
                    "ended_at": datetime.utcnow(),
                })
                fresh_db.commit()
                fresh_db.close()
                logger.info("Marked run as FAILED via fresh session", run_id=job_run.run_id)
            except Exception as last_err:
                logger.error("Could not mark run as FAILED even with fresh session", error=str(last_err), run_id=job_run.run_id)
        raise
    finally:
        try:
            db.close()
        except Exception:
            pass


def _extract_domain(url: str) -> str:
    """Extract domain from URL (e.g., 'https://www.example.com/page' -> 'example.com')."""
    if not url:
        return ""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url if url.startswith("http") else f"https://{url}")
        host = parsed.hostname or ""
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return ""


def _apply_company_gate(
    db,
    jobs: List[Dict[str, Any]],
    counters: Dict[str, Any],
    tenant_id: Optional[int] = None,
    max_employee_count: int = 500,
    min_employee_count: int = 1,
    drop_confidential: bool = True,
    excluded_industries: Optional[List[str]] = None,
    enrich: bool = True,
    enrich_max_companies: int = 300,
    min_salary_threshold: int = 0,
) -> List[Dict[str, Any]]:
    """Drop out-of-scope companies by size / industry / placeholder name.

    Runs after keyword + company-name exclusion. Fills missing industry/size via
    a bounded, cached LLM step (``resolve_company_metadata_batch``) so the gate
    can act on sources that don't return company attributes. Mutates ``counters``
    with per-reason drop counts and returns the surviving jobs.
    """
    from app.services.company_filters import (
        is_placeholder_company,
        industry_is_excluded,
        exceeds_size_ceiling,
        below_size_floor,
        salary_below_threshold,
    )

    counters.setdefault("excluded_confidential", 0)
    counters.setdefault("excluded_too_large", 0)
    counters.setdefault("excluded_too_small", 0)
    counters.setdefault("excluded_industry", 0)
    counters.setdefault("excluded_salary", 0)
    counters.setdefault("enriched_companies", 0)

    if not jobs:
        return jobs

    # 1) Placeholder / confidential employers — no enrichment needed.
    if drop_confidential:
        kept = []
        for job in jobs:
            if is_placeholder_company(job.get("client_name")):
                counters["excluded_confidential"] += 1
            else:
                kept.append(job)
        jobs = kept

    # 2) Fill missing industry/size (ClientInfo cache + bounded LLM), annotate jobs.
    if enrich and jobs:
        missing = [
            (job.get("client_name"), job.get("employer_website") or "")
            for job in jobs
            if not (job.get("industry") and (job.get("company_size") or job.get("_employee_count")))
        ]
        if missing:
            try:
                from app.services.company_enrichment import resolve_company_metadata_batch
                meta = resolve_company_metadata_batch(
                    db, missing, tenant_id=tenant_id, max_llm_calls=enrich_max_companies,
                )
            except Exception as e:  # enrichment is best-effort; never fail the run
                logger.warning(f"Company metadata enrichment failed: {e}")
                meta = {}

            enriched = 0
            for job in jobs:
                key = (job.get("client_name") or "").strip().lower()
                m = meta.get(key)
                if not m:
                    continue
                filled = False
                if not job.get("industry") and m.get("industry"):
                    job["industry"] = m["industry"]
                    filled = True
                if m.get("employee_count") is not None:
                    job["_employee_count"] = m["employee_count"]
                    if not job.get("company_size"):
                        job["company_size"] = str(m["employee_count"])
                    filled = True
                if not job.get("company_size") and m.get("company_size"):
                    job["company_size"] = m["company_size"]
                    filled = True
                if filled:
                    enriched += 1
            counters["enriched_companies"] += enriched

    # 3) Salary + size + industry gate.
    final = []
    for job in jobs:
        if salary_below_threshold(job.get("salary_min"), job.get("salary_max"), min_salary_threshold):
            counters["excluded_salary"] += 1
            continue
        size_signal = job.get("_employee_count")
        if size_signal is None:
            size_signal = job.get("company_size")
        if exceeds_size_ceiling(size_signal, max_employee_count):
            counters["excluded_too_large"] += 1
            continue
        if below_size_floor(size_signal, min_employee_count):
            counters["excluded_too_small"] += 1
            continue
        if industry_is_excluded(job.get("industry"), excluded_industries):
            counters["excluded_industry"] += 1
            continue
        final.append(job)

    logger.info(
        "Company gate: dropped %s confidential, %s too-large, %s too-small, %s industry-excluded (enriched %s companies)",
        counters["excluded_confidential"], counters["excluded_too_large"],
        counters["excluded_too_small"], counters["excluded_industry"],
        counters["enriched_companies"],
    )
    return final


def upsert_client(db, client_name: str, employer_website: str = None, employer_linkedin_url: str = None, tenant_id: int = None, industry: str = None, company_size: str = None):
    """Create or update client_info record with normalized matching."""
    try:
        # Try exact match first (scoped to tenant)
        q = db.query(ClientInfo).filter(ClientInfo.client_name == client_name)
        if tenant_id is not None:
            q = q.filter(ClientInfo.tenant_id == tenant_id)
        client = q.first()

        # If not found, try normalized match
        if not client:
            normalized = normalize_company_name(client_name)
            cq = db.query(ClientInfo)
            if tenant_id is not None:
                cq = cq.filter(ClientInfo.tenant_id == tenant_id)
            all_clients = cq.all()
            for c in all_clients:
                if normalize_company_name(c.client_name) == normalized:
                    client = c
                    break

        if not client:
            client = ClientInfo(
                tenant_id=tenant_id or 1,
                client_name=client_name,
                status=ClientStatus.ACTIVE,
                start_date=date.today(),
                service_count=1,
                client_category=ClientCategory.PROSPECT,
            )
            # Populate enrichment fields from lead data
            if employer_website:
                client.website = employer_website
                client.domain = _extract_domain(employer_website)
            if employer_linkedin_url:
                client.linkedin_url = employer_linkedin_url
            if industry:
                client.industry = industry
            if company_size:
                client.company_size = company_size
            db.add(client)
            db.flush()
        else:
            client.service_count = (client.service_count or 0) + 1

            # Backfill missing website/linkedin from lead data
            if employer_website and not client.website:
                client.website = employer_website
                if not client.domain:
                    client.domain = _extract_domain(employer_website)
            if employer_linkedin_url and not client.linkedin_url:
                client.linkedin_url = employer_linkedin_url
            if industry and not client.industry:
                client.industry = industry
            if company_size and not client.company_size:
                client.company_size = company_size

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
    tenant_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Import leads from XLSX file."""
    db = SessionLocal()
    counters = {"inserted": 0, "updated": 0, "skipped": 0, "errors": 0}

    try:
        df = pd.read_excel(filepath)
        logger.info(f"Reading {len(df)} rows from {filepath}")

        from app.services.lead_eligibility import LeadEligibilityGate
        gate = LeadEligibilityGate(db, tenant_id=tenant_id)
        counters.setdefault("excluded", 0)

        for _, row in df.iterrows():
            try:
                client_name = str(row.get("Company", row.get("client_name", "")))
                job_title = str(row.get("Job Title", row.get("job_title", "")))

                if not client_name or not job_title:
                    counters["skipped"] += 1
                    continue

                # Exclusion gate — do not import out-of-scope companies. Name-based
                # rules apply (placeholder / blacklist / keyword); industry/size
                # are unknown at import and resolved later by the enrichment gate.
                eligible, reason = gate.check({"client_name": client_name, "job_title": job_title})
                if not eligible:
                    counters["excluded"] += 1
                    logger.info("Import row excluded by gate", company=client_name, reason=reason)
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
                    tenant_id=tenant_id or 1,
                    client_name=client_name,
                    job_title=job_title,
                    state=str(row.get("State", row.get("state", ""))) if pd.notna(row.get("State", row.get("state"))) else None,
                    source="file_import",
                    employment_type=str(row.get("Position Type", row.get("Employment Type", ""))) if pd.notna(row.get("Position Type", row.get("Employment Type"))) else None,
                    lead_status=LeadStatus.OPEN,
                )
                db.add(lead)
                counters["inserted"] += 1

                upsert_client(db, client_name, tenant_id=tenant_id)

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
