"""AI-powered natural language search for leads."""
import re
import structlog
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func

from app.db.models.lead import LeadDetails

logger = structlog.get_logger()

# US state name → abbreviation mapping
US_STATES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY",
}
# Reverse map: abbreviation → full name
US_STATE_ABBREVS = {v: k.title() for k, v in US_STATES.items()}


def parse_natural_query(query: str) -> Dict[str, Any]:
    """Parse a natural language lead search query into structured filters.

    Examples:
        'tech companies in Texas hiring HR managers 80k+'
        → {industry: ['tech'], state: 'TX', job_title: 'HR manager', salary_min: 80000}

        'manufacturing in Ohio'
        → {industry: ['manufacturing'], state: 'OH'}

        'recent leads from last 7 days'
        → {days_ago: 7}
    """
    query_lower = query.lower().strip()
    filters: Dict[str, Any] = {}

    # Extract salary
    salary_match = re.search(r'(\d+)\s*k\s*\+', query_lower)
    if salary_match:
        filters["salary_min"] = int(salary_match.group(1)) * 1000
    salary_match2 = re.search(r'\$(\d{2,3}),?(\d{3})\s*\+?', query_lower)
    if salary_match2:
        filters["salary_min"] = int(salary_match2.group(1) + salary_match2.group(2))

    # Extract state
    for state_name, abbrev in US_STATES.items():
        if state_name in query_lower or f" {abbrev.lower()} " in f" {query_lower} ":
            filters["state"] = abbrev
            break

    # Extract city (pattern: "in CityName, STATE" or "in CityName")
    city_match = re.search(r'in\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)', query)
    if city_match and city_match.group(1).lower() not in US_STATES:
        filters["city"] = city_match.group(1)

    # Extract industry keywords
    industries = []
    industry_keywords = {
        "tech": "Technology", "technology": "Technology",
        "healthcare": "Healthcare", "health": "Healthcare", "medical": "Healthcare",
        "manufacturing": "Manufacturing", "logistics": "Logistics",
        "retail": "Retail", "finance": "Financial Services", "financial": "Financial Services",
        "education": "Education", "engineering": "Engineering",
        "construction": "Construction", "energy": "Energy",
        "hospitality": "Hospitality", "real estate": "Real Estate",
        "legal": "Legal", "insurance": "Insurance", "automotive": "Automotive",
        "food": "Food & Beverage", "oil": "Oil & Gas",
    }
    for keyword, industry in industry_keywords.items():
        if keyword in query_lower:
            industries.append(industry)
    if industries:
        filters["industries"] = industries

    # Extract job title keywords
    title_keywords = [
        "hr manager", "hr director", "recruiter", "talent acquisition",
        "operations manager", "plant manager", "warehouse manager",
        "logistics manager", "production supervisor", "general manager",
        "regional manager", "site manager", "project manager",
        "purchasing manager", "procurement manager", "safety manager",
        "quality manager", "maintenance manager", "facilities manager",
        "branch manager", "manufacturing manager", "engineering manager",
    ]
    for title in title_keywords:
        if title in query_lower:
            filters["job_title"] = title
            break

    # If no specific title found, try to extract "hiring X" pattern
    if "job_title" not in filters:
        hiring_match = re.search(r'hiring\s+(.+?)(?:\s+\d|$|\s+in\s+)', query_lower)
        if hiring_match:
            filters["job_title"] = hiring_match.group(1).strip()

    # Extract time range
    days_match = re.search(r'(?:last|past)\s+(\d+)\s+days?', query_lower)
    if days_match:
        filters["days_ago"] = int(days_match.group(1))
    elif "recent" in query_lower or "new" in query_lower:
        filters["days_ago"] = 7
    elif "this week" in query_lower:
        filters["days_ago"] = 7
    elif "this month" in query_lower:
        filters["days_ago"] = 30

    # Extract status
    if "open" in query_lower:
        filters["status"] = "open"
    elif "closed" in query_lower:
        filters["status"] = "closed"
    elif "hunting" in query_lower:
        filters["status"] = "hunting"

    # Extract source
    source_keywords = ["linkedin", "indeed", "glassdoor", "jsearch", "apollo", "adzuna"]
    for source in source_keywords:
        if source in query_lower:
            filters["source"] = source
            break

    return filters


def execute_ai_search(query: str, db: Session, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
    """Parse a natural language query and execute it against the leads database.

    Returns: {filters: dict, results: list[dict], total: int, query: str}
    """
    from datetime import datetime, timedelta

    filters = parse_natural_query(query)

    q = db.query(LeadDetails).filter(LeadDetails.is_archived == False)

    if "state" in filters:
        q = q.filter(func.upper(LeadDetails.state) == filters["state"])

    if "city" in filters:
        q = q.filter(LeadDetails.city.ilike(f"%{filters['city']}%"))

    if "industries" in filters:
        # LeadDetails has no industry column; search in client_name as best approximation
        industry_filters = [LeadDetails.client_name.ilike(f"%{ind}%") for ind in filters["industries"]]
        q = q.filter(or_(*industry_filters))

    if "job_title" in filters:
        q = q.filter(LeadDetails.job_title.ilike(f"%{filters['job_title']}%"))

    if "salary_min" in filters:
        q = q.filter(LeadDetails.salary_min >= filters["salary_min"])

    if "status" in filters:
        q = q.filter(LeadDetails.lead_status == filters["status"])

    if "source" in filters:
        q = q.filter(LeadDetails.source.ilike(f"%{filters['source']}%"))

    if "days_ago" in filters:
        cutoff = datetime.utcnow() - timedelta(days=filters["days_ago"])
        q = q.filter(LeadDetails.created_at >= cutoff)

    total = q.count()
    results = q.order_by(LeadDetails.created_at.desc()).offset(offset).limit(limit).all()

    return {
        "query": query,
        "filters_applied": filters,
        "total": total,
        "results": [
            {
                "lead_id": r.lead_id,
                "company_name": r.client_name,
                "job_title": r.job_title,
                "state": r.state,
                "city": getattr(r, "city", None),
                "salary_min": float(r.salary_min) if r.salary_min else None,
                "salary_max": float(r.salary_max) if r.salary_max else None,
                "status": r.lead_status.value if r.lead_status else None,
                "source": r.source,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in results
        ],
    }
