"""Company enrichment service.

Multi-tier enrichment strategy:
1. Aggregate from leads (free, always) — website/linkedin from lead data, most common state
2. LLM research (uses configured AI adapter) — fills remaining gaps via AI knowledge
3. OpenCorporates (free 500/month) — if configured
4. Clearbit (paid) — if configured

Only fills missing fields (never overwrites existing data).
"""
import structlog
from datetime import datetime, timedelta
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
    lq = db.query(LeadDetails).filter(
        LeadDetails.client_name == client.client_name,
        LeadDetails.is_archived == False
    )
    if client.tenant_id is not None:
        # Only this tenant's leads may feed this tenant's company record.
        lq = lq.filter(LeadDetails.tenant_id == client.tenant_id)
    leads = lq.all()

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


#: How long a company's research result is trusted before an automated path may
#: pay to research it again. Fields like ``description`` / ``founded_year`` are
#: often permanently unknown; without this, every run re-bought the same lookup.
RESEARCH_TTL_DAYS = 30

#: The fields automated callers actually need. Optional fields (description,
#: founded_year, headquarters, linkedin_url) alone never justify a repeat lookup.
_ESSENTIAL_LLM_FIELDS = ("website", "industry", "company_size", "employee_count")

#: Marker in ``enrichment_source`` meaning "an LLM research call has run".
_LLM_SOURCE = "llm"


def _sources_of(client: ClientInfo) -> list:
    return [s.strip() for s in (client.enrichment_source or "").split(",") if s.strip()]


def _add_source(client: ClientInfo, label: str) -> None:
    sources = _sources_of(client)
    if label not in sources:
        sources.append(label)
    client.enrichment_source = ", ".join(sources)[:100]


def _recently_researched(enriched_at, attempts) -> bool:
    if not enriched_at or not (attempts or 0):
        return False
    return enriched_at >= datetime.utcnow() - timedelta(days=RESEARCH_TTL_DAYS)


def _meter_research(db: Session, tenant_id: Optional[int], calls: int, reference: str) -> None:
    """Bill completed company-research calls as ``firmographic_lookup``.

    Only calls that actually ran are billed — never cache hits. ``tenant_id=None``
    (super-admin / internal) is not metered, same rule as everywhere else.
    """
    if calls <= 0 or tenant_id is None:
        return
    try:
        from app.services.credit_metering import meter
        meter(db, tenant_id, "firmographic_lookup", calls, reference_id=reference,
              description="Company research (AI)")
    except Exception as e:  # metering must never break enrichment
        logger.warning("company_research_meter_failed", error=str(e))


