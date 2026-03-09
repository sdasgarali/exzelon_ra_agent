"""Waterfall contact enrichment — chains multiple providers in priority order."""
import structlog
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session

logger = structlog.get_logger()

# Provider priority chain
WATERFALL_ORDER = [
    "apollo", "seamless", "hunter", "snovio",
    "rocketreach", "pdl", "proxycurl",
]


def waterfall_enrich(
    company_name: str,
    domain: str = "",
    lead_id: int = None,
    max_contacts: int = 4,
    db: Session = None,
) -> Dict[str, Any]:
    """Chain through contact discovery providers, stopping on first result.

    Falls back through the chain on empty results:
    Apollo → Seamless → Hunter → Snov.io → RocketReach → PDL → Proxycurl
    """
    results = {
        "contacts_found": 0,
        "provider_used": None,
        "providers_tried": [],
        "contacts": [],
    }

    for provider_name in WATERFALL_ORDER:
        results["providers_tried"].append(provider_name)
        try:
            contacts = _try_provider(provider_name, company_name, domain, max_contacts)
            if contacts:
                results["contacts_found"] = len(contacts)
                results["provider_used"] = provider_name
                results["contacts"] = contacts
                logger.info("Waterfall enrichment found contacts",
                           provider=provider_name,
                           company=company_name,
                           count=len(contacts))
                return results
        except Exception as e:
            logger.warning("Waterfall provider failed",
                         provider=provider_name,
                         error=str(e))
            continue

    logger.info("Waterfall enrichment exhausted all providers",
               company=company_name)
    return results


def _try_provider(
    provider_name: str,
    company_name: str,
    domain: str,
    max_contacts: int,
) -> List[Dict[str, Any]]:
    """Try a single provider and return contacts if any found."""
    from app.core.config import settings

    if provider_name == "apollo" and settings.APOLLO_API_KEY:
        from app.services.adapters.contact_discovery.apollo_adapter import ApolloContactAdapter
        adapter = ApolloContactAdapter()
        return adapter.discover_contacts(company_name=company_name, domain=domain, limit=max_contacts)

    if provider_name == "seamless" and settings.SEAMLESS_API_KEY:
        from app.services.adapters.contact_discovery.seamless_adapter import SeamlessContactAdapter
        adapter = SeamlessContactAdapter()
        return adapter.discover_contacts(company_name=company_name, domain=domain, limit=max_contacts)

    # Add other providers as they're configured
    return []
