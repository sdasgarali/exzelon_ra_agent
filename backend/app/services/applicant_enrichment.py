"""Applicant-count enrichment for sourced jobs (scrape-based).

No job-board API returns applicant counts, so for the pages that DO show one —
LinkedIn and Indeed job pages — we scrape via Firecrawl and parse the number.
This is paid + slow, so it is:
  * OFF by default and gated on a Firecrawl API key,
  * targeted (only linkedin.com / indeed.com job URLs),
  * bounded per run (``max_lookups``),
  * recall-preserving (any miss keeps the lead),
  * cost-tracked.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import structlog

from app.services.applicant_parser import parse_applicant_count
from app.services.firecrawl_client import scrape_markdown

logger = structlog.get_logger()

# Only these hosts publicly surface an applicant/clicked-apply count.
_SCRAPABLE_HOSTS = ("linkedin.com", "indeed.com")


def _is_scrapable(url: Optional[str]) -> bool:
    if not url:
        return False
    try:
        host = (urlparse(url).hostname or "").lower()
    except (ValueError, AttributeError):
        return False
    return any(host == h or host.endswith("." + h) for h in _SCRAPABLE_HOSTS)


def resolve_applicant_counts(
    db,
    jobs: List[Dict[str, Any]],
    api_key: str,
    max_lookups: int = 50,
    timeout: int = 20,
    tenant_id: Optional[int] = None,
    run_id: Optional[int] = None,
) -> Dict[int, int]:
    """Scrape + parse applicant counts for eligible jobs.

    Returns ``{id(job): applicant_count}`` for every job we could resolve a count
    for. Jobs without a scrapable URL, beyond the lookup budget, or with no
    parseable count are simply absent from the result (→ never dropped).
    """
    if not api_key or not jobs or max_lookups <= 0:
        return {}

    results: Dict[int, int] = {}
    scrapes = 0
    for job in jobs:
        if scrapes >= max_lookups:
            logger.info("Applicant scrape cap reached", cap=max_lookups)
            break
        url = job.get("job_link") or ""
        if not _is_scrapable(url):
            continue
        scrapes += 1
        md = scrape_markdown(url, api_key, timeout=timeout)
        if not md:
            continue
        count = parse_applicant_count(md)
        if count is not None:
            results[id(job)] = count

    if scrapes:
        # Best-effort cost tracking (firecrawl not in the cost config → 0.0, still logs volume).
        try:
            from app.services.cost_tracker import record_pipeline_cost
            record_pipeline_cost(
                db, source="firecrawl", api_calls=scrapes, results=len(results),
                run_id=run_id, category="lead_sourcing", tenant_id=tenant_id,
            )
        except Exception as e:  # never fail sourcing on cost bookkeeping
            logger.warning("Firecrawl cost tracking failed", error=str(e))

    logger.info("Applicant enrichment complete", scrapes=scrapes, resolved=len(results))
    return results
