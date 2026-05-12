"""Intent data and buying signals detection."""
import json
import structlog
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from app.db.models.lead import LeadDetails
from app.db.query_helpers import tenant_filter

logger = structlog.get_logger()

# LOB-aware intent scoring weight matrices
# Each LOB type has a set of signal evaluators with their max points
LOB_INTENT_WEIGHTS: Dict[str, Dict[str, int]] = {
    "staffing": {
        "active_hiring": 25,
        "company_size_match": 15,
        "posting_recency": 15,
        "industry_match": 10,
        "linkedin_verified": 5,
        "website_present": 5,
        "salary_level": 10,
        "high_budget_role": 10,
        "recent_posting_7d": 5,
    },
    "rcm": {
        "npi_verified": 20,
        "practice_size": 15,
        "registration_recency": 15,
        "healthcare_specialty": 15,
        "authorized_official": 10,
        "phone_verified": 5,
        "provider_count": 5,
        "billing_hiring": 5,
        "website_present": 5,
        "industry_match": 5,
    },
    "software_dev": {
        "recent_funding": 25,
        "employee_range": 15,
        "funding_recency": 15,
        "tech_vertical": 10,
        "website_verified": 5,
        "tech_stack_age": 10,
        "funding_amount": 10,
        "tech_hiring": 5,
        "github_presence": 5,
    },
    "ai_services": {
        "ai_talent_hiring": 25,
        "enterprise_fit": 15,
        "activity_recency": 15,
        "tech_maturity": 10,
        "github_presence": 5,
        "repo_activity": 10,
        "team_size": 10,
        "ai_hiring": 5,
        "website_present": 5,
    },
    "digital_marketing": {
        "poor_website_score": 25,
        "smb_fit": 15,
        "audit_recency": 15,
        "local_industry": 10,
        "review_count": 5,
        "seo_gap": 10,
        "marketing_hiring": 10,
        "business_status": 5,
        "website_present": 5,
    },
}

# Intent tier thresholds
INTENT_TIERS = [
    (76, "Burning"),
    (51, "Hot"),
    (26, "Warm"),
    (0, "Cold"),
]


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


