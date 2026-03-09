"""Campaign auto-enrollment service — matches validated contacts to campaign rules."""
import json
from typing import Dict, Any, List, Optional
import structlog

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.models.campaign import (
    Campaign, CampaignContact, CampaignStatus,
)
from app.db.models.contact import ContactDetails, OutreachStatus
from app.db.models.lead import LeadDetails
from app.db.models.suppression import SuppressionList

logger = structlog.get_logger()


def parse_enrollment_rules(campaign: Campaign) -> Optional[Dict[str, Any]]:
    """Parse enrollment_rules_json from a campaign. Returns None if disabled/invalid."""
    if not campaign.enrollment_rules_json:
        return None
    try:
        rules = json.loads(campaign.enrollment_rules_json)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(rules, dict):
        return None
    if not rules.get("enabled", False):
        return None
    return rules


def find_matching_contacts(
    campaign: Campaign,
    rules: Dict[str, Any],
    db: Session,
) -> List[int]:
    """Build a query to find contacts matching enrollment rules. Returns list of contact_ids."""
    # Calculate remaining enrollment capacity
    daily_cap = rules.get("daily_cap", 200)
    max_per_run = rules.get("max_per_run", 50)
    already_today = campaign.auto_enrolled_today or 0
    remaining = daily_cap - already_today
    if remaining <= 0:
        return []
    limit = min(max_per_run, remaining)

    query = db.query(ContactDetails.contact_id)

    # Must be active outreach status
    query = query.filter(ContactDetails.outreach_status == OutreachStatus.ACTIVE)

    # Validation status filter
    validation_statuses = rules.get("validation_status")
    if validation_statuses and isinstance(validation_statuses, list) and len(validation_statuses) > 0:
        # Case-insensitive match
        lower_statuses = [s.lower() for s in validation_statuses]
        query = query.filter(func.lower(ContactDetails.validation_status).in_(lower_statuses))
    else:
        # Default: only Valid
        query = query.filter(func.lower(ContactDetails.validation_status) == "valid")

    # Priority level filter
    priority_levels = rules.get("priority_levels")
    if priority_levels and isinstance(priority_levels, list) and len(priority_levels) > 0:
        query = query.filter(ContactDetails.priority_level.in_(priority_levels))

    # State filter
    states = rules.get("states")
    if states and isinstance(states, list) and len(states) > 0:
        upper_states = [s.upper() for s in states]
        query = query.filter(func.upper(ContactDetails.location_state).in_(upper_states))

    # Source filter
    sources = rules.get("sources")
    if sources and isinstance(sources, list) and len(sources) > 0:
        lower_sources = [s.lower() for s in sources]
        query = query.filter(func.lower(ContactDetails.source).in_(lower_sources))

    # Lead score filter
    min_lead_score = rules.get("min_lead_score")
    if min_lead_score and isinstance(min_lead_score, (int, float)) and min_lead_score > 0:
        query = query.filter(ContactDetails.lead_score >= int(min_lead_score))

    # Job title keywords filter (OR across keywords, matched against lead.job_title)
    job_title_keywords = rules.get("job_title_keywords")
    if job_title_keywords and isinstance(job_title_keywords, list) and len(job_title_keywords) > 0:
        from sqlalchemy import or_
        keyword_filters = []
        for kw in job_title_keywords:
            kw = kw.strip()
            if kw:
                keyword_filters.append(LeadDetails.job_title.ilike(f"%{kw}%"))
        if keyword_filters:
            query = query.join(
                LeadDetails,
                LeadDetails.lead_id == ContactDetails.lead_id,
                isouter=True,
            )
            query = query.filter(or_(*keyword_filters))

    # Exclude: already enrolled in this campaign
    already_enrolled_subq = db.query(CampaignContact.contact_id).filter(
        CampaignContact.campaign_id == campaign.campaign_id,
    ).subquery()
    query = query.filter(~ContactDetails.contact_id.in_(already_enrolled_subq))

    # Exclude: suppressed emails
    suppressed_subq = db.query(SuppressionList.email).subquery()
    query = query.filter(~func.lower(ContactDetails.email).in_(suppressed_subq))

    # Exclude archived contacts
    query = query.filter(ContactDetails.is_archived == False)

    # Apply limit and return
    results = query.limit(limit).all()
    return [r[0] for r in results]


def run_auto_enrollment_for_campaign(
    campaign: Campaign,
    db: Session,
) -> Dict[str, Any]:
    """Run auto-enrollment for a single campaign. Returns stats."""
    rules = parse_enrollment_rules(campaign)
    if not rules:
        return {"campaign_id": campaign.campaign_id, "skipped": True, "reason": "rules disabled or invalid"}

    contact_ids = find_matching_contacts(campaign, rules, db)
    if not contact_ids:
        return {"campaign_id": campaign.campaign_id, "enrolled": 0, "matched": 0}

    # Use existing enroll_contacts function
    from app.services.campaign_engine import enroll_contacts
    result = enroll_contacts(campaign.campaign_id, contact_ids, db)

    enrolled = result.get("enrolled", 0)
    if enrolled > 0:
        campaign.auto_enrolled_today = (campaign.auto_enrolled_today or 0) + enrolled
        db.commit()

    return {
        "campaign_id": campaign.campaign_id,
        "campaign_name": campaign.name,
        "matched": len(contact_ids),
        "enrolled": enrolled,
        "duplicates": result.get("duplicates", 0),
    }


