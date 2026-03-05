"""Pipeline run summary generation with deterministic scoring and optional AI narratives."""
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from sqlalchemy.orm import Session

from app.db.models.job_run import JobRun, JobStatus

logger = logging.getLogger(__name__)


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


def _build_ai_prompt(pipeline_name: str, counters: Dict[str, Any], score: int,
                     status: str, duration: Optional[float], error_message: Optional[str]) -> List[Dict[str, str]]:
    """Build the messages list for the AI adapter."""
    metrics_lines = "\n".join(f"  {k}: {v}" for k, v in counters.items() if v)
    duration_str = f"{duration:.1f}s" if duration else "N/A"

    system_msg = (
        "You are a pipeline operations analyst for a cold email outreach platform. "
        "Analyze the pipeline run results and provide insights. "
        "Respond ONLY with valid JSON, no markdown fences, no extra text."
    )

    user_msg = (
        f"Pipeline: {pipeline_name.replace('_', ' ').title()}\n"
        f"Duration: {duration_str}\n"
        f"Score: {score}/100\n"
        f"Status: {status}\n"
        f"Metrics:\n{metrics_lines}\n"
    )
    if error_message:
        user_msg += f"Error: {error_message}\n"

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
                      status: str, duration: Optional[float], error_message: Optional[str]) -> Dict[str, Any]:
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

    if score < 60:
        suggestions.append(f"Score is low ({score}/100). Review the pipeline configuration and input data quality.")
    if errors and total and (errors / max(total, 1)) > 0.1:
        suggestions.append("Error rate exceeds 10%. Check API key configuration and service availability.")
    if pipeline_name == "lead_sourcing" and counters.get("skipped", 0) > counters.get("inserted", 0):
        suggestions.append("High skip rate detected. Consider expanding search criteria or target industries.")
    if pipeline_name == "email_validation" and counters.get("invalid", 0) > counters.get("valid", 0):
        suggestions.append("More invalid than valid emails. Review contact discovery sources for data quality.")
    if not suggestions and score == 100:
        suggestions.append("Perfect score. No improvements needed for this run.")

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

    return {
        "summary": summary,
        "suggestions": suggestions,
        "highlights": highlights,
    }


def generate_pipeline_summary(db: Session, job_run: JobRun) -> Dict[str, Any]:
    """Generate a complete summary report for a pipeline run.

    Uses AI for narrative/suggestions when available, falls back to templates.
    Success score is always deterministic.

    Args:
        db: Database session
        job_run: The JobRun instance to summarize

    Returns:
        Dict with success_score, summary, suggestions, highlights, generated_at, ai_generated
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

    # Calculate duration
    duration: Optional[float] = None
    if job_run.started_at and job_run.ended_at:
        duration = round((job_run.ended_at - job_run.started_at).total_seconds(), 1)

    error_message = job_run.error_message

    # Try AI generation
    ai_generated = False
    narrative: Optional[Dict[str, Any]] = None

    try:
        from app.services.warmup.content_generator import get_ai_adapter
        adapter = get_ai_adapter(db)
        if adapter:
            messages = _build_ai_prompt(job_run.pipeline_name, counters, score, status, duration, error_message)
            raw = adapter._call_api(messages, temperature=0.4, max_tokens=500)

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
        narrative = _fallback_summary(job_run.pipeline_name, counters, score, status, duration, error_message)

    return {
        "success_score": score,
        "summary": narrative.get("summary", ""),
        "suggestions": narrative.get("suggestions", []),
        "highlights": narrative.get("highlights", []),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ai_generated": ai_generated,
    }
