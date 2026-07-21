"""Pipeline run summary generation with deterministic scoring, enhanced diagnostics, and optional AI narratives."""
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from sqlalchemy.orm import Session

from app.db.models.job_run import JobRun, JobStatus

logger = logging.getLogger(__name__)

# --- Constants ---

SUB_SOURCE_LABELS = {
    "linkedin": "LinkedIn",
    "indeed": "Indeed",
    "glassdoor": "Glassdoor",
    "ziprecruiter": "ZipRecruiter",
    "jsearch": "Other (JSearch)",
    "apollo": "Apollo.io",
}

ADAPTER_LABELS = {
    "jsearch": "JSearch (RapidAPI)",
    "apollo": "Apollo.io",
    "seamless": "Seamless.AI",
    "theirstack": "TheirStack",
    "serpapi": "SerpAPI (Google Jobs)",
    "adzuna": "Adzuna",
    "hunter_contact": "Hunter.io (Contacts)",
    "snovio": "Snov.io",
    "rocketreach": "RocketReach",
    "pdl": "People Data Labs",
    "proxycurl": "Proxycurl",
    "clearbit": "Clearbit",
    "opencorporates": "OpenCorporates",
    "neverbounce": "NeverBounce",
    "zerobounce": "ZeroBounce",
    "hunter": "Hunter.io",
    "clearout": "Clearout",
    "emailable": "Emailable",
    "mailboxvalidator": "MailboxValidator",
    "reacher": "Reacher",
    "smtp": "SMTP (Direct Send)",
    "mailmerge": "Mail Merge (CSV Export)",
    "mock": "Mock (Test Data)",
}

PIPELINE_LABELS = {
    "lead_sourcing": "Lead Sourcing",
    "contact_enrichment": "Contact Enrichment",
    "email_validation": "Email Validation",
    "outreach_send": "Outreach Send",
    "outreach": "Outreach Send",
    "outreach_mailmerge": "Outreach Mail Merge",
}

PIPELINE_MECHANISM_KNOWLEDGE = {
    "lead_sourcing": (
        "Lead Sourcing Pipeline fetches job postings from configured sources (JSearch via RapidAPI, Apollo.io). "
        "Jobs are filtered by 22 non-IT target industries, exclude IT keywords and US staffing agencies. "
        "Salary threshold: $30k+. Posted within last 30 days. Location: United States. "
        "Deduplication uses normalized company name + job title + state as composite key. "
        "Auto-enrichment copies existing company contacts to new leads (zero API calls). "
        "Sources run in parallel via ThreadPoolExecutor (max 3 workers)."
    ),
    "contact_enrichment": (
        "Contact Enrichment discovers decision-makers for leads using Apollo.io and/or Seamless.AI. "
        "Max 4 contacts per company per job. Priority levels: P1 (job poster) to P5 (functional manager). "
        "Cache-first strategy: reuses existing company contacts before making API calls. "
        "Company sibling enrichment: when a company's contacts are found, all leads for that company get enriched. "
        "Apollo contacts auto-marked as 'valid' (pre-verified). Other sources marked 'pending'. "
        "ApolloCreditsExhaustedError stops pipeline early (intentional - avoids wasting remaining leads)."
    ),
    "email_validation": (
        "Email Validation verifies contact emails using one configured provider per run. "
        "Supported: NeverBounce, ZeroBounce, Hunter.io, Clearout, Emailable, MailboxValidator, Reacher. "
        "Results: valid, invalid, catch_all, unknown. Stored in email_validation_results table. "
        "Previously validated emails are skipped (cache hit). Only unvalidated contacts processed. "
        "Validated leads progress from 'enriched' to 'validated' status. "
        "Bounce rate calculated as: invalid / total_validated * 100."
    ),
    "outreach_send": (
        "Outreach Send emails contacts with validated emails via SMTP through configured sender mailboxes. "
        "Daily limit: 30 emails per mailbox. Cooldown: 10 days between emails to same contact. "
        "Only contacts with 'valid' validation status receive outreach. "
        "Mailbox selection: active mailboxes with 'cold_ready' or 'active' warmup status, least loaded first. "
        "Each email gets open/click tracking (pixel + link redirect), unsubscribe footer. "
        "Templates rendered with merge fields. Fallback to hardcoded template if none active."
    ),
    "outreach_mailmerge": (
        "Outreach Mailmerge exports verified, eligible contacts to CSV for external mail merge tools (Word/Outlook). "
        "Same eligibility rules as outreach_send (valid email, not in cooldown, not archived). "
        "Creates: contacts CSV + Word template guide with merge field instructions. "
        "Records OutreachEvent for each contact (channel=MAILMERGE, status=SENT)."
    ),
}
# Alias for the short name
PIPELINE_MECHANISM_KNOWLEDGE["outreach"] = PIPELINE_MECHANISM_KNOWLEDGE["outreach_send"]