def enrich_from_llm(db: Session, client: ClientInfo, tenant_id: Optional[int] = None) -> dict:
    """Tier 2: Use configured AI adapter to research missing company fields.

    Only fills null fields, never overwrites existing data.
    Returns dict of fields that were updated.

    Each research call that runs is metered (``firmographic_lookup``). A company
    that has already been researched is not re-bought just because optional fields
    stayed null: it is researched again only when an essential field is missing
    AND the last research is older than ``RESEARCH_TTL_DAYS``.
    """
    # Check which fields are still missing
    missing = []
    for field in _LLM_FIELD_LIMITS:
        if getattr(client, field, None) is None:
            missing.append(field)

    if not missing:
        return {}

    if _LLM_SOURCE in _sources_of(client):
        essential_missing = [
            f for f in missing
            if f in _ESSENTIAL_LLM_FIELDS
            # a size signal is either field
            and not (f in ("company_size", "employee_count")
                     and (client.company_size or client.employee_count))
        ]
        if not essential_missing:
            logger.debug("llm_enrich_skipped", client=client.client_name,
                         reason="only_optional_fields_missing")
            return {}
        if client.enriched_at and client.enriched_at >= datetime.utcnow() - timedelta(days=RESEARCH_TTL_DAYS):
            logger.debug("llm_enrich_skipped", client=client.client_name,
                         reason="researched_recently")
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

    # The call ran: bill it, and record that this company has been researched so
    # the next run does not buy the same answer again.
    _meter_research(db, tenant_id, 1, reference=f"client:{client.client_id}")
    _add_source(client, _LLM_SOURCE)
    client.enriched_at = datetime.utcnow()

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
            ClientInfo.enriched_at,
            ClientInfo.enrich_attempts,
        ).filter(ClientInfo.client_name.in_(names))
        if tenant_id is not None:
            q = q.filter(ClientInfo.tenant_id == tenant_id)
        for cn, ind, size, emp, web, enr_at, attempts in q.all():
            cached[cn.strip().lower()] = {
                "industry": ind, "company_size": size, "employee_count": emp, "website": web,
                "recent": _recently_researched(enr_at, attempts),
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
        # Researched within the TTL and still incomplete: the answer is "unknown",
        # and paying again would buy the same answer. (Also covers companies the
        # gate dropped last run, whose results are persisted below.)
        if c and c.get("recent"):
            continue
        to_enrich.append((key, info, c))

    # Companies whose lookups actually ran this call → persisted below, so the
    # next run reads them from the cache instead of paying again.
    researched: dict = {}  # key -> source label

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
                        researched[key] = "firmographic"
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
        _persist_researched(db, tenant_id, unique, researched, result)
        return result

    # free_only pins Groq (free tier). If no Groq key is configured we fall back
    # to cache-only rather than silently using a paid provider — the caller uses
    # this path specifically to avoid AI spend.
    adapter = _get_ai_adapter(
        db, tenant_id=tenant_id, force_provider="groq" if free_only else None
    )
    if not adapter:
        _persist_researched(db, tenant_id, unique, researched, result)
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
            return key, None, False
        return key, (data if isinstance(data, dict) else None), True

    from concurrent.futures import ThreadPoolExecutor

    llm_calls = 0
    with ThreadPoolExecutor(max_workers=6) as ex:
        for key, data, ran in ex.map(_research, to_enrich):
            if ran:
                llm_calls += 1
                researched.setdefault(key, _LLM_SOURCE)
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

    # Bill every research call that ran (main thread — workers never touch the
    # session). The free_only path is the internal pre-enrichment gate, which
    # exists to SAVE the tenant a paid contact lookup and is pinned to the free
    # provider, so it is not billed.
    if not free_only:
        _meter_research(db, tenant_id, llm_calls, reference="company_metadata_batch")

    _persist_researched(db, tenant_id, unique, researched, result)
    return result


def _persist_researched(db: Session, tenant_id: Optional[int], unique: dict,
                        researched: dict, result: dict) -> None:
    """Store what this batch paid to learn, so the next run reads it from cache.

    The lead-sourcing gate DROPS most companies it researches. Before this, their
    results were never stored, so every scheduled run re-bought them. Each
    researched company is upserted into this tenant's ClientInfo (filling null
    fields only, stamping ``enriched_at`` / ``enrich_attempts``). A company seen
    for the first time is stored as an INACTIVE record with no services; lead
    sourcing re-activates it if it later becomes a real lead.

    Best-effort: a failure here only costs a future cache miss.
    """
    if tenant_id is None or not researched:
        return
    from app.db.models.client import ClientStatus

    now = datetime.utcnow()
    for key, source in researched.items():
        info = unique.get(key) or {}
        name = (info.get("name") or "").strip()[:255]
        if not name:
            continue
        r = result.get(key) or {}
        try:
            with db.begin_nested():  # one company's failure never touches the rest
                client = db.query(ClientInfo).filter(
                    ClientInfo.tenant_id == tenant_id,
                    ClientInfo.client_name == name,
                ).first()
                if client is None:
                    client = ClientInfo(
                        tenant_id=tenant_id,
                        client_name=name,
                        status=ClientStatus.INACTIVE,
                        service_count=0,
                        enrich_attempts=0,
                    )
                    db.add(client)
                if not client.industry and r.get("industry"):
                    client.industry = str(r["industry"])[:100]
                if not client.company_size and r.get("company_size"):
                    client.company_size = str(r["company_size"])[:50]
                if not client.employee_count and r.get("employee_count") is not None:
                    try:
                        client.employee_count = int(r["employee_count"])
                    except (ValueError, TypeError):
                        pass
                if not client.domain and info.get("domain"):
                    client.domain = (_extract_domain(info["domain"]) or info["domain"])[:255]
                _add_source(client, source)
                client.enriched_at = now
                client.enrich_attempts = (client.enrich_attempts or 0) + 1
                db.flush()
        except Exception as e:
            logger.debug("company_research_persist_failed", company=name, error=str(e))


def bulk_enrich_clients(db: Session, client_ids: list[int], tenant_id: Optional[int] = None) -> dict:
    """Enrich multiple clients."""
    results = []
    enriched = 0
    skipped = 0

    for cid in client_ids:
        cq = db.query(ClientInfo).filter(ClientInfo.client_id == cid)
        if tenant_id is not None:
            cq = cq.filter(ClientInfo.tenant_id == tenant_id)
        client = cq.first()
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
