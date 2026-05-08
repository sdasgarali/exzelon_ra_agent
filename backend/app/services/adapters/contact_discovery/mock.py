"""Mock contact discovery adapter for testing."""
from typing import List, Dict, Any, Optional
import random
from app.services.adapters.base import ContactDiscoveryAdapter
from app.db.models.contact import PriorityLevel


class MockContactDiscoveryAdapter(ContactDiscoveryAdapter):
    """Mock adapter that generates sample contact data for testing."""

    FIRST_NAMES = ["John", "Jane", "Michael", "Sarah", "David", "Emily", "Robert", "Lisa", "James", "Maria"]
    LAST_NAMES = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Wilson", "Martinez"]

    TITLES_BY_PRIORITY = {
        PriorityLevel.P1_JOB_POSTER: ["Hiring Manager", "Talent Acquisition Specialist"],
        PriorityLevel.P2_HR_TA_RECRUITER: ["HR Recruiter", "Talent Acquisition Coordinator", "Technical Recruiter"],
        PriorityLevel.P3_HR_MANAGER: ["HR Manager", "HRBP", "HR Director", "VP of Human Resources"],
        PriorityLevel.P4_OPS_LEADER: ["Operations Manager", "Plant Manager", "Production Manager", "Business Unit Leader"],
        PriorityLevel.P5_FUNCTIONAL_MANAGER: ["Department Manager", "Team Lead", "Supervisor", "Project Manager"]
    }

    STATES = ["CA", "TX", "FL", "NY", "IL", "PA", "OH", "GA", "NC", "MI"]

    def test_connection(self) -> bool:
        """Mock always returns successful connection."""
        return True

    def search_contacts(
        self,
        company_name: str,
        job_title: Optional[str] = None,
        state: Optional[str] = None,
        titles: Optional[List[str]] = None,
        limit: int = 4,
        domain: Optional[str] = None,
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """Generate mock contacts for a company."""
        contacts = []

        # Generate contacts in priority order
        priority_levels = list(PriorityLevel)
        random.shuffle(priority_levels)

        for i, priority in enumerate(priority_levels[:limit]):
            first_name = random.choice(self.FIRST_NAMES)
            last_name = random.choice(self.LAST_NAMES)
            title = random.choice(self.TITLES_BY_PRIORITY.get(priority, ["Manager"]))
            contact_state = state if state else random.choice(self.STATES)

            # Generate email
            company_domain = company_name.lower().replace(" ", "").replace(",", "").replace(".", "").replace("'", "").replace("&", "").replace("(", "").replace(")", "")[:15]
            email = f"{first_name.lower()}.{last_name.lower()}@{company_domain}.com"

            contact = {
                "first_name": first_name,
                "last_name": last_name,
                "title": title,
                "email": email,
                "phone": f"+1-555-{random.randint(100, 999)}-{random.randint(1000, 9999)}",
                "location_state": contact_state,
                "priority_level": priority,
                "source": "mock"
            }
            contacts.append(contact)

        return contacts

    def normalize(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize contact data (mock data is already normalized)."""
        return raw_data