def run_auto_enrollment(db: Session) -> Dict[str, Any]:
    """Run auto-enrollment across all active campaigns with enrollment rules."""
    campaigns = db.query(Campaign).filter(
        Campaign.status == CampaignStatus.ACTIVE,
        Campaign.is_archived == False,
        Campaign.enrollment_rules_json.isnot(None),
    ).all()

    results = {
        "campaigns_checked": len(campaigns),
        "total_enrolled": 0,
        "per_campaign": [],
    }

    for campaign in campaigns:
        try:
            stats = run_auto_enrollment_for_campaign(campaign, db)
            results["per_campaign"].append(stats)
            results["total_enrolled"] += stats.get("enrolled", 0)
        except Exception as e:
            logger.error("Auto-enrollment failed for campaign",
                        campaign_id=campaign.campaign_id, error=str(e))
            results["per_campaign"].append({
                "campaign_id": campaign.campaign_id,
                "error": str(e),
            })

    return results


def preview_enrollment_matches(
    campaign_id: int,
    rules: Dict[str, Any],
    db: Session,
) -> int:
    """Count matching contacts without enrolling (for frontend preview)."""
    campaign = db.query(Campaign).filter(
        Campaign.campaign_id == campaign_id,
    ).first()
    if not campaign:
        return 0

    # Temporarily set rules on campaign object for find_matching_contacts
    # We use a copy to avoid modifying the actual DB record
    preview_rules = {**rules, "enabled": True, "max_per_run": 10000, "daily_cap": 10000}

    # Build same query but just count
    from sqlalchemy import or_

    query = db.query(func.count(ContactDetails.contact_id))

    # Must be active outreach status
    query = query.filter(ContactDetails.outreach_status == OutreachStatus.ACTIVE)

    # Validation status filter
    validation_statuses = preview_rules.get("validation_status")
    if validation_statuses and isinstance(validation_statuses, list) and len(validation_statuses) > 0:
        lower_statuses = [s.lower() for s in validation_statuses]
        query = query.filter(func.lower(ContactDetails.validation_status).in_(lower_statuses))
    else:
        query = query.filter(func.lower(ContactDetails.validation_status) == "valid")

    # Priority level filter
    priority_levels = preview_rules.get("priority_levels")
    if priority_levels and isinstance(priority_levels, list) and len(priority_levels) > 0:
        query = query.filter(ContactDetails.priority_level.in_(priority_levels))

    # State filter
    states = preview_rules.get("states")
    if states and isinstance(states, list) and len(states) > 0:
        upper_states = [s.upper() for s in states]
        query = query.filter(func.upper(ContactDetails.location_state).in_(upper_states))

    # Source filter
    sources = preview_rules.get("sources")
    if sources and isinstance(sources, list) and len(sources) > 0:
        lower_sources = [s.lower() for s in sources]
        query = query.filter(func.lower(ContactDetails.source).in_(lower_sources))

    # Lead score filter
    min_lead_score = preview_rules.get("min_lead_score")
    if min_lead_score and isinstance(min_lead_score, (int, float)) and min_lead_score > 0:
        query = query.filter(ContactDetails.lead_score >= int(min_lead_score))

    # Job title keywords filter
    job_title_keywords = preview_rules.get("job_title_keywords")
    if job_title_keywords and isinstance(job_title_keywords, list) and len(job_title_keywords) > 0:
        keyword_filters = []
        for kw in job_title_keywords:
            kw = kw.strip()
            if kw:
                keyword_filters.append(LeadDetails.job_title.ilike(f"%{kw}%"))
        if keyword_filters:
            query = query.join(
                LeadDetails,
                LeadDetails.lead_id == ContactDetails.lead_id,
                isouter=True,
            )
            query = query.filter(or_(*keyword_filters))

    # Exclude: already enrolled in this campaign
    already_enrolled_subq = db.query(CampaignContact.contact_id).filter(
        CampaignContact.campaign_id == campaign_id,
    ).subquery()
    query = query.filter(~ContactDetails.contact_id.in_(already_enrolled_subq))

    # Exclude: suppressed emails
    suppressed_subq = db.query(SuppressionList.email).subquery()
    query = query.filter(~func.lower(ContactDetails.email).in_(suppressed_subq))

    # Exclude archived
    query = query.filter(ContactDetails.is_archived == False)

    return query.scalar() or 0
