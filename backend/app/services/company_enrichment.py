"""Company enrichment service.

Three-tier enrichment strategy:
1. Aggregate from leads (free, always) — website/linkedin from lead data, most common state
2. OpenCorporates (free 500/month) — if configured
3. Clearbit (paid) — if configured

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


def enrich_client(db: Session, client: ClientInfo) -> dict:
    """Run all enrichment tiers for a single client.

    Returns summary of what was enriched.
    """
    result = {"client_id": client.client_id, "client_name": client.client_name, "fields_updated": []}

    # Tier 1: Aggregate from leads (always free)
    lead_updates = enrich_from_leads(db, client)
    if lead_updates:
        result["fields_updated"].extend(list(lead_updates.keys()))

    return result


def bulk_enrich_clients(db: Session, client_ids: list[int]) -> dict:
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

        r = enrich_client(db, client)
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
