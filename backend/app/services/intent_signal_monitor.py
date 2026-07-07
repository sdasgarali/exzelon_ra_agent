"""Intent Signal Monitor — trigger-based prospecting for LOB lead generation.

Monitors configured sources for new intent signals (funding rounds, job postings,
tech stack changes, new NPI registrations). Creates leads automatically when
signals match LOB criteria.

This service is designed to be called periodically by the scheduler or manually
via the API. It processes each LOB's signal configuration and creates leads
for matching signals.
"""
import json
import structlog
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session

from app.db.base import SessionLocal
from app.db.models.lead import LeadDetails, LeadStatus
from app.db.models.line_of_business import LineOfBusiness, LOBStatus
from app.core.config import settings
from app.core.settings_resolver import get_tenant_setting, get_lob_config

logger = structlog.get_logger()

# Signal type definitions with their adapter mapping
SIGNAL_TYPES = {
    "new_npi_registration": {
        "adapter": "npi_registry",
        "description": "New healthcare practice NPI registrations",
        "lob_types": ["rcm"],
        "default_interval_hours": 24,
    },
    "funding_round": {
        "adapter": "crunchbase",
        "description": "Companies that recently received funding",
        "lob_types": ["software_dev", "ai_services"],
        "default_interval_hours": 24,
    },
    "poor_pagespeed": {
        "adapter": "pagespeed",
        "description": "Websites with poor performance scores",
        "lob_types": ["digital_marketing"],
        "default_interval_hours": 168,  # weekly
    },
    "tech_stack_change": {
        "adapter": "builtwith",
        "description": "Companies that changed their tech stack",
        "lob_types": ["software_dev", "digital_marketing"],
        "default_interval_hours": 168,  # weekly
    },
    "github_activity": {
        "adapter": "github_org",
        "description": "Organizations with recent GitHub activity",
        "lob_types": ["software_dev", "ai_services"],
        "default_interval_hours": 168,  # weekly
    },
    "hiring_signal": {
        "adapter": "hiring_signal",
        "description": "Internal hiring pattern analysis for buying signals",
        "lob_types": ["rcm", "software_dev", "ai_services", "digital_marketing"],
        "default_interval_hours": 24,
    },
    "news_event": {
        "adapter": "news_signal",
        "description": "News and event monitoring for business triggers",
        "lob_types": ["rcm", "software_dev", "ai_services", "digital_marketing"],
        "default_interval_hours": 24,
    },
}