def calculate_intent_score_v2(lead: LeadDetails, lob_type: str = "staffing") -> dict:
    """Calculate LOB-aware intent score using per-LOB weight matrices.

    Unlike v1 which uses flat weights, v2 evaluates different signals with
    different weights depending on the LOB type. A "recent funding" signal
    is worth 25 points for software_dev but 0 for staffing.

    Args:
        lead: LeadDetails model instance
        lob_type: One of staffing, rcm, software_dev, ai_services, digital_marketing

    Returns:
        Dict with intent_score (0-100), signals, signal_count, tier, top_signal
    """
    weights = LOB_INTENT_WEIGHTS.get(lob_type, LOB_INTENT_WEIGHTS["staffing"])
    score = 0
    signals: List[str] = []
    signal_scores: Dict[str, int] = {}

    # Parse metadata for LOB-specific signals
    metadata = {}
    if lead.metadata_json:
        try:
            metadata = json.loads(lead.metadata_json)
        except (json.JSONDecodeError, TypeError):
            pass

    # --- Universal signals (applicable across all LOBs) ---

    # Active hiring / job posting
    if lead.job_title and lead.job_title != "Prospect":
        pts = weights.get("active_hiring", 0)
        if pts:
            score += pts
            signals.append("active_hiring")
            signal_scores["active_hiring"] = pts

    # Posting/creation recency
    if lead.created_at:
        age_days = (datetime.utcnow() - lead.created_at).days
        if age_days <= 7:
            pts = weights.get("posting_recency", weights.get("registration_recency", weights.get("funding_recency", weights.get("activity_recency", weights.get("audit_recency", 0)))))
            if pts:
                score += pts
                signals.append("recent_7d")
                signal_scores["recent_7d"] = pts
        elif age_days <= 30:
            pts_key = "posting_recency" if "posting_recency" in weights else "registration_recency" if "registration_recency" in weights else "funding_recency" if "funding_recency" in weights else "activity_recency" if "activity_recency" in weights else "audit_recency"
            pts = weights.get(pts_key, 0) // 2  # Half points for 30-day recency
            if pts:
                score += pts
                signals.append("recent_30d")
                signal_scores["recent_30d"] = pts

    # Company size match
    if lead.company_size:
        try:
            size_str = str(lead.company_size).replace("+", "").replace(",", "")
            size = int(size_str.split("-")[0])
            size_matched = False

            if lob_type == "rcm" and 2 <= size <= 200:
                size_matched = True
            elif lob_type == "software_dev" and 20 <= size <= 500:
                size_matched = True
            elif lob_type == "ai_services" and 50 <= size <= 2000:
                size_matched = True
            elif lob_type == "digital_marketing" and 5 <= size <= 200:
                size_matched = True
            elif lob_type == "staffing" and 50 <= size <= 5000:
                size_matched = True

            if size_matched:
                pts_key = "company_size_match" if "company_size_match" in weights else "practice_size" if "practice_size" in weights else "employee_range" if "employee_range" in weights else "enterprise_fit" if "enterprise_fit" in weights else "smb_fit"
                pts = weights.get(pts_key, 0)
                if pts:
                    score += pts
                    signals.append("company_size_fit")
                    signal_scores["company_size_fit"] = pts
        except (ValueError, IndexError):
            pass

    # Industry match
    if lead.industry:
        pts_key = "industry_match" if "industry_match" in weights else "healthcare_specialty" if "healthcare_specialty" in weights else "tech_vertical" if "tech_vertical" in weights else "tech_maturity" if "tech_maturity" in weights else "local_industry"
        pts = weights.get(pts_key, 0)
        if pts:
            score += pts
            signals.append("industry_match")
            signal_scores["industry_match"] = pts

    # LinkedIn/website presence
    if lead.employer_linkedin_url:
        pts = weights.get("linkedin_verified", 0)
        if pts:
            score += pts
            signals.append("linkedin_verified")
            signal_scores["linkedin_verified"] = pts

    if lead.employer_website:
        pts = weights.get("website_present", weights.get("website_verified", 0))
        if pts:
            score += pts
            signals.append("website_present")
            signal_scores["website_present"] = pts

    # Salary / budget signal
    if lead.salary_min:
        try:
            salary = float(lead.salary_min)
            if salary >= 80000:
                pts = weights.get("salary_level", weights.get("high_budget_role", weights.get("funding_amount", 0)))
                if pts:
                    score += pts
                    signals.append("high_budget")
                    signal_scores["high_budget"] = pts
        except (ValueError, TypeError):
            pass

    # --- Metadata-based signals (LOB-specific) ---

    signal_type = metadata.get("signal_type", "")

    # NPI-specific signals (RCM)
    if signal_type == "npi" or metadata.get("npi_number"):
        pts = weights.get("npi_verified", 0)
        if pts:
            score += pts
            signals.append("npi_verified")
            signal_scores["npi_verified"] = pts

        if metadata.get("authorized_official_name"):
            pts = weights.get("authorized_official", 0)
            if pts:
                score += pts
                signals.append("authorized_official")
                signal_scores["authorized_official"] = pts

        provider_count = metadata.get("provider_count", 0)
        if provider_count and int(provider_count) > 0:
            pts = weights.get("provider_count", 0)
            if pts:
                score += pts
                signals.append("provider_count")
                signal_scores["provider_count"] = pts

        if metadata.get("phone"):
            pts = weights.get("phone_verified", 0)
            if pts:
                score += pts
                signals.append("phone_verified")
                signal_scores["phone_verified"] = pts

    # Funding signals (Software Dev, AI Services)
    funding_total = metadata.get("funding_total_usd", 0)
    if funding_total:
        try:
            if float(funding_total) > 0:
                pts = weights.get("recent_funding", weights.get("funding_amount", 0))
                if pts:
                    score += pts
                    signals.append("has_funding")
                    signal_scores["has_funding"] = pts
        except (ValueError, TypeError):
            pass

    # Tech stack signals (Software Dev, Digital Marketing)
    if metadata.get("tech_stack") or metadata.get("technologies"):
        pts = weights.get("tech_stack_age", 0)
        if pts:
            score += pts
            signals.append("tech_stack_data")
            signal_scores["tech_stack_data"] = pts

    # GitHub/repo signals (Software Dev, AI Services)
    public_repos = metadata.get("public_repos", 0)
    if public_repos:
        try:
            if int(public_repos) > 10:
                pts = weights.get("github_presence", weights.get("repo_activity", 0))
                if pts:
                    score += pts
                    signals.append("github_active")
                    signal_scores["github_active"] = pts
        except (ValueError, TypeError):
            pass

    # Performance score signals (Digital Marketing)
    perf_score = metadata.get("performance_score")
    if perf_score is not None:
        try:
            if float(perf_score) < 0.5:
                pts = weights.get("poor_website_score", weights.get("seo_gap", 0))
                if pts:
                    score += pts
                    signals.append("poor_performance")
                    signal_scores["poor_performance"] = pts
        except (ValueError, TypeError):
            pass

    # Review count (Digital Marketing)
    review_count = metadata.get("user_rating_count", metadata.get("review_count", 0))
    if review_count:
        try:
            if int(review_count) > 10:
                pts = weights.get("review_count", 0)
                if pts:
                    score += pts
                    signals.append("has_reviews")
                    signal_scores["has_reviews"] = pts
        except (ValueError, TypeError):
            pass

    # Hiring signal metadata
    if signal_type == "hiring_signal":
        hiring_key = {
            "rcm": "billing_hiring",
            "software_dev": "tech_hiring",
            "ai_services": "ai_hiring",
            "digital_marketing": "marketing_hiring",
        }.get(lob_type)
        if hiring_key:
            pts = weights.get(hiring_key, 0)
            if pts:
                score += pts
                signals.append(hiring_key)
                signal_scores[hiring_key] = pts

    # News signal metadata
    if signal_type == "news_signal":
        news_signals = metadata.get("signals", [])
        if news_signals:
            # Add points based on relevance
            pts = 5  # Base points for any news signal
            score += pts
            signals.append("news_signal")
            signal_scores["news_signal"] = pts

    # Cap at 100
    final_score = min(score, 100)

    # Determine tier
    tier = "Cold"
    for threshold, tier_name in INTENT_TIERS:
        if final_score >= threshold:
            tier = tier_name
            break

    # Find top signal
    top_signal = ""
    if signal_scores:
        top_signal = max(signal_scores, key=signal_scores.get)

    return {
        "intent_score": final_score,
        "signals": signals,
        "signal_count": len(signals),
        "tier": tier,
        "top_signal": top_signal,
    }
