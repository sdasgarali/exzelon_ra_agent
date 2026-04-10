"""Mock job source adapter for testing.

IMPACT ON LEAD COUNT:
  - The mock adapter is used when NO real API keys (JSearch, Apollo) are configured.
  - It generates synthetic data for testing/demo purposes.
  - Previously generated only 10-25 jobs, now generates 80-150 for realistic testing.
  - To get REAL leads, configure JSearch or Apollo API keys in Settings.
"""
from datetime import date, timedelta
from typing import List, Dict, Any, Optional
import random
from app.services.adapters.base import JobSourceAdapter


class MockJobSourceAdapter(JobSourceAdapter):
    """Mock adapter that generates sample job data for testing.

    IMPACT: When this adapter is active (no real API keys configured), all leads
    are synthetic. Configure real API keys in Settings > Job Sources to get
    actual job postings from LinkedIn, Indeed, Glassdoor, etc.
    """

    # Expanded company list - 50 companies across target non-IT industries
    # IMPACT: More companies = more unique leads after deduplication
    SAMPLE_COMPANIES = [
        # Healthcare
        "Acme Healthcare Corp", "MediCare Solutions", "HealthFirst Systems",
        "Valley Medical Center", "Sunrise Senior Living", "Pacific Health Group",
        "Midwest Regional Hospital", "CareBridge Health", "Premier Nursing Services",
        # Manufacturing
        "AutoParts Manufacturing", "Precision Metal Works", "Great Lakes Steel",
        "National Plastics Corp", "Superior Coatings Inc", "Atlas Assembly Group",
        "Midwest Tool and Die", "American Fabrication Co", "Continental Manufacturing",
        # Logistics and Warehousing
        "Industrial Logistics LLC", "Express Distribution Inc", "Heartland Freight",
        "Pacific Shipping Corp", "Central Warehousing Co", "National Supply Chain Inc",
        "Rapid Fulfillment Services", "Continental Cargo LLC",
        # Construction and Trades
        "Construction Builders Inc", "Summit Contractors Group", "Ironclad Roofing",
        "Keystone Plumbing Corp", "Elite Electrical Services", "Foundation Paving Co",
        # Retail and Hospitality
        "Retail Giants Co", "Fresh Foods Market", "Comfort Inn Holdings",
        "Golden Table Restaurant Group", "Metro Grocery Chain", "Sunset Resort Group",
        # Energy and Industrial
        "Energy Solutions Ltd", "Lone Star Oil Services", "WindPower Systems",
        "SolarField Energy Corp", "Mountain Gas Utilities",
        # Other Non-IT
        "Food Processing Corp", "Real Estate Holdings", "Insurance Partners Inc",
        "Financial Services Group", "Legal Associates LLP",
        "Greenfield Agriculture Co", "BlueSky Environmental",
    ]

    SAMPLE_TITLES = [
        "Warehouse Manager", "Production Supervisor", "HR Coordinator",
        "Operations Manager", "Plant Manager", "Logistics Coordinator",
        "Sales Representative", "Customer Service Manager", "Quality Assurance Lead",
        "Maintenance Technician", "Forklift Operator", "Shipping Clerk",
        "HR Manager", "HR Director", "Recruiter", "Talent Acquisition Manager",
        "Supply Chain Manager", "Safety Manager", "Facilities Manager",
        "Branch Manager", "Regional Manager", "General Manager",
        "Site Manager", "Distribution Manager", "Purchasing Manager",
    ]

    STATES = [
        "CA", "TX", "FL", "NY", "IL", "PA", "OH", "GA", "NC", "MI",
        "NJ", "VA", "WA", "AZ", "MA", "TN", "IN", "MO", "MD", "WI",
        "CO", "MN", "SC", "AL", "LA", "KY", "OR", "OK", "CT", "UT",
    ]

    def test_connection(self) -> bool:
        """Mock always returns successful connection."""
        return True

    def fetch_jobs(
        self,
        location: str = "United States",
        posted_within_days: int = 30,
        industries: Optional[List[str]] = None,
        exclude_keywords: Optional[List[str]] = None,
        job_titles: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Generate mock job postings for testing/demo.

        IMPACT ON LEAD COUNT:
          - Generates 80-150 jobs (was 10-25) for more realistic testing.
          - Exclude keywords are still applied but with a larger pool, more
            leads survive the filtering.

        Args:
            location: Target location
            posted_within_days: Days since posting (default 30 for broader range)
            industries: Target industries
            exclude_keywords: Keywords to exclude
            job_titles: Target job titles to use (cycles through all)
        """
        import time
        run_id = int(time.time())  # IMPACT: Unique run ID so each run generates unique job_links
        jobs = []
        # IMPACT: Increased from 10-25 to 80-150 for realistic demo data
        num_jobs = random.randint(80, 150)

        # Use provided job_titles or fall back to sample titles
        available_titles = job_titles if job_titles else self.SAMPLE_TITLES

        for i in range(num_jobs):
            company = self.SAMPLE_COMPANIES[i % len(self.SAMPLE_COMPANIES)]
            # Cycle through provided job titles
            title = available_titles[i % len(available_titles)]
            state = self.STATES[i % len(self.STATES)]

            job = {
                "client_name": company,
                "job_title": title,
                "state": state,
                "posting_date": date.today() - timedelta(days=random.randint(0, posted_within_days)),
                "job_link": f"https://jobs.example.com/{run_id}-{i}",
                "salary_min": random.randint(40000, 60000),
                "salary_max": random.randint(65000, 120000),
                "source": "mock",
                "employment_type": random.choice(["Full-time", "Part-time", "Contract", "Temporary"]),
            }

            # Apply exclude keywords filter
            if exclude_keywords:
                should_exclude = False
                for keyword in exclude_keywords:
                    if keyword.lower() in title.lower() or keyword.lower() in company.lower():
                        should_exclude = True
                        break
                if should_exclude:
                    continue

            jobs.append(job)

        return jobs

    def normalize(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize job data (mock data is already normalized)."""
        return raw_data