def check_intent_signals(
    tenant_id: Optional[int] = None,
    lob_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Check configured intent signals and create leads for matching ones.

    This is the main entry point for trigger-based prospecting.
    Can be called by the scheduler or manually via API.

    Args:
        tenant_id: Scope to a specific tenant (or check all if None)
        lob_id: Scope to a specific LOB (or check all active LOBs if None)

    Returns:
        Summary of signals checked and leads created.
    """
    db = SessionLocal()
    results = {
        "signals_checked": 0,
        "leads_created": 0,
        "errors": 0,
        "details": [],
    }

    try:
        # Get LOBs to process
        query = db.query(LineOfBusiness).filter(LineOfBusiness.status == LOBStatus.ACTIVE)
        if tenant_id:
            query = query.filter(LineOfBusiness.tenant_id == tenant_id)
        if lob_id:
            query = query.filter(LineOfBusiness.lob_id == lob_id)

        lobs = query.all()

        for lob in lobs:
            lob_results = _check_signals_for_lob(db, lob)
            results["signals_checked"] += lob_results["signals_checked"]
            results["leads_created"] += lob_results["leads_created"]
            results["errors"] += lob_results["errors"]
            results["details"].append({
                "lob_id": lob.lob_id,
                "lob_name": lob.name,
                "lob_type": lob.lob_type,
                **lob_results,
            })

        logger.info(
            "intent_signal_check_completed",
            signals_checked=results["signals_checked"],
            leads_created=results["leads_created"],
        )

    except Exception as e:
        logger.error("intent_signal_check_failed", error=str(e))
        results["errors"] += 1
    finally:
        db.close()

    return results


def _check_signals_for_lob(db: Session, lob: LineOfBusiness) -> Dict[str, Any]:
    """Check intent signals configured for a specific LOB."""
    result = {"signals_checked": 0, "leads_created": 0, "errors": 0}

    # Get LOB's signal configuration
    lead_source_config = get_lob_config(db, lob.lob_id, "lead_source_config") or {}
    signals_config = lead_source_config.get("intent_signals", {})

    if not signals_config:
        # Use default signals for this LOB type
        signals_config = _default_signals_for_lob_type(lob.lob_type)

    for signal_name, signal_params in signals_config.items():
        if signal_name not in SIGNAL_TYPES:
            continue

        signal_def = SIGNAL_TYPES[signal_name]

        # Check if this signal type is relevant for this LOB
        if lob.lob_type not in signal_def["lob_types"]:
            continue

        try:
            leads = _fetch_signal(
                db=db,
                signal_name=signal_name,
                signal_def=signal_def,
                signal_params=signal_params if isinstance(signal_params, dict) else {},
                lob=lob,
            )
            result["signals_checked"] += 1

            # Create leads from signals
            for lead_data in leads:
                created = _create_lead_from_signal(db, lead_data, lob)
                if created:
                    result["leads_created"] += 1

        except Exception as e:
            logger.warning(
                "signal_check_error",
                signal=signal_name,
                lob_id=lob.lob_id,
                error=str(e),
            )
            result["errors"] += 1

    return result


def _fetch_signal(
    db: Session,
    signal_name: str,
    signal_def: Dict[str, Any],
    signal_params: Dict[str, Any],
    lob: LineOfBusiness,
) -> List[Dict[str, Any]]:
    """Fetch leads from a signal source."""
    adapter_name = signal_def["adapter"]
    leads = []

    if adapter_name == "npi_registry":
        from app.services.adapters.lead_sources.npi_registry import NPIRegistryAdapter
        adapter = NPIRegistryAdapter()
        taxonomy = signal_params.get("taxonomy", "")
        state = signal_params.get("state", "")
        leads = adapter.fetch_leads(
            taxonomy=taxonomy,
            state=state,
            limit=signal_params.get("limit", 50),
        )

    elif adapter_name == "crunchbase":
        from app.services.adapters.lead_sources.crunchbase import CrunchbaseAdapter
        api_key = get_tenant_setting(db, "crunchbase_api_key", tenant_id=lob.tenant_id) or settings.CRUNCHBASE_API_KEY
        if api_key:
            adapter = CrunchbaseAdapter(api_key=api_key)
            leads = adapter.fetch_leads(
                categories=signal_params.get("categories", []),
                funding_stage=signal_params.get("funding_stage", ""),
                limit=signal_params.get("limit", 25),
            )

    elif adapter_name == "pagespeed":
        from app.services.adapters.lead_sources.pagespeed import PageSpeedAdapter
        api_key = get_tenant_setting(db, "google_places_api_key", tenant_id=lob.tenant_id) or settings.GOOGLE_PLACES_API_KEY
        adapter = PageSpeedAdapter(api_key=api_key)
        domains = signal_params.get("domains", [])
        if domains:
            leads = adapter.fetch_leads(
                domains=domains,
                max_score=signal_params.get("max_score", 0.5),
                limit=signal_params.get("limit", 20),
            )

    elif adapter_name == "github_org":
        from app.services.adapters.lead_sources.github_org import GitHubOrgAdapter
        token = get_tenant_setting(db, "github_token", tenant_id=lob.tenant_id) or settings.GITHUB_TOKEN
        adapter = GitHubOrgAdapter(token=token)
        leads = adapter.fetch_leads(
            query=signal_params.get("query", ""),
            language=signal_params.get("language", ""),
            min_repos=signal_params.get("min_repos", 10),
            limit=signal_params.get("limit", 30),
        )

    elif adapter_name == "builtwith":
        from app.services.adapters.lead_sources.builtwith import BuiltWithAdapter
        api_key = get_tenant_setting(db, "builtwith_api_key", tenant_id=lob.tenant_id) or settings.BUILTWITH_API_KEY
        if api_key:
            adapter = BuiltWithAdapter(api_key=api_key)
            leads = adapter.fetch_leads(
                technology=signal_params.get("technology", ""),
                limit=signal_params.get("limit", 20),
            )

    elif adapter_name == "hiring_signal":
        from app.services.adapters.lead_sources.hiring_signal import HiringSignalAdapter
        adapter = HiringSignalAdapter(db=db, tenant_id=lob.tenant_id)
        leads = adapter.fetch_leads(
            lob_type=lob.lob_type,
            days_back=signal_params.get("days_back", 30),
            limit=signal_params.get("limit", 50),
        )

    elif adapter_name == "news_signal":
        from app.services.adapters.lead_sources.news_signal import NewsSignalAdapter
        adapter = NewsSignalAdapter()
        leads = adapter.fetch_leads(
            lob_type=lob.lob_type,
            limit=signal_params.get("limit", 20),
        )

    return leads


def _create_lead_from_signal(
    db: Session, lead_data: Dict[str, Any], lob: LineOfBusiness
) -> bool:
    """Create a lead from a signal match, with dedup check."""
    client_name = lead_data.get("client_name", "")
    if not client_name:
        return False

    # Dedup: check if lead already exists for this company + LOB
    from app.services.pipelines.lead_sourcing import normalize_company_name
    normalized = normalize_company_name(client_name)

    existing = db.query(LeadDetails).filter(
        LeadDetails.tenant_id == lob.tenant_id,
        LeadDetails.lob_id == lob.lob_id,
    ).all()

    for ex in existing:
        if normalize_company_name(ex.client_name or "") == normalized:
            return False  # Already exists

    try:
        lead = LeadDetails(
            tenant_id=lob.tenant_id,
            lob_id=lob.lob_id,
            client_name=client_name,
            job_title=lead_data.get("job_title", "Prospect"),
            state=lead_data.get("state"),
            city=lead_data.get("city"),
            source=lead_data.get("source", "intent_signal"),
            industry=lead_data.get("industry"),
            employer_website=lead_data.get("employer_website"),
            company_size=str(lead_data.get("company_size", "")) if lead_data.get("company_size") else None,
            job_link=lead_data.get("job_link"),
            lead_status=LeadStatus.NEW,
            first_name=lead_data.get("contact_first_name"),
            last_name=lead_data.get("contact_last_name"),
            contact_title=lead_data.get("contact_title"),
            contact_phone=lead_data.get("contact_phone"),
            metadata_json=json.dumps(lead_data.get("metadata", {})) if lead_data.get("metadata") else None,
        )
        db.add(lead)
        db.flush()
        return True
    except Exception as e:
        db.rollback()
        logger.warning("signal_lead_create_error", error=str(e), company=client_name)
        return False


def _default_signals_for_lob_type(lob_type: str) -> Dict[str, Any]:
    """Return default signal configurations for a LOB type."""
    defaults = {
        "staffing": {},
        "rcm": {
            "new_npi_registration": {"taxonomy": "Internal Medicine", "state": "", "limit": 50},
            "hiring_signal": {"lob_type": "rcm", "days_back": 30, "limit": 50},
            "news_event": {"lob_type": "rcm", "limit": 20},
        },
        "software_dev": {
            "funding_round": {"categories": ["software", "saas"], "funding_stage": "series_a", "limit": 25},
            "tech_stack_change": {"technology": "WordPress", "limit": 20},
            "github_activity": {"query": "software", "min_repos": 20, "limit": 30},
            "hiring_signal": {"lob_type": "software_dev", "days_back": 30, "limit": 50},
            "news_event": {"lob_type": "software_dev", "limit": 20},
        },
        "ai_services": {
            "funding_round": {"categories": ["artificial-intelligence", "machine-learning"], "limit": 25},
            "github_activity": {"query": "ai machine-learning", "min_repos": 10, "limit": 30},
            "hiring_signal": {"lob_type": "ai_services", "days_back": 30, "limit": 50},
            "news_event": {"lob_type": "ai_services", "limit": 20},
        },
        "digital_marketing": {
            "poor_pagespeed": {"max_score": 0.4, "limit": 20},
            "tech_stack_change": {"technology": "WordPress", "limit": 20},
            "hiring_signal": {"lob_type": "digital_marketing", "days_back": 30, "limit": 50},
            "news_event": {"lob_type": "digital_marketing", "limit": 20},
        },
        "custom": {},
    }
    return defaults.get(lob_type, {})


def get_available_signals(lob_type: str = "") -> List[Dict[str, Any]]:
    """Return available signal types with their metadata.

    If lob_type is provided, only returns signals relevant to that LOB.
    """
    signals = []
    for name, info in SIGNAL_TYPES.items():
        if lob_type and lob_type not in info["lob_types"]:
            continue
        signals.append({
            "name": name,
            "description": info["description"],
            "adapter": info["adapter"],
            "lob_types": info["lob_types"],
            "default_interval_hours": info["default_interval_hours"],
        })
    return signals