# Maps error_type -> (root_cause_template, [solution_templates])
# {adapter_label} is substituted at runtime with the human-readable adapter name.
ERROR_TYPE_FALLBACK_SOLUTIONS: Dict[str, tuple] = {
    "api_key_invalid": (
        "The API key for {adapter_label} is missing, expired, or incorrect.",
        [
            "Verify your API key in Settings > Integrations for {adapter_label}.",
            "Regenerate the key in your {adapter_label} account dashboard.",
            "Ensure the API key has the required scopes/permissions.",
        ],
    ),
    "credits_exhausted": (
        "API credits for {adapter_label} have been fully consumed.",
        [
            "Check your remaining credits in the {adapter_label} account dashboard.",
            "Upgrade your {adapter_label} plan for additional credits.",
            "Enable alternative data sources to reduce dependency on {adapter_label}.",
        ],
    ),
    "rate_limited": (
        "Too many requests were sent to {adapter_label} in a short period.",
        [
            "Wait 15-30 minutes before retrying the pipeline.",
            "Reduce the number of parallel workers in pipeline settings.",
            "Consider upgrading your {adapter_label} API tier for higher rate limits.",
        ],
    ),
    "connection_error": (
        "Network or DNS failure when connecting to {adapter_label}.",
        [
            "Check your server's internet connectivity.",
            "Check if {adapter_label} is experiencing an outage (status page).",
            "Verify firewall rules are not blocking outbound requests.",
            "Retry the pipeline — transient network issues often resolve themselves.",
        ],
    ),
    "high_error_rate": (
        "More than 50% of validation requests to {adapter_label} returned errors.",
        [
            "Check {adapter_label} service status for any ongoing incidents.",
            "Review the quality of email addresses being submitted for validation.",
            "Try switching to a different email validation provider.",
        ],
    ),
    "smtp_failure": (
        "SMTP authentication or connectivity failed for {adapter_label}.",
        [
            "Verify mailbox credentials (email + app password) in Mailbox settings.",
            "Check SMTP port and TLS/SSL configuration.",
            "Verify SPF, DKIM, and DMARC DNS records for the sending domain.",
            "Check if the sending IP or domain is on any email blacklists.",
        ],
    ),
    "no_match": (
        "Zero results returned from {adapter_label} for the given search criteria.",
        [
            "Broaden search criteria (expand job titles, industries, or locations).",
            "Verify that {adapter_label} has coverage for your target market.",
            "Check if search filters are too restrictive.",
        ],
    ),
    "low_results": (
        "Fewer results than expected were returned from {adapter_label}.",
        [
            "Review target job titles and industries for broader coverage.",
            "{adapter_label} may have limited data for your specific market segment.",
            "Consider adding more data providers to supplement results.",
        ],
    ),
    "pipeline_failure": (
        "An unhandled exception occurred during pipeline execution.",
        [
            "Check the error message details below for specifics.",
            "Review application logs for the full stack trace.",
            "Retry the pipeline — transient errors may resolve on retry.",
        ],
    ),
    "unknown": (
        "An unexpected error occurred with {adapter_label}.",
        [
            "Review the error message for more details.",
            "Check application logs for additional context.",
            "If the issue persists, contact support with the run ID.",
        ],
    ),
}


def build_error_details(counters: Dict[str, Any], error_message: Optional[str] = None) -> List[Dict[str, Any]]:
    """Extract error entries from api_diagnostics and top-level error_message.

    Returns a list of dicts with keys: error_type, adapter, adapter_label, message,
    root_cause (empty string), proposed_solutions (empty list).
    """
    errors: List[Dict[str, Any]] = []
    seen_messages: set = set()

    # 1. Scan api_diagnostics for entries with status="error"/"warning" AND error_type set
    api_diag = counters.get("api_diagnostics", [])
    if isinstance(api_diag, list):
        for d in api_diag:
            if not isinstance(d, dict):
                continue
            diag_status = d.get("status", "")
            error_type = d.get("error_type")
            if diag_status == "error" and error_type:
                msg = d.get("error_message", "") or ""
                adapter = d.get("adapter", "unknown")
                errors.append({
                    "error_type": error_type,
                    "adapter": adapter,
                    "adapter_label": ADAPTER_LABELS.get(adapter, adapter),
                    "message": msg,
                    "root_cause": "",
                    "proposed_solutions": [],
                })
                if msg:
                    seen_messages.add(msg.strip().lower())
            elif diag_status == "warning" and error_type:
                msg = d.get("error_message", "") or ""
                adapter = d.get("adapter", "unknown")
                errors.append({
                    "error_type": error_type,
                    "adapter": adapter,
                    "adapter_label": ADAPTER_LABELS.get(adapter, adapter),
                    "message": msg,
                    "root_cause": "",
                    "proposed_solutions": [],
                })
                if msg:
                    seen_messages.add(msg.strip().lower())

    # 2. If top-level error_message exists and isn't already captured, add as pipeline_failure
    if error_message:
        normalized = error_message.strip().lower()
        if normalized not in seen_messages:
            errors.append({
                "error_type": "pipeline_failure",
                "adapter": None,
                "adapter_label": "Pipeline",
                "message": error_message,
                "root_cause": "",
                "proposed_solutions": [],
            })

    return errors


