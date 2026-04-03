"""Intent data and buying signals detection."""
import structlog
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from app.db.models.lead import LeadDetails
from app.db.query_helpers import tenant_filter

logger = structlog.get_logger()


def calculate_intent_score(lead: LeadDetails) -> dict:
    """Calculate buying intent score based on available signals.

    Args:
        lead: LeadDetails model instance.

    Returns:
        Dict with intent_score (0-100), signals list, and signal_count.
    """
    score = 0
    signals = []

    # Hiring signal (they have a job posting = they're growing)
    if lead.job_title:
        score += 20
        signals.append("active_hiring")

    # Recency signal
    if lead.created_at:
        age_days = (datetime.utcnow() - lead.created_at).days
        if age_days <= 7:
            score += 15
            signals.append("recent_posting_7d")
        elif age_days <= 30:
            score += 10
            signals.append("recent_posting_30d")

    # Company size signal
    if lead.company_size:
        try:
            size_str = str(lead.company_size).replace("+", "").replace(",", "")
            size = int(size_str.split("-")[0])
            if 50 <= size <= 500:
                score += 15
                signals.append("mid_market_company")
            elif size > 500:
                score += 10
                signals.append("enterprise_company")
        except (ValueError, IndexError):
            pass

    # Industry match
    if lead.industry:
        score += 10
        signals.append("industry_identified")

    # Salary signal (higher salary = more budget)
    if lead.salary_min and float(lead.salary_min) >= 80000:
        score += 10
        signals.append("high_budget_role")

    # LinkedIn presence
    if lead.employer_linkedin_url:
        score += 5
        signals.append("linkedin_verified")

    # Website presence
    if lead.employer_website:
        score += 5
        signals.append("website_verified")

    return {
        "intent_score": min(score, 100),
        "signals": signals,
        "signal_count": len(signals),
    }


def enrich_leads_with_intent(
    db: Session,
    tenant_id: int,
    limit: int = 100,
) -> list:
    """Batch calculate intent scores for leads.

    Args:
        db: Database session.
        tenant_id: Tenant scope.
        limit: Maximum number of leads to process.

    Returns:
        List of dicts with lead info and intent scores, sorted by score desc.
    """
    leads_q = db.query(LeadDetails).filter(LeadDetails.is_archived == False)
    leads_q = tenant_filter(leads_q, LeadDetails, tenant_id)
    leads = leads_q.order_by(LeadDetails.created_at.desc()).limit(limit).all()

    results = []
    for lead in leads:
        intent = calculate_intent_score(lead)
        results.append({
            "lead_id": lead.lead_id,
            "company_name": lead.company_name if hasattr(lead, "company_name") else lead.client_name,
            "client_name": lead.client_name,
            "job_title": lead.job_title,
            "intent_score": intent["intent_score"],
            "signals": intent["signals"],
            "signal_count": intent["signal_count"],
        })

    # Sort by intent score descending
    results.sort(key=lambda x: x["intent_score"], reverse=True)
    return results
