"""Company enrichment service.

Multi-tier enrichment strategy:
1. Aggregate from leads (free, always) — website/linkedin from lead data, most common state
2. LLM research (uses configured AI adapter) — fills remaining gaps via AI knowledge
3. OpenCorporates (free 500/month) — if configured
4. Clearbit (paid) — if configured

Only fills missing fields (never overwrites existing data).
"""
import structlog
from datetime import datetime, date
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func

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


def _get_ai_adapter(db: Session, tenant_id: Optional[int] = None):
    """Load the configured AI adapter from settings."""
    provider = get_tenant_setting(db, "warmup_ai_provider", tenant_id=tenant_id, default="groq")
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
        if provider == "groq":
            from app.services.adapters.ai.groq import GroqAdapter
            return GroqAdapter(api_key=api_key)
        elif provider == "openai":
            from app.services.adapters.ai.openai_adapter import OpenAIAdapter
            return OpenAIAdapter(api_key=api_key)
        elif provider == "anthropic":
            from app.services.adapters.ai.anthropic_adapter import AnthropicAdapter
            return AnthropicAdapter(api_key=api_key)
        elif provider == "gemini":
            from app.services.adapters.ai.gemini import GeminiAdapter
            return GeminiAdapter(api_key=api_key)
    except Exception:
        pass
    return None


# Fields that LLM can fill, mapped to max lengths for string columns
_LLM_FIELD_LIMITS = {
    "website": 500,
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

    # Tier 1: Aggregate from leads (always free)
    lead_updates = enrich_from_leads(db, client)
    if lead_updates:
        result["fields_updated"].extend(list(lead_updates.keys()))

    # Tier 2: LLM research (uses configured AI adapter)
    llm_updates = enrich_from_llm(db, client, tenant_id=tenant_id)
    if llm_updates:
        result["fields_updated"].extend(list(llm_updates.keys()))

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