def _fill_error_analysis_fallback(error_details: List[Dict[str, Any]]) -> None:
    """Fill root_cause and proposed_solutions using ERROR_TYPE_FALLBACK_SOLUTIONS templates.

    Modifies error_details in-place. Uses {adapter_label} substitution.
    Falls back to 'unknown' for unrecognized error_types.
    """
    for entry in error_details:
        error_type = entry.get("error_type", "unknown")
        adapter_label = entry.get("adapter_label", "the service")
        template = ERROR_TYPE_FALLBACK_SOLUTIONS.get(error_type, ERROR_TYPE_FALLBACK_SOLUTIONS["unknown"])
        root_cause_tpl, solutions_tpl = template
        entry["root_cause"] = root_cause_tpl.format(adapter_label=adapter_label)
        entry["proposed_solutions"] = [s.format(adapter_label=adapter_label) for s in solutions_tpl]


def calculate_success_score(pipeline_name: str, counters: Dict[str, Any], status: str) -> int:
    """Calculate a deterministic 0-100 success score from pipeline counters.

    Args:
        pipeline_name: Name of the pipeline (lead_sourcing, contact_enrichment, etc.)
        counters: Parsed counters dict from job_run.counters_json
        status: Job status string (completed, failed, cancelled)

    Returns:
        Integer score 0-100
    """
    if status == "failed":
        return 0

    pipeline = pipeline_name.lower()
    errors = counters.get("errors", 0)

    if pipeline == "lead_sourcing":
        inserted = counters.get("inserted", 0)
        updated = counters.get("updated", 0)
        skipped = counters.get("skipped", 0)
        total = inserted + updated + skipped + errors
        if total == 0:
            return 0
        base = ((inserted + updated) / total) * 100
        penalty = min(errors * 5, 30)
        return max(0, min(100, round(base - penalty)))

    if pipeline == "contact_enrichment":
        contacts_found = counters.get("contacts_found", 0)
        leads_enriched = counters.get("leads_enriched", 0)
        skipped = counters.get("skipped", 0)
        contacts_reused = counters.get("contacts_reused", 0)
        total = contacts_found + skipped + errors
        if total == 0:
            total = leads_enriched or 1
        base = (contacts_found / total) * 100
        bonus = min(contacts_reused * 2, 10)
        return max(0, min(100, round(base + bonus)))

    if pipeline == "email_validation":
        valid = counters.get("valid", 0)
        invalid = counters.get("invalid", 0)
        validated = counters.get("validated", 0) or (valid + invalid + errors)
        if validated == 0:
            return 0
        base = (valid / validated) * 100
        bounce_rate = invalid / validated if validated > 0 else 0
        penalty = min(bounce_rate * 400, 20)  # -4 per 1% bounce, max -20
        return max(0, min(100, round(base - penalty)))

    if pipeline in ("outreach_send", "outreach"):
        sent = counters.get("sent", 0)
        exported = counters.get("exported", 0)
        total = counters.get("total", 0) or (sent + errors)
        if total == 0:
            return 0 if sent == 0 and exported == 0 else 100
        base = (sent / total) * 100
        penalty = min(errors * 10, 40)
        return max(0, min(100, round(base - penalty)))

    if pipeline == "outreach_mailmerge":
        exported = counters.get("exported", 0)
        total = counters.get("total", 0) or exported
        if total == 0:
            return 0 if exported == 0 else 100
        return max(0, min(100, round((exported / total) * 100)))

    # Unknown pipeline — return 50 as neutral
    return 50


