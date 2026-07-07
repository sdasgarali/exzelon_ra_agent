"""Company enrichment service.

Multi-tier enrichment strategy:
1. Aggregate from leads (free, always) — website/linkedin from lead data, most common state
2. LLM research (uses configured AI adapter) — fills remaining gaps via AI knowledge
3. OpenCorporates (free 500/month) — if configured
4. Clearbit (paid) — if configured

Only fills missing fields (never overwrites existing data).
"""
import structlog
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session

from app.db.models.client import ClientInfo
from app.db.models.lead import LeadDetails
from app.core.config import settings
from app.core.settings_resolver import get_tenant_setting

logger = structlog.get_logger()


def _extract_domain(url: str) -> str:
    """Extract domain from URL."""
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


def enrich_from_leads(db: Session, client: ClientInfo) -> dict:
    """Tier 1: Aggregate enrichment data from lead_details for this company.

    Returns dict of fields that were updated.
    """
    updated = {}
    leads = db.query(LeadDetails).filter(
        LeadDetails.client_name == client.client_name,
        LeadDetails.is_archived == False
    ).all()

    if not leads:
        return updated

    # Website from employer_website
    if not client.website:
        for lead in leads:
            if lead.employer_website:
                client.website = lead.employer_website
                updated["website"] = lead.employer_website
                break

    # LinkedIn from employer_linkedin_url
    if not client.linkedin_url:
        for lead in leads:
            if lead.employer_linkedin_url:
                client.linkedin_url = lead.employer_linkedin_url
                updated["linkedin_url"] = lead.employer_linkedin_url
                break

    # Domain from website
    if not client.domain and client.website:
        client.domain = _extract_domain(client.website)
        if client.domain:
            updated["domain"] = client.domain

    # Most common state -> location_state
    if not client.location_state:
        state_counts = {}
        for lead in leads:
            if lead.state:
                state_counts[lead.state] = state_counts.get(lead.state, 0) + 1
        if state_counts:
            best_state = max(state_counts, key=state_counts.get)
            client.location_state = best_state
            updated["location_state"] = best_state

    if updated:
        sources = [client.enrichment_source] if client.enrichment_source else []
        if "leads" not in sources:
            sources.append("leads")
        client.enrichment_source = ", ".join(sources)
        client.enriched_at = datetime.utcnow()

    return updated


# Providers billed per-token. Used by ``free_only`` callers that must never
# incur AI spend (e.g. resolving unknowns purely to AVOID a paid contact API).
PAID_AI_PROVIDERS = {"openai", "anthropic", "gemini"}


def _get_ai_adapter(
    db: Session, tenant_id: Optional[int] = None, force_provider: Optional[str] = None
):
    """Load an AI adapter from settings.

    ``force_provider`` overrides the tenant's configured provider — used to pin
    the free Groq provider when the caller must not incur AI spend.
    """
    provider = force_provider or get_tenant_setting(
        db, "warmup_ai_provider", tenant_id=tenant_id, default="groq"
    )
    api_key_map = {
        "groq": "groq_api_key",
        "openai": "openai_api_key",
        "anthropic": "anthropic_api_key",
        "gemini": "gemini_api_key",
    }
    api_key = get_tenant_setting(db, api_key_map.get(provider, "groq_api_key"), tenant_id=tenant_id, default="")
    if not api_key:
        return None
    try:
        adapter = None
        if provider == "groq":
            from app.services.adapters.ai.groq import GroqAdapter
            adapter = GroqAdapter(api_key=api_key)
        elif provider == "openai":
            from app.services.adapters.ai.openai_adapter import OpenAIAdapter
            adapter = OpenAIAdapter(api_key=api_key)
        elif provider == "anthropic":
            from app.services.adapters.ai.anthropic_adapter import AnthropicAdapter
            adapter = AnthropicAdapter(api_key=api_key)
        elif provider == "gemini":
            from app.services.adapters.ai.gemini import GeminiAdapter
            adapter = GeminiAdapter(api_key=api_key)
        if adapter is not None:
            adapter._cost_db = db
            adapter._cost_tenant_id = tenant_id
            adapter._cost_feature = "company_enrichment"
        return adapter
    except Exception:
        pass
    return None


# Fields that LLM can fill, mapped to max lengths for string columns
_LLM_FIELD_LIMITS = {
    "website": 500,
    "linkedin_url": 500,
    "industry": 100,
    "description": 2000,
    "company_size": 50,
    "headquarters": 255,
    "founded_year": None,  # int
    "employee_count": None,  # int
}


