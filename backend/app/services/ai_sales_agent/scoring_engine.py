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


def calculate_lead_score(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Score a lead based on job/company signals.

    Returns: {score: 0-100, factors: {reason: points}, reasoning: str}
    """
    lead = ctx.get("lead", {})
    company = ctx.get("company", {})
    score = 0
    factors: Dict[str, int] = {}

    if lead.get("job_title"):
        score += 20
        factors["ACTIVE_HIRING"] = 20

    posting = lead.get("posting_date")
    if posting:
        try:
            posting_dt = datetime.fromisoformat(posting) if isinstance(posting, str) else posting
            days_old = (datetime.utcnow() - posting_dt).days
            if days_old <= 7:
                score += 15
                factors["RECENT_POSTING_7D"] = 15
            elif days_old <= 30:
                score += 10
                factors["RECENT_POSTING_30D"] = 10
        except (ValueError, TypeError):
            pass

    size = company.get("size") or ""
    if "51-200" in size or "201-500" in size:
        score += 15
        factors["MID_MARKET"] = 15
    elif "501-1000" in size or "1001-5000" in size or "5000+" in size:
        score += 10
        factors["ENTERPRISE"] = 10

    if company.get("industry"):
        score += 10
        factors["INDUSTRY_IDENTIFIED"] = 10

    salary = lead.get("salary_min")
    if salary and salary >= 80000:
        score += 10
        factors["HIGH_BUDGET_ROLE"] = 10

    if company.get("linkedin"):
        score += 5
        factors["LINKEDIN_VERIFIED"] = 5

    if company.get("website"):
        score += 5
        factors["WEBSITE_VERIFIED"] = 5

    score = min(100, score)
    return {
        "score": score,
        "factors": factors,
        "reasoning": ", ".join(f"{k}(+{v})" for k, v in factors.items()),
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