def build_quality_funnel(pipeline_name: str, counters: Dict[str, Any], status: str) -> Dict[str, Any]:
    """Build a quality funnel breakdown that reframes filtering as positive quality control.

    Args:
        pipeline_name: Name of the pipeline
        counters: Parsed counters dict from job_run.counters_json
        status: Job status string (completed, failed, cancelled)

    Returns:
        Dict with total_discovered, new_added, updated, duplicates_caught, errors, filter_breakdown
    """
    if status == "failed":
        errors = 1 if counters.get("errors", 0) == 0 else counters["errors"]
        return {
            "total_discovered": 0,
            "new_added": 0,
            "updated": 0,
            "duplicates_caught": 0,
            "errors": errors,
            "filter_breakdown": [
                {"label": "Errors", "count": errors, "icon": "alert-triangle"},
            ],
        }

    pipeline = pipeline_name.lower()
    errors = counters.get("errors", 0)

    if pipeline == "lead_sourcing":
        inserted = counters.get("inserted", 0)
        updated = counters.get("updated", 0)
        skipped = counters.get("skipped", 0)
        total = inserted + updated + skipped + errors
        breakdown = []
        if skipped > 0:
            breakdown.append({"label": "Duplicates removed", "count": skipped, "icon": "shield"})
        if updated > 0:
            breakdown.append({"label": "Records updated", "count": updated, "icon": "refresh-cw"})
        if errors > 0:
            breakdown.append({"label": "Errors", "count": errors, "icon": "alert-triangle"})
        return {
            "total_discovered": total,
            "new_added": inserted,
            "updated": updated,
            "duplicates_caught": skipped,
            "errors": errors,
            "filter_breakdown": breakdown,
        }

    if pipeline == "contact_enrichment":
        contacts_found = counters.get("contacts_found", 0)
        contacts_reused = counters.get("contacts_reused", 0)
        skipped = counters.get("skipped", 0)
        total = contacts_found + contacts_reused + skipped + errors
        breakdown = []
        if contacts_reused > 0:
            breakdown.append({"label": "Reused from cache", "count": contacts_reused, "icon": "database"})
        if skipped > 0:
            breakdown.append({"label": "No results", "count": skipped, "icon": "search-x"})
        if errors > 0:
            breakdown.append({"label": "Errors", "count": errors, "icon": "alert-triangle"})
        return {
            "total_discovered": total,
            "new_added": contacts_found,
            "updated": contacts_reused,
            "duplicates_caught": skipped,
            "errors": errors,
            "filter_breakdown": breakdown,
        }

    if pipeline == "email_validation":
        valid = counters.get("valid", 0)
        invalid = counters.get("invalid", 0)
        catch_all = counters.get("catch_all", 0)
        unknown = counters.get("unknown", 0)
        validated = counters.get("validated", 0) or (valid + invalid + catch_all + unknown + errors)
        breakdown = []
        if invalid > 0:
            breakdown.append({"label": "Invalid emails", "count": invalid, "icon": "x-circle"})
        if catch_all > 0:
            breakdown.append({"label": "Catch-all domains", "count": catch_all, "icon": "help-circle"})
        if unknown > 0:
            breakdown.append({"label": "Unknown status", "count": unknown, "icon": "help-circle"})
        if errors > 0:
            breakdown.append({"label": "Errors", "count": errors, "icon": "alert-triangle"})
        return {
            "total_discovered": validated,
            "new_added": valid,
            "updated": 0,
            "duplicates_caught": invalid + catch_all + unknown,
            "errors": errors,
            "filter_breakdown": breakdown,
        }

    if pipeline in ("outreach_send", "outreach"):
        sent = counters.get("sent", 0)
        skipped = counters.get("skipped", 0)
        total = counters.get("total", 0) or (sent + skipped + errors)
        breakdown = []
        if skipped > 0:
            breakdown.append({"label": "Skipped (cooldown/limit)", "count": skipped, "icon": "clock"})
        if errors > 0:
            breakdown.append({"label": "Send errors", "count": errors, "icon": "alert-triangle"})
        return {
            "total_discovered": total,
            "new_added": sent,
            "updated": 0,
            "duplicates_caught": skipped,
            "errors": errors,
            "filter_breakdown": breakdown,
        }

    if pipeline == "outreach_mailmerge":
        exported = counters.get("exported", 0)
        skipped = counters.get("skipped", 0)
        total = counters.get("total", 0) or (exported + skipped)
        breakdown = []
        if skipped > 0:
            breakdown.append({"label": "Skipped (ineligible)", "count": skipped, "icon": "clock"})
        return {
            "total_discovered": total,
            "new_added": exported,
            "updated": 0,
            "duplicates_caught": skipped,
            "errors": 0,
            "filter_breakdown": breakdown,
        }

    # Unknown pipeline — empty funnel
    return {
        "total_discovered": 0,
        "new_added": 0,
        "updated": 0,
        "duplicates_caught": 0,
        "errors": 0,
        "filter_breakdown": [],
    }


# --- Builder Functions ---

def _build_run_metadata(job_run: JobRun) -> Dict[str, Any]:
    """Extract run metadata from a JobRun object."""
    status = job_run.status.value if isinstance(job_run.status, JobStatus) else str(job_run.status)
    duration: Optional[float] = None
    if job_run.started_at and job_run.ended_at:
        duration = round((job_run.ended_at - job_run.started_at).total_seconds(), 1)

    started_at = None
    if job_run.started_at:
        dt = job_run.started_at
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        started_at = dt.isoformat()

    ended_at = None
    if job_run.ended_at:
        dt = job_run.ended_at
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        ended_at = dt.isoformat()

    return {
        "run_id": job_run.run_id,
        "pipeline_name": job_run.pipeline_name,
        "pipeline_label": PIPELINE_LABELS.get(job_run.pipeline_name, job_run.pipeline_name.replace("_", " ").title()),
        "status": status,
        "triggered_by": job_run.triggered_by,
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_seconds": duration,
    }