def enrich_from_llm(db: Session, client: ClientInfo, tenant_id: Optional[int] = None) -> dict:
    """Tier 2: Use configured AI adapter to research missing company fields.

    Only fills null fields, never overwrites existing data.
    Returns dict of fields that were updated.
    """
    # Check which fields are still missing
    missing = []
    for field in _LLM_FIELD_LIMITS:
        if getattr(client, field, None) is None:
            missing.append(field)

    if not missing:
        return {}

    adapter = _get_ai_adapter(db, tenant_id=tenant_id)
    if not adapter:
        logger.debug("llm_enrich_skipped", reason="no_ai_adapter_configured")
        return {}

    try:
        data = adapter.research_company(
            company_name=client.client_name,
            domain=client.domain,
            location=client.location_state,
        )
    except Exception as exc:
        logger.warning("llm_enrich_failed", client=client.client_name, error=str(exc))
        return {}

    if not data or not isinstance(data, dict):
        return {}

    updated = {}
    for field in missing:
        val = data.get(field)
        if val is None:
            continue

        limit = _LLM_FIELD_LIMITS[field]
        if limit is not None:
            # String field — validate type and truncate
            if not isinstance(val, str):
                val = str(val)
            val = val[:limit]
        else:
            # Integer field — validate type
            if not isinstance(val, int):
                try:
                    val = int(val)
                except (ValueError, TypeError):
                    continue

        setattr(client, field, val)
        updated[field] = val

    if updated:
        sources = [client.enrichment_source] if client.enrichment_source else []
        if "llm" not in sources:
            sources.append("llm")
        client.enrichment_source = ", ".join(sources)
        client.enriched_at = datetime.utcnow()
        logger.info("llm_enrich_success", client=client.client_name, fields=list(updated.keys()))

    return updated


def enrich_client(db: Session, client: ClientInfo, tenant_id: Optional[int] = None) -> dict:
    """Run all enrichment tiers for a single client.

    Returns summary of what was enriched.
    """
    result = {"client_id": client.client_id, "client_name": client.client_name, "fields_updated": []}

    # Increment enrichment attempt counter
    client.enrich_attempts = (client.enrich_attempts or 0) + 1

    # Tier 1: Aggregate from leads (always free)
    lead_updates = enrich_from_leads(db, client)
    if lead_updates:
        result["fields_updated"].extend(list(lead_updates.keys()))

    # Tier 2: LLM research (uses configured AI adapter)
    llm_updates = enrich_from_llm(db, client, tenant_id=tenant_id)
    if llm_updates:
        result["fields_updated"].extend(list(llm_updates.keys()))

    return result


