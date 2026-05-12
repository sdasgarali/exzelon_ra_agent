"""Centralized Scoring Engine — composable scores with explainable reason codes.

Consolidates scoring from intent_data.py and adds engagement scoring,
content scoring, and composite scoring. Every score includes reason
codes explaining why points were added/deducted.
"""
from datetime import datetime
from typing import Any, Dict

import structlog

logger = structlog.get_logger()

PRIORITY_WEIGHTS = {
    "P1_JOB_POSTER": 1.5,
    "P2_HIRING_MANAGER": 1.3,
    "P3_HR_CONTACT": 1.1,
    "P4_DEPARTMENT_HEAD": 1.0,
    "P5_FUNCTIONAL_MANAGER": 0.9,
}

# LOB-specific scoring signal weights (max points per signal)
LOB_SCORING_WEIGHTS: Dict[str, Dict[str, int]] = {
    "staffing": {
        "hiring_signals": 25,
        "company_size": 15,
        "industry_match": 15,
        "recency": 15,
        "salary_budget": 10,
        "web_presence": 10,
        "contact_quality": 10,
    },
    "rcm": {
        "practice_size": 20,
        "specialty_match": 20,
        "provider_count": 15,
        "location": 15,
        "npi_verified": 10,
        "web_presence": 10,
        "contact_quality": 10,
    },
    "software_dev": {
        "funding_stage": 20,
        "hiring_velocity": 15,
        "tech_stack_age": 15,
        "company_growth": 15,
        "team_size": 10,
        "web_presence": 15,
        "contact_quality": 10,
    },
    "ai_services": {
        "ai_adoption": 20,
        "automation_need": 20,
        "budget_signals": 15,
        "tech_maturity": 15,
        "company_size": 10,
        "web_presence": 10,
        "contact_quality": 10,
    },
    "digital_marketing": {
        "seo_gap": 20,
        "social_presence": 15,
        "website_quality": 20,
        "review_score": 15,
        "location": 10,
        "web_presence": 10,
        "contact_quality": 10,
    },
}


def calculate_lead_score(ctx: Dict[str, Any], lob_type: str = "") -> Dict[str, Any]:
    """Score a lead based on job/company signals, with optional LOB-specific weights.

    When lob_type is provided, uses LOB-specific scoring criteria in addition
    to the base scoring. Otherwise, uses the default staffing-oriented scoring.

    Returns: {score: 0-100, factors: {reason: points}, reasoning: str}
    """
    lead = ctx.get("lead", {})
    company = ctx.get("company", {})
    metadata = lead.get("metadata") or {}
    score = 0
    factors: Dict[str, int] = {}

    # Get LOB weights (fall back to staffing)
    weights = LOB_SCORING_WEIGHTS.get(lob_type, LOB_SCORING_WEIGHTS["staffing"])

    # --- Base signals (apply to all LOBs) ---
    if lead.get("job_title"):
        pts = weights.get("hiring_signals", 20)
        score += pts
        factors["ACTIVE_HIRING"] = pts

    posting = lead.get("posting_date")
    if posting:
        try:
            posting_dt = datetime.fromisoformat(posting) if isinstance(posting, str) else posting
            days_old = (datetime.utcnow() - posting_dt).days
            recency_max = weights.get("recency", 15)
            if days_old <= 7:
                score += recency_max
                factors["RECENT_POSTING_7D"] = recency_max
            elif days_old <= 30:
                pts = int(recency_max * 0.67)
                score += pts
                factors["RECENT_POSTING_30D"] = pts
        except (ValueError, TypeError):
            pass

    size = company.get("size") or ""
    size_max = weights.get("company_size", 15)
    if "51-200" in size or "201-500" in size:
        score += size_max
        factors["MID_MARKET"] = size_max
    elif "501-1000" in size or "1001-5000" in size or "5000+" in size:
        pts = int(size_max * 0.67)
        score += pts
        factors["ENTERPRISE"] = pts

    if company.get("industry"):
        pts = weights.get("industry_match", 10)
        score += pts
        factors["INDUSTRY_IDENTIFIED"] = pts

    salary = lead.get("salary_min")
    if salary and salary >= 80000:
        pts = weights.get("salary_budget", 10)
        score += pts
        factors["HIGH_BUDGET_ROLE"] = pts

    if company.get("linkedin"):
        score += 5
        factors["LINKEDIN_VERIFIED"] = 5

    if company.get("website"):
        pts = weights.get("web_presence", 5)
        score += pts
        factors["WEBSITE_VERIFIED"] = pts

    # --- LOB-specific signals (from lead metadata) ---
    if lob_type == "rcm":
        if metadata.get("npi_number"):
            pts = weights.get("npi_verified", 10)
            score += pts
            factors["NPI_VERIFIED"] = pts
        provider_count = metadata.get("provider_count", 0)
        if provider_count >= 5:
            pts = weights.get("provider_count", 15)
            score += pts
            factors["MULTI_PROVIDER_PRACTICE"] = pts
        if metadata.get("specialty"):
            pts = weights.get("specialty_match", 10)
            score += pts
            factors["SPECIALTY_MATCHED"] = pts

    elif lob_type == "software_dev":
        funding = metadata.get("funding_total_usd", 0)
        if funding > 1_000_000:
            pts = weights.get("funding_stage", 20)
            score += pts
            factors["FUNDED_COMPANY"] = pts
        elif funding > 0:
            pts = int(weights.get("funding_stage", 20) * 0.5)
            score += pts
            factors["SEED_FUNDED"] = pts
        if metadata.get("tech_stack"):
            pts = weights.get("tech_stack_age", 10)
            score += pts
            factors["TECH_STACK_KNOWN"] = pts

    elif lob_type == "ai_services":
        if metadata.get("categories"):
            cats = set(c.lower() for c in metadata["categories"])
            if cats & {"artificial intelligence", "machine learning", "deep learning"}:
                pts = weights.get("ai_adoption", 15)
                score += pts
                factors["AI_AWARE_COMPANY"] = pts
        if metadata.get("public_repos", 0) > 10:
            pts = weights.get("tech_maturity", 10)
            score += pts
            factors["TECH_ACTIVE"] = pts

    elif lob_type == "digital_marketing":
        perf_score = metadata.get("performance_score")
        if perf_score is not None and perf_score < 0.5:
            pts = weights.get("website_quality", 20)
            score += pts
            factors["POOR_WEBSITE_PERFORMANCE"] = pts
        seo_score = metadata.get("seo_score")
        if seo_score is not None and seo_score < 0.7:
            pts = weights.get("seo_gap", 15)
            score += pts
            factors["SEO_GAP_IDENTIFIED"] = pts
        review_count = metadata.get("review_count", 0)
        if review_count > 0 and metadata.get("rating", 5) < 4.0:
            pts = weights.get("review_score", 10)
            score += pts
            factors["LOW_REVIEWS"] = pts

    score = min(100, score)
    return {
        "score": score,
        "factors": factors,
        "reasoning": ", ".join(f"{k}(+{v})" for k, v in factors.items()),
        "lob_type": lob_type or "staffing",
    }


