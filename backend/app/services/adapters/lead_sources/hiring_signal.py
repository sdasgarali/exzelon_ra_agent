"""Hiring Signal Adapter — mines existing leads for buying intent patterns.

Analyzes job titles in lead_details to detect companies investing in roles
that signal outsourcing/service opportunities per LOB type. Zero external
API calls, zero cost.

Example: If a small company is hiring a "CTO" or "VP Engineering", they likely
need dev resources. If a practice is hiring "billing managers", they might
benefit from outsourced RCM.
"""
import structlog
from datetime import datetime, timedelta
from typing import List, Dict, Any

from sqlalchemy.orm import Session

from app.services.adapters.base import LeadSourceAdapter

logger = structlog.get_logger()

# LOB-specific hiring signal keywords
# Each maps to job title substrings that indicate buying intent for that LOB
HIRING_SIGNAL_KEYWORDS: Dict[str, List[str]] = {
    "rcm": [
        "medical billing", "revenue cycle", "coding specialist",
        "claims analyst", "billing manager", "billing director",
        "billing coordinator", "charge entry", "accounts receivable",
        "denial management",
    ],
    "software_dev": [
        "cto", "vp engineering", "tech lead", "solutions architect",
        "director of engineering", "head of engineering",
        "chief technology officer", "vp technology",
        "software architect", "engineering manager",
    ],
    "ai_services": [
        "ai engineer", "ml engineer", "data scientist",
        "chief ai officer", "nlp engineer", "machine learning",
        "head of ai", "director of ai", "vp data science",
        "deep learning", "computer vision engineer",
    ],
    "digital_marketing": [
        "marketing director", "seo specialist", "content manager",
        "growth manager", "digital marketing manager",
        "vp marketing", "head of marketing", "marketing coordinator",
        "brand manager", "social media manager",
    ],
}

# Company size thresholds for signal relevance
# Smaller companies hiring senior roles = stronger outsourcing signal
LOB_SIZE_THRESHOLDS: Dict[str, int] = {
    "rcm": 200,
    "software_dev": 200,
    "ai_services": 500,
    "digital_marketing": 100,
}


class HiringSignalAdapter(LeadSourceAdapter):
    """Adapter that mines existing leads for LOB-specific hiring signals.

    This adapter queries the lead_details table for job titles matching
    LOB-specific patterns, groups by company, and returns companies showing
    buying intent based on their hiring patterns.
    """

    def __init__(self, db: Session = None, tenant_id: int = None):
        self.db = db
        self.tenant_id = tenant_id
        self._api_calls = 0  # Always 0 — no external API

    def fetch_leads(
        self,
        query: str = "",
        location: str = "United States",
        limit: int = 100,
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """Fetch leads with hiring signals from existing data.

        Args:
            query: Ignored (LOB type determines keywords)
            location: Geographic filter (not used for DB queries)
            limit: Max results
            lob_type: Required — one of rcm, software_dev, ai_services, digital_marketing
            days_back: How far back to look (default 30)

        Returns:
            List of normalized lead dicts with hiring signal metadata.
        """
        lob_type = kwargs.get("lob_type", "")
        days_back = int(kwargs.get("days_back", 30))

        if not lob_type or lob_type not in HIRING_SIGNAL_KEYWORDS:
            logger.warning("hiring_signal_no_lob_type", lob_type=lob_type)
            return []

        if not self.db:
            logger.warning("hiring_signal_no_db_session")
            return []

        keywords = HIRING_SIGNAL_KEYWORDS[lob_type]
        cutoff = datetime.utcnow() - timedelta(days=days_back)

        try:
            from app.db.models.lead import LeadDetails
            from sqlalchemy import or_, func

            # Build title filter — match any keyword in job_title
            title_filters = [
                func.lower(LeadDetails.job_title).contains(kw.lower())
                for kw in keywords
            ]

            q = self.db.query(LeadDetails).filter(
                LeadDetails.created_at >= cutoff,
                or_(*title_filters),
            )
            if self.tenant_id:
                q = q.filter(LeadDetails.tenant_id == self.tenant_id)

            matches = q.order_by(LeadDetails.created_at.desc()).limit(limit * 3).all()

            # Group by company, deduplicate
            company_signals: Dict[str, Dict[str, Any]] = {}
            for lead in matches:
                company = (lead.client_name or "").strip()
                if not company:
                    continue

                company_key = company.lower()
                if company_key not in company_signals:
                    company_signals[company_key] = {
                        "client_name": company,
                        "job_title": "Prospect",
                        "state": lead.state,
                        "city": lead.city,
                        "industry": lead.industry,
                        "employer_website": lead.employer_website,
                        "employer_linkedin_url": lead.employer_linkedin_url,
                        "company_size": lead.company_size,
                        "source": "hiring_signal",
                        "job_link": lead.job_link,
                        "metadata": {
                            "signal_type": "hiring_signal",
                            "lob_type": lob_type,
                            "matching_titles": [],
                            "signal_count": 0,
                            "first_signal_date": lead.created_at.isoformat() if lead.created_at else None,
                        },
                    }

                sig = company_signals[company_key]
                title = lead.job_title or ""
                if title not in sig["metadata"]["matching_titles"]:
                    sig["metadata"]["matching_titles"].append(title)
                sig["metadata"]["signal_count"] += 1

            # Sort by signal count descending, limit results
            results = sorted(
                company_signals.values(),
                key=lambda x: x["metadata"]["signal_count"],
                reverse=True,
            )[:limit]

            logger.info(
                "hiring_signal_results",
                lob_type=lob_type,
                matches=len(matches),
                companies=len(results),
            )
            return results

        except Exception as e:
            logger.error("hiring_signal_fetch_error", error=str(e))
            return []

    def normalize(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Already normalized in fetch_leads."""
        return raw_data

    def test_connection(self) -> bool:
        """Always succeeds — no external dependency."""
        return True
