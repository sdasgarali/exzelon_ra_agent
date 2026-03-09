"""AI ICP Wizard — generates Ideal Customer Profiles from business descriptions."""
import json
import structlog
from typing import Dict, Any

logger = structlog.get_logger()


def generate_icp(
    company_desc: str,
    offering: str,
    pain_points: str,
) -> Dict[str, Any]:
    """Generate an Ideal Customer Profile using AI.

    Falls back to rule-based generation if AI is unavailable.

    Args:
        company_desc: Description of the user's company
        offering: What they sell / service they provide
        pain_points: Problems they solve for customers

    Returns:
        {industries: [], job_titles: [], states: [], company_sizes: [], rationale: str}
    """
    # Try AI-powered generation
    try:
        return _generate_with_ai(company_desc, offering, pain_points)
    except Exception as e:
        logger.warning("AI ICP generation failed, using rule-based fallback", error=str(e))
        return _generate_rule_based(company_desc, offering, pain_points)


def _generate_with_ai(company_desc: str, offering: str, pain_points: str) -> Dict[str, Any]:
    """Use AI adapter to generate ICP."""
    from app.services.adapters.ai_content import get_ai_adapter

    prompt = f"""You are a B2B sales strategist. Based on the following business description, generate an Ideal Customer Profile (ICP).

**Company Description:** {company_desc}
**Product/Service Offering:** {offering}
**Pain Points Solved:** {pain_points}

Return a JSON object with exactly these fields:
- "industries": array of 3-5 target industry names (e.g., "Healthcare", "Manufacturing", "Logistics")
- "job_titles": array of 5-8 decision-maker job titles to target (e.g., "HR Manager", "Operations Director")
- "states": array of 3-5 best US state abbreviations for this offering (e.g., "TX", "CA", "OH")
- "company_sizes": array of company size ranges (e.g., "1-50", "51-200", "201-500")
- "rationale": a 2-3 sentence explanation of why this ICP makes sense

Return ONLY the JSON object, no markdown or other text."""

    adapter = get_ai_adapter()
    response = adapter.generate_content(prompt=prompt, max_tokens=800)

    # Parse JSON from response
    text = response.get("content", "") if isinstance(response, dict) else str(response)

    # Extract JSON from response (handle markdown code blocks)
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    result = json.loads(text.strip())

    # Validate required fields
    for field in ["industries", "job_titles", "states", "company_sizes", "rationale"]:
        if field not in result:
            result[field] = []
    if not result.get("rationale"):
        result["rationale"] = "AI-generated profile based on business description."

    return result


def _generate_rule_based(company_desc: str, offering: str, pain_points: str) -> Dict[str, Any]:
    """Rule-based fallback ICP generation using keyword matching."""
    combined = f"{company_desc} {offering} {pain_points}".lower()

    # Industry matching
    industry_keywords = {
        "Healthcare": ["health", "medical", "hospital", "clinic", "patient", "nursing"],
        "Manufacturing": ["manufactur", "production", "factory", "plant", "assembly"],
        "Logistics": ["logistics", "shipping", "transport", "warehouse", "freight", "supply chain"],
        "Retail": ["retail", "store", "shop", "consumer", "ecommerce", "e-commerce"],
        "Construction": ["construct", "building", "contractor", "architect"],
        "Energy": ["energy", "power", "utility", "solar", "oil", "gas"],
        "Hospitality": ["hotel", "restaurant", "hospitality", "food service", "catering"],
        "Education": ["education", "school", "university", "training", "learn"],
        "Financial Services": ["finance", "bank", "insurance", "invest", "accounting"],
        "Real Estate": ["real estate", "property", "commercial real", "residential"],
    }

    industries = []
    for industry, keywords in industry_keywords.items():
        if any(kw in combined for kw in keywords):
            industries.append(industry)
    if not industries:
        industries = ["Manufacturing", "Healthcare", "Logistics"]

    # Job title matching
    hr_keywords = ["staffing", "recruit", "talent", "hiring", "workforce", "hr ", "human resource"]
    ops_keywords = ["operations", "management", "efficiency", "process", "supply chain"]

    job_titles = []
    if any(kw in combined for kw in hr_keywords):
        job_titles.extend(["HR Manager", "HR Director", "Talent Acquisition Manager", "Recruiter", "Staffing Coordinator"])
    if any(kw in combined for kw in ops_keywords):
        job_titles.extend(["Operations Manager", "General Manager", "Plant Manager", "Regional Manager"])
    if not job_titles:
        job_titles = ["HR Manager", "Operations Manager", "General Manager", "Purchasing Manager", "Regional Manager"]

    # State selection - top states by business activity
    states = ["TX", "CA", "FL", "OH", "IL"]

    # Company sizes - default mid-market
    company_sizes = ["51-200", "201-500", "501-1000"]
    if "small" in combined or "startup" in combined:
        company_sizes = ["1-50", "51-200"]
    elif "enterprise" in combined or "large" in combined:
        company_sizes = ["501-1000", "1001-5000", "5001+"]

    return {
        "industries": industries[:5],
        "job_titles": job_titles[:8],
        "states": states,
        "company_sizes": company_sizes,
        "rationale": f"Profile generated based on keyword analysis of your business description. "
                     f"Targeting {', '.join(industries[:3])} industries with "
                     f"focus on {', '.join(job_titles[:3])} decision-makers.",
    }