def resolve_company_metadata_batch(
    db: Session,
    companies,
    tenant_id: Optional[int] = None,
    max_llm_calls: int = 300,
    use_llm: bool = True,
    free_only: bool = False,
) -> dict:
    """Resolve {industry, company_size, employee_count} for many companies.

    Used by the lead-sourcing size/industry gate to fill attributes for sources
    that don't return them. Strategy per company:
      1. Cache — read from an existing ClientInfo row (free, no API).
      2. LLM — the configured AI adapter's ``research_company`` (Groq), bounded
         to ``max_llm_calls`` per run and run in a thread pool.

    Args:
        companies: iterable of ``(client_name, domain)`` tuples (domain optional).
        max_llm_calls: hard ceiling on AI lookups this run (cost/latency guard).
        use_llm: when False, only the ClientInfo cache is consulted.
        free_only: pin the free Groq provider; if no Groq key, degrade to
            cache-only instead of using a paid provider (never incur AI spend).

    Returns:
        dict keyed by ``client_name.strip().lower()`` →
        ``{"industry", "company_size", "employee_count"}`` (values may be None).
        Threads never touch the DB session — all DB reads happen up front.
    """
    result: dict = {}

    # Dedupe by lowercased name; keep the first non-empty domain seen.
    unique: dict = {}
    for name, domain in companies:
        key = (name or "").strip().lower()
        if not key:
            continue
        if key not in unique:
            unique[key] = {"name": (name or "").strip(), "domain": (domain or "").strip()}
        elif domain and not unique[key]["domain"]:
            unique[key]["domain"] = (domain or "").strip()

    if not unique:
        return result

    # 1) Cache from ClientInfo (case-insensitive on exact stored name).
    cached: dict = {}
    names = [v["name"] for v in unique.values()]
    if names:
        q = db.query(
            ClientInfo.client_name,
            ClientInfo.industry,
            ClientInfo.company_size,
            ClientInfo.employee_count,
            ClientInfo.website,
        ).filter(ClientInfo.client_name.in_(names))
        if tenant_id is not None:
            q = q.filter(ClientInfo.tenant_id == tenant_id)
        for cn, ind, size, emp, web in q.all():
            cached[cn.strip().lower()] = {
                "industry": ind, "company_size": size, "employee_count": emp, "website": web,
            }

    to_enrich = []
    for key, info in unique.items():
        c = cached.get(key)
        result[key] = {
            "industry": (c or {}).get("industry"),
            "company_size": (c or {}).get("company_size"),
            "employee_count": (c or {}).get("employee_count"),
        }
        # Fully cached (industry + a size signal) → no LLM needed.
        if c and c.get("industry") and (c.get("employee_count") or c.get("company_size")):
            continue
        to_enrich.append((key, info, c))

    # 1b) Firmographic provider (Apollo) — authoritative company SIZE by domain.
    # The LLM step below fills industry for recognizable names but rarely a real
    # headcount; a data provider does. Runs ONLY when the caller allows paid
    # lookups (never under free_only, which the pre-enrichment gate uses to avoid
    # spend) and only for companies that carry a domain (Apollo needs one).
    if to_enrich and not free_only:
        from app.services.company_firmographics import (
            enrich_firmographics_batch,
            get_firmographic_provider,
        )
        if get_firmographic_provider(db, tenant_id=tenant_id) == "apollo":
            max_firmo = int(get_tenant_setting(
                db, "company_firmographic_max_lookups",
                tenant_id=tenant_id, default=settings.COMPANY_FIRMOGRAPHIC_MAX_LOOKUPS,
            ))
            firmo_items = [
                (info["name"], info["domain"] or _extract_domain((c or {}).get("website") or ""))
                for (key, info, c) in to_enrich
            ]
            firmo = enrich_firmographics_batch(
                db, firmo_items, tenant_id=tenant_id, max_lookups=max_firmo,
            )
            if firmo:
                remaining = []
                for (key, info, c) in to_enrich:
                    m = firmo.get(key)
                    if m:
                        r = result.get(key, {})
                        if not r.get("industry") and m.get("industry"):
                            r["industry"] = str(m["industry"])[:100]
                        if not r.get("employee_count") and m.get("employee_count") is not None:
                            r["employee_count"] = m["employee_count"]
                        if not r.get("company_size") and m.get("company_size"):
                            r["company_size"] = str(m["company_size"])[:50]
                        result[key] = r
                    rr = result.get(key, {})
                    # Still needs the LLM only if industry or a size signal is missing.
                    if not (rr.get("industry") and (rr.get("employee_count") or rr.get("company_size"))):
                        remaining.append((key, info, c))
                to_enrich = remaining

    if not use_llm or max_llm_calls <= 0 or not to_enrich:
        return result

    # free_only pins Groq (free tier). If no Groq key is configured we fall back
    # to cache-only rather than silently using a paid provider — the caller uses
    # this path specifically to avoid AI spend.
    adapter = _get_ai_adapter(
        db, tenant_id=tenant_id, force_provider="groq" if free_only else None
    )
    if not adapter:
        return result
    # Threads must not write to the DB session; disable per-call cost DB writes.
    adapter._cost_db = None

    to_enrich = to_enrich[:max_llm_calls]

    def _research(item):
        key, info, c = item
        domain = info["domain"] or _extract_domain((c or {}).get("website") or "")
        try:
            data = adapter.research_company(company_name=info["name"], domain=domain, location=None)
        except Exception:
            return key, None
        return key, data if isinstance(data, dict) else None

    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=6) as ex:
        for key, data in ex.map(_research, to_enrich):
            if not data:
                continue
            merged = result.get(key, {})
            if not merged.get("industry") and data.get("industry"):
                merged["industry"] = str(data["industry"])[:100]
            if not merged.get("company_size") and data.get("company_size"):
                merged["company_size"] = str(data["company_size"])[:50]
            if not merged.get("employee_count") and data.get("employee_count") is not None:
                try:
                    merged["employee_count"] = int(data["employee_count"])
                except (ValueError, TypeError):
                    pass
            result[key] = merged

    return result


def bulk_enrich_clients(db: Session, client_ids: list[int], tenant_id: Optional[int] = None) -> dict:
    """Enrich multiple clients."""
    results = []
    enriched = 0
    skipped = 0

    for cid in client_ids:
        client = db.query(ClientInfo).filter(ClientInfo.client_id == cid).first()
        if not client:
            results.append({"client_id": cid, "error": "Not found"})
            skipped += 1
            continue

        r = enrich_client(db, client, tenant_id=tenant_id)
        results.append(r)
        if r["fields_updated"]:
            enriched += 1
        else:
            skipped += 1

    db.commit()

    return {
        "total": len(client_ids),
        "enriched": enriched,
        "skipped": skipped,
        "results": results,
    }