def calculate_engagement_score(history: Dict[str, Any]) -> Dict[str, Any]:
    """Score engagement level from outreach history.

    Returns: {score: 0-100, level: cold/warm/hot/dead, factors: {}}
    """
    sent = history.get("emails_sent", 0)
    replied = history.get("emails_replied", 0)
    opened = history.get("emails_opened", 0)
    clicked = history.get("emails_clicked", 0)

    if sent == 0:
        return {"score": 0, "level": "cold", "factors": {}, "reasoning": "No emails sent"}

    score = 0
    factors: Dict[str, int] = {}

    if replied > 0:
        reply_points = min(40, replied * 20)
        score += reply_points
        factors["REPLIED"] = reply_points

    if clicked > 0:
        click_points = min(25, clicked * 15)
        score += click_points
        factors["CLICKED"] = click_points

    if opened > 0:
        open_points = min(25, opened * 5)
        score += open_points
        factors["OPENED"] = open_points

    if sent >= 3 and replied == 0 and opened == 0:
        score = max(0, score - 10)
        factors["NO_ENGAGEMENT_PENALTY"] = -10

    score = min(100, max(0, score))

    if score >= 60:
        level = "hot"
    elif score >= 25:
        level = "warm"
    elif sent >= 3 and score == 0:
        level = "dead"
    else:
        level = "cold"

    return {
        "score": score,
        "level": level,
        "factors": factors,
        "reasoning": ", ".join(f"{k}({'+' if v > 0 else ''}{v})" for k, v in factors.items()),
    }


def calculate_composite_score(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Calculate a weighted composite score combining lead + engagement + priority.

    Weights: lead_score 40%, engagement 40%, priority 20%
    """
    lead_result = calculate_lead_score(ctx)
    engagement_result = calculate_engagement_score(ctx.get("history", {}))

    priority = ctx.get("contact", {}).get("priority")
    priority_weight = PRIORITY_WEIGHTS.get(priority, 1.0)
    priority_score = int(priority_weight * 50)

    composite = int(
        lead_result["score"] * 0.4
        + engagement_result["score"] * 0.4
        + priority_score * 0.2
    )
    composite = min(100, max(0, composite))

    return {
        "lead_score": lead_result["score"],
        "engagement_score": engagement_result["score"],
        "engagement_level": engagement_result["level"],
        "priority_score": priority_score,
        "composite": composite,
        "lead_factors": lead_result["factors"],
        "engagement_factors": engagement_result["factors"],
    }
