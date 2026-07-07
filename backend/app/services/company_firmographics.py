"""Firmographic enrichment — fill company industry / size / employee_count from a
data provider (Apollo), keyed by DOMAIN.

Why a dedicated module
----------------------
The free Groq resolver (``company_enrichment.resolve_company_metadata_batch``)
fills *industry* for recognizable company names but cannot reliably determine
company *size*. Apollo's ``/organizations/enrich`` returns authoritative employee
counts — but ONLY by domain (name-only lookups return nothing; verified live).

So a domain is a hard prerequisite for firmographic size. This module is the
single source of truth for domain-keyed firmographic lookups, reused by:
  - the sourcing resolver (``resolve_company_metadata_batch``), and
  - the one-time backfill script (``scripts/backfill_company_size.py``).

Cost discipline
---------------
Apollo org-enrich is billed per credit. Every entry point is bounded by an
explicit ``max_lookups`` and cost-tracked. The provider is OFF by default
(``company_firmographic_provider = "none"``) and is NEVER invoked on the
free-only pre-enrichment gate path (which must not incur paid spend).
"""
from __future__ import annotations

from typing import Iterable, Optional, Tuple

import httpx
import structlog
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.settings_resolver import get_tenant_setting

logger = structlog.get_logger()

_APOLLO_ORG_ENRICH_URL = "https://api.apollo.io/api/v1/organizations/enrich"


def employee_count_to_size(count: int) -> str:
    """Bucket an employee count into the app's standard size-range string."""
    if count <= 50:
        return "1-50"
    if count <= 200:
        return "51-200"
    if count <= 500:
        return "201-500"
    if count <= 1000:
        return "501-1000"
    if count <= 5000:
        return "1001-5000"
    return "5000+"


def get_firmographic_provider(db: Session, tenant_id: Optional[int] = None) -> str:
    """Configured firmographic provider name, lower-cased ("none" when disabled)."""
    val = get_tenant_setting(
        db, "company_firmographic_provider",
        tenant_id=tenant_id, default=settings.COMPANY_FIRMOGRAPHIC_PROVIDER,
    )
    return str(val or "none").strip().lower()


def _get_apollo_key(db: Session, tenant_id: Optional[int] = None) -> str:
    key = get_tenant_setting(db, "apollo_api_key", tenant_id=tenant_id, default="")
    return key or getattr(settings, "APOLLO_API_KEY", "") or ""


def apollo_enrich_by_domain(http: httpx.Client, api_key: str, domain: str) -> Optional[dict]:
    """Look up one company by domain via Apollo /organizations/enrich.

    Returns ``{industry, employee_count, company_size, website, linkedin_url}``
    (values may be None) or ``None`` when the company is unknown / on error.
    Never raises — firmographic enrichment is best-effort.
    """
    if not domain or not api_key:
        return None
    try:
        resp = http.post(
            _APOLLO_ORG_ENRICH_URL,
            params={"domain": domain},
            headers={"X-Api-Key": api_key, "Accept": "application/json"},
            timeout=15,
        )
    except Exception as e:  # network / timeout — best-effort
        logger.warning("apollo_org_enrich_error", domain=domain, error=str(e))
        return None
    if resp.status_code != 200:
        # 404 = unknown company (expected, quiet); other codes are worth a warning.
        if resp.status_code != 404:
            logger.warning("apollo_org_enrich_http", domain=domain, status=resp.status_code)
        return None
    try:
        org = (resp.json() or {}).get("organization") or {}
    except Exception:
        return None
    if not org:
        return None
    emp = org.get("estimated_num_employees")
    emp_int = int(emp) if isinstance(emp, (int, float)) else None
    return {
        "industry": org.get("industry"),
        "employee_count": emp_int,
        "company_size": employee_count_to_size(emp_int) if emp_int else None,
        "website": org.get("website_url"),
        "linkedin_url": org.get("linkedin_url"),
    }


def enrich_firmographics_batch(
    db: Session,
    items: Iterable[Tuple[Optional[str], Optional[str]]],
    tenant_id: Optional[int] = None,
    max_lookups: int = 100,
    run_id: Optional[int] = None,
) -> dict:
    """Resolve firmographics for many companies via the configured provider.

    Args:
        items: iterable of ``(company_name, domain)``. Only entries WITH a domain
            are looked up — Apollo cannot resolve by name (verified). Domain-less
            companies are silently skipped (caller falls back to the LLM / a
            separate domain-backfill).
        max_lookups: hard ceiling on provider calls this batch (cost guard).
        run_id: optional job-run id for cost attribution.

    Returns:
        dict keyed by ``company_name.strip().lower()`` → the ``apollo_enrich_by_domain``
        payload. Empty dict when the provider is disabled / unkeyed (a no-op).
    """
    if get_firmographic_provider(db, tenant_id=tenant_id) != "apollo":
        return {}
    api_key = _get_apollo_key(db, tenant_id=tenant_id)
    if not api_key:
        logger.info("firmographic_skip_no_key", provider="apollo")
        return {}

    # Dedupe by name; keep the first domain seen. Drop domain-less entries.
    by_name: dict = {}
    for name, domain in items:
        key = (name or "").strip().lower()
        dom = (domain or "").strip()
        if not key or not dom:
            continue
        by_name.setdefault(key, dom)
    if not by_name:
        return {}

    out: dict = {}
    calls = 0
    with httpx.Client() as http:
        for key, dom in by_name.items():
            if calls >= max_lookups:
                logger.info(
                    "firmographic_cap_reached",
                    cap=max_lookups, skipped=len(by_name) - calls,
                )
                break
            org = apollo_enrich_by_domain(http, api_key, dom)
            calls += 1
            if org:
                out[key] = org

    if calls:
        try:
            from app.services.cost_tracker import record_pipeline_cost
            record_pipeline_cost(
                db, source="apollo_firmographic", api_calls=calls, results=len(out),
                run_id=run_id, category="firmographic", tenant_id=tenant_id,
            )
        except Exception:  # cost recording must never break enrichment
            logger.debug("firmographic_cost_record_failed", exc_info=True)

    logger.info("firmographic_batch_done", looked_up=calls, resolved=len(out))
    return out