def _build_source_breakdown(pipeline_name: str, counters: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Build per-source breakdown from enriched or legacy counters."""
    pipeline = pipeline_name.lower()
    breakdown: List[Dict[str, Any]] = []

    if pipeline == "lead_sourcing":
        # New format: per_source_detail
        psd = counters.get("per_source_detail")
        if psd and isinstance(psd, dict):
            for src, detail in psd.items():
                breakdown.append({
                    "source_name": src,
                    "source_label": ADAPTER_LABELS.get(src, src),
                    "status": "error" if detail.get("fetched", 0) == 0 and detail.get("new", 0) == 0 else "success",
                    "status_detail": None,
                    "total_retrieved": detail.get("fetched", 0),
                    "new_records": detail.get("new", 0),
                    # "excluded" = dropped by ICP gates (industry/size/staffing/...);
                    # fall back to the old "existing_in_db" key for pre-migration runs.
                    "excluded": detail.get("excluded", detail.get("existing_in_db", 0)),
                    "skipped": detail.get("skipped_dedup", 0),
                    "errors": 0,
                    "is_sub_source": False,
                    "parent_source": None,
                })

            # Add sub-source breakdown rows (LinkedIn, Indeed, Glassdoor, etc.)
            pssd = counters.get("per_sub_source_detail")
            if pssd and isinstance(pssd, dict) and len(pssd) > 1:
                # Sort sub-sources by fetched count descending for readability
                sorted_subs = sorted(pssd.items(), key=lambda x: x[1].get("fetched", 0), reverse=True)
                for sub_src, sub_detail in sorted_subs:
                    breakdown.append({
                        "source_name": f"sub:{sub_src}",
                        "source_label": SUB_SOURCE_LABELS.get(sub_src, sub_src.title()),
                        "status": "success" if sub_detail.get("fetched", 0) > 0 else "warning",
                        "status_detail": None,
                        "total_retrieved": sub_detail.get("fetched", 0),
                        "new_records": sub_detail.get("new", 0),
                        "excluded": sub_detail.get("excluded", sub_detail.get("existing_in_db", 0)),
                        "skipped": sub_detail.get("skipped_dedup", 0),
                        "errors": 0,
                        "is_sub_source": True,
                        "parent_source": "jsearch",
                    })
        else:
            # Legacy fallback: per_source / jobs_per_source
            per_source = counters.get("per_source") or counters.get("jobs_per_source") or {}
            for src, count in per_source.items():
                breakdown.append({
                    "source_name": src,
                    "source_label": ADAPTER_LABELS.get(src, src),
                    "status": "success" if count > 0 else "warning",
                    "status_detail": None,
                    "total_retrieved": count,
                    "new_records": 0,
                    "excluded": 0,
                    "skipped": 0,
                    "errors": 0,
                    "is_sub_source": False,
                    "parent_source": None,
                })

    elif pipeline == "contact_enrichment":
        astats = counters.get("adapter_stats")
        if astats and isinstance(astats, dict):
            for adapter_name, stats in astats.items():
                total_calls = stats.get("calls", 0)
                contacts_ret = stats.get("contacts_returned", 0)
                errs = stats.get("errors", 0)
                status = "success"
                if errs > 0:
                    status = "error"
                elif stats.get("no_results", 0) > total_calls * 0.5:
                    status = "warning"
                breakdown.append({
                    "source_name": adapter_name,
                    "source_label": ADAPTER_LABELS.get(adapter_name, adapter_name),
                    "status": status,
                    "status_detail": None,
                    "total_retrieved": contacts_ret,
                    "new_records": contacts_ret,
                    "existing_in_db": counters.get("contacts_reused", 0) if len(astats) == 1 else 0,
                    "skipped": stats.get("no_results", 0),
                    "errors": errs,
                })
        # If no adapter_stats, we don't have per-source data for contact enrichment

    elif pipeline == "email_validation":
        provider = counters.get("provider_used", "unknown")
        breakdown.append({
            "source_name": provider,
            "source_label": ADAPTER_LABELS.get(provider, provider),
            "status": "success" if counters.get("errors", 0) == 0 else "warning",
            "status_detail": None,
            "total_retrieved": counters.get("validated", 0),
            "new_records": counters.get("valid", 0),
            "existing_in_db": 0,
            "skipped": counters.get("invalid", 0) + counters.get("catch_all", 0) + counters.get("unknown", 0),
            "errors": counters.get("errors", 0),
        })

    elif pipeline in ("outreach_send", "outreach"):
        per_mbx = counters.get("per_mailbox")
        if per_mbx and isinstance(per_mbx, dict):
            for mbx_email, stats in per_mbx.items():
                breakdown.append({
                    "source_name": mbx_email,
                    "source_label": mbx_email,
                    "status": "success" if stats.get("errors", 0) == 0 else "warning",
                    "status_detail": None,
                    "total_retrieved": stats.get("sent", 0) + stats.get("errors", 0),
                    "new_records": stats.get("sent", 0),
                    "existing_in_db": 0,
                    "skipped": 0,
                    "errors": stats.get("errors", 0),
                })
        else:
            # Legacy single entry
            breakdown.append({
                "source_name": "smtp",
                "source_label": ADAPTER_LABELS.get("smtp", "SMTP"),
                "status": "success" if counters.get("errors", 0) == 0 else "warning",
                "status_detail": None,
                "total_retrieved": counters.get("sent", 0),
                "new_records": counters.get("sent", 0),
                "existing_in_db": 0,
                "skipped": counters.get("skipped", 0),
                "errors": counters.get("errors", 0),
            })

    elif pipeline == "outreach_mailmerge":
        breakdown.append({
            "source_name": "mailmerge",
            "source_label": ADAPTER_LABELS.get("mailmerge", "Mail Merge"),
            "status": "success",
            "status_detail": None,
            "total_retrieved": counters.get("exported", 0),
            "new_records": counters.get("exported", 0),
            "existing_in_db": 0,
            "skipped": counters.get("skipped", 0),
            "errors": 0,
        })

    # Check api_diagnostics for error status details and apply to breakdown
    api_diag = counters.get("api_diagnostics", [])
    diag_map = {}
    if isinstance(api_diag, list):
        for d in api_diag:
            if isinstance(d, dict):
                diag_map[d.get("adapter", "")] = d

    for entry in breakdown:
        diag = diag_map.get(entry["source_name"])
        if diag:
            if diag.get("status") == "error":
                entry["status"] = "error"
                entry["status_detail"] = diag.get("error_type")

    return breakdown


def _build_api_diagnostics(pipeline_name: str, counters: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Build API diagnostics from enriched or legacy counters."""
    diagnostics: List[Dict[str, Any]] = []

    # Try enriched api_diagnostics first
    raw_diag = counters.get("api_diagnostics")
    if raw_diag and isinstance(raw_diag, list):
        for d in raw_diag:
            if not isinstance(d, dict):
                continue
            adapter_name = d.get("adapter", "unknown")
            records = d.get("jobs_returned", d.get("contacts_returned", d.get("emails_checked", d.get("emails_sent", 0))))
            diagnostics.append({
                "adapter_name": adapter_name,
                "adapter_label": ADAPTER_LABELS.get(adapter_name, adapter_name),
                "status": d.get("status", "success"),
                "status_detail": d.get("error_type"),
                "error_message": d.get("error_message"),
                "records_returned": records or 0,
            })
        return diagnostics

    # Legacy fallback: derive minimal diagnostics from counters
    pipeline = pipeline_name.lower()
    errors = counters.get("errors", 0)

    if pipeline == "lead_sourcing":
        sources = counters.get("sources") or counters.get("sources_used") or []
        per_source = counters.get("per_source") or counters.get("jobs_per_source") or {}
        for src in sources:
            count = per_source.get(src, 0)
            diagnostics.append({
                "adapter_name": src,
                "adapter_label": ADAPTER_LABELS.get(src, src),
                "status": "success" if count > 0 else ("warning" if errors == 0 else "error"),
                "status_detail": None,
                "error_message": None,
                "records_returned": count,
            })

    elif pipeline == "contact_enrichment":
        # Use adapter_stats if present
        astats = counters.get("adapter_stats")
        if astats and isinstance(astats, dict):
            for aname, stats in astats.items():
                diagnostics.append({
                    "adapter_name": aname,
                    "adapter_label": ADAPTER_LABELS.get(aname, aname),
                    "status": "error" if stats.get("errors", 0) > 0 else "success",
                    "status_detail": None,
                    "error_message": None,
                    "records_returned": stats.get("contacts_returned", 0),
                })

    elif pipeline == "email_validation":
        provider = counters.get("provider_used", "unknown")
        diagnostics.append({
            "adapter_name": provider,
            "adapter_label": ADAPTER_LABELS.get(provider, provider),
            "status": "success" if errors == 0 else "warning",
            "status_detail": None,
            "error_message": None,
            "records_returned": counters.get("validated", 0),
        })

    elif pipeline in ("outreach_send", "outreach"):
        diagnostics.append({
            "adapter_name": "smtp",
            "adapter_label": ADAPTER_LABELS.get("smtp", "SMTP"),
            "status": "success" if errors == 0 else "warning",
            "status_detail": None,
            "error_message": None,
            "records_returned": counters.get("sent", 0),
        })

    elif pipeline == "outreach_mailmerge":
        diagnostics.append({
            "adapter_name": "mailmerge",
            "adapter_label": ADAPTER_LABELS.get("mailmerge", "Mail Merge"),
            "status": "success",
            "status_detail": None,
            "error_message": None,
            "records_returned": counters.get("exported", 0),
        })

    return diagnostics


def _build_ai_prompt(pipeline_name: str, counters: Dict[str, Any], score: int,
                     status: str, duration: Optional[float], error_message: Optional[str],
                     source_breakdown: List[Dict[str, Any]], api_diagnostics: List[Dict[str, Any]],
                     error_details: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, str]]:
    """Build the messages list for the AI adapter with mechanism knowledge."""
    # Filter counters to simple scalar values for metrics display
    metrics_lines = "\n".join(
        f"  {k}: {v}" for k, v in counters.items()
        if isinstance(v, (int, float, str)) and v and k not in ("per_source_detail", "api_diagnostics", "adapter_stats", "per_mailbox", "skip_reasons")
    )
    duration_str = f"{duration:.1f}s" if duration else "N/A"

    mechanism = PIPELINE_MECHANISM_KNOWLEDGE.get(pipeline_name.lower(), "")

    system_msg = (
        "You are a pipeline operations analyst for a cold email outreach platform.\n\n"
    )
    if mechanism:
        system_msg += f"PIPELINE MECHANISM:\n{mechanism}\n\n"
    system_msg += (
        "Analyze the results and provide insights. Because you understand the pipeline's mechanism, "
        "suggest specific improvements (e.g., enable additional sources, adjust filters, check API keys). "
        "Respond ONLY with valid JSON, no markdown fences, no extra text."
    )

    # Build sources summary
    sources_lines = ""
    if source_breakdown:
        parts = []
        for sb in source_breakdown:
            part = f"{sb['source_label']} ({sb['total_retrieved']} retrieved"
            if sb.get("new_records"):
                part += f", {sb['new_records']} new"
            if sb.get("existing_in_db"):
                part += f", {sb['existing_in_db']} existing"
            if sb.get("skipped"):
                part += f", {sb['skipped']} skipped"
            part += ")"
            parts.append(part)
        sources_lines = f"Sources Used: {'; '.join(parts)}\n"

    # Build API status summary
    api_status_lines = ""
    if api_diagnostics:
        parts = []
        for ad in api_diagnostics:
            part = f"{ad['adapter_label']}={ad['status']}"
            if ad.get("status_detail"):
                part += f" ({ad['status_detail']})"
            if ad.get("error_message"):
                part += f" [{ad['error_message'][:100]}]"
            parts.append(part)
        api_status_lines = f"API Status: {', '.join(parts)}\n"

    user_msg = (
        f"Pipeline: {pipeline_name.replace('_', ' ').title()}\n"
        f"Duration: {duration_str}, Score: {score}/100, Status: {status}\n"
        f"Metrics:\n{metrics_lines}\n"
    )
    if sources_lines:
        user_msg += sources_lines
    if api_status_lines:
        user_msg += api_status_lines
    if error_message:
        user_msg += f"Error: {error_message}\n"

    # Add error details for AI analysis
    if error_details:
        error_lines = []
        for ed in error_details:
            error_lines.append(f"  - {ed['adapter_label']}: {ed['error_type']} — {ed['message'][:100]}")
        user_msg += "Errors Encountered:\n" + "\n".join(error_lines) + "\n"

    if error_details:
        user_msg += (
            '\nRespond as JSON: {"summary": "2-3 sentence overview", '
            '"suggestions": ["actionable suggestion 1", ...], '
            '"highlights": ["positive highlight 1", ...], '
            '"error_analysis": [{"root_cause": "explanation", "proposed_solutions": ["fix 1", ...]}, ...]}'
        )
    else:
        user_msg += (
            '\nRespond as JSON: {"summary": "2-3 sentence overview", '
            '"suggestions": ["actionable suggestion 1", ...], '
            '"highlights": ["positive highlight 1", ...]}'
        )

    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]


def _fallback_summary(pipeline_name: str, counters: Dict[str, Any], score: int,
                      status: str, duration: Optional[float], error_message: Optional[str],
                      error_details: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Generate a template-based summary when no AI adapter is available."""
    name = pipeline_name.replace("_", " ").title()
    duration_str = f" in {duration:.1f}s" if duration else ""

    # Build summary sentence
    if status == "failed":
        summary = f"{name} failed{duration_str}."
        if error_message:
            summary += f" Error: {error_message[:200]}"
    elif status == "cancelled":
        summary = f"{name} was cancelled{duration_str}."
    else:
        parts = []
        for key in ("inserted", "updated", "skipped", "contacts_found", "leads_enriched",
                     "validated", "valid", "invalid", "sent", "exported"):
            val = counters.get(key, 0)
            if val:
                parts.append(f"{val} {key.replace('_', ' ')}")
        detail = ", ".join(parts) if parts else "no records processed"
        summary = f"{name} completed{duration_str}. Results: {detail}."

    # Build suggestions
    suggestions: List[str] = []
    errors = counters.get("errors", 0)
    total = sum(v for v in counters.values() if isinstance(v, (int, float)))

    if errors and total and (errors / max(total, 1)) > 0.1:
        suggestions.append("Error rate exceeds 10%. Check API key configuration and service availability.")
    if pipeline_name == "lead_sourcing" and counters.get("skipped", 0) > counters.get("inserted", 0):
        suggestions.append("High skip rate detected. Consider expanding search criteria or target industries.")
    if pipeline_name == "email_validation" and counters.get("invalid", 0) > counters.get("valid", 0):
        suggestions.append("More invalid than valid emails. Review contact discovery sources for data quality.")
    if pipeline_name in ("outreach_send", "outreach") and errors > 0:
        suggestions.append("Some emails failed to send. Check mailbox credentials and SMTP configuration.")
    if not suggestions and errors == 0:
        suggestions.append("Clean run with no issues detected.")

    # Build highlights
    highlights: List[str] = []
    if counters.get("inserted", 0) > 0:
        highlights.append(f"{counters['inserted']} new records added")
    if counters.get("contacts_found", 0) > 0:
        highlights.append(f"{counters['contacts_found']} contacts discovered")
    if counters.get("contacts_reused", 0) > 0:
        highlights.append(f"{counters['contacts_reused']} contacts reused from cache (API credits saved)")
    if counters.get("valid", 0) > 0:
        highlights.append(f"{counters['valid']} emails verified as valid")
    if counters.get("sent", 0) > 0:
        highlights.append(f"{counters['sent']} emails sent successfully")
    if counters.get("exported", 0) > 0:
        highlights.append(f"{counters['exported']} records exported for mail merge")
    if errors == 0 and total > 0:
        highlights.append("Zero errors during processing")

    # Fill error analysis with fallback templates
    if error_details:
        _fill_error_analysis_fallback(error_details)

    return {
        "summary": summary,
        "suggestions": suggestions,
        "highlights": highlights,
        "error_analysis": error_details or [],
    }


def generate_pipeline_summary(db: Session, job_run: JobRun) -> Dict[str, Any]:
    """Generate a complete enhanced summary report for a pipeline run.

    Uses AI for narrative/suggestions when available, falls back to templates.
    Success score is always deterministic. Now includes run_metadata,
    source_breakdown, and api_diagnostics.

    Args:
        db: Database session
        job_run: The JobRun instance to summarize

    Returns:
        Dict with success_score, summary, suggestions, highlights, generated_at, ai_generated,
        run_metadata, source_breakdown, api_diagnostics, counters
    """
    # Parse counters
    counters: Dict[str, Any] = {}
    if job_run.counters_json:
        try:
            counters = json.loads(job_run.counters_json)
        except (json.JSONDecodeError, TypeError):
            pass

    status = job_run.status.value if isinstance(job_run.status, JobStatus) else str(job_run.status)
    score = calculate_success_score(job_run.pipeline_name, counters, status)
    quality_funnel = build_quality_funnel(job_run.pipeline_name, counters, status)

    # Calculate duration
    duration: Optional[float] = None
    if job_run.started_at and job_run.ended_at:
        duration = round((job_run.ended_at - job_run.started_at).total_seconds(), 1)

    error_message = job_run.error_message

    # Build enhanced sections
    run_metadata = _build_run_metadata(job_run)
    source_breakdown = _build_source_breakdown(job_run.pipeline_name, counters)
    api_diagnostics = _build_api_diagnostics(job_run.pipeline_name, counters)

    # Build error details from diagnostics + error_message
    error_details = build_error_details(counters, error_message)

    # Try AI generation
    ai_generated = False
    narrative: Optional[Dict[str, Any]] = None

    try:
        from app.services.warmup.content_generator import get_ai_adapter
        adapter = get_ai_adapter(db)
        if adapter:
            messages = _build_ai_prompt(
                job_run.pipeline_name, counters, score, status, duration, error_message,
                source_breakdown, api_diagnostics, error_details
            )
            max_tokens = 700 if error_details else 500
            raw = adapter._call_api(messages, temperature=0.4, max_tokens=max_tokens)

            # Strip markdown fences if present
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
                cleaned = cleaned.strip()

            narrative = json.loads(cleaned)
            ai_generated = True
    except Exception as e:
        logger.warning(f"AI summary generation failed, using fallback: {e}")

    if not narrative:
        narrative = _fallback_summary(job_run.pipeline_name, counters, score, status, duration, error_message, error_details)

    # Merge AI error_analysis back into error_details (by index), fill gaps with fallback
    if ai_generated and error_details:
        ai_error_analysis = narrative.get("error_analysis", [])
        for i, entry in enumerate(error_details):
            if i < len(ai_error_analysis) and isinstance(ai_error_analysis[i], dict):
                ai_ea = ai_error_analysis[i]
                if ai_ea.get("root_cause"):
                    entry["root_cause"] = ai_ea["root_cause"]
                if ai_ea.get("proposed_solutions"):
                    entry["proposed_solutions"] = ai_ea["proposed_solutions"]
            # Fill any remaining gaps with fallback
            if not entry["root_cause"] or not entry["proposed_solutions"]:
                _fill_error_analysis_fallback([entry])

    # Build flat counters for response (only simple scalar values)
    flat_counters = {k: v for k, v in counters.items() if isinstance(v, (int, float, str, bool))}

    return {
        # Existing fields (preserved for backward compat)
        "success_score": score,
        "summary": narrative.get("summary", ""),
        "suggestions": narrative.get("suggestions", []),
        "highlights": narrative.get("highlights", []),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ai_generated": ai_generated,
        # Enhanced sections
        "run_metadata": run_metadata,
        "source_breakdown": source_breakdown,
        "api_diagnostics": api_diagnostics,
        "counters": flat_counters,
        # Quality funnel (replaces success_score in UI)
        "quality_funnel": quality_funnel,
        # Error analysis
        "error_analysis": error_details,
    }
