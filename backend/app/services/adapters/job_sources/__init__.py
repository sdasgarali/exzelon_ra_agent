"""Job source adapters package.

Note: Apollo.io is intentionally NOT a job source. It is a contact-enrichment
platform (see services/adapters/contact_discovery/apollo.py) and is only wired
into the Contact Enrichment pipeline, never lead sourcing.
"""
from app.services.adapters.job_sources.mock import MockJobSourceAdapter
from app.services.adapters.job_sources.jsearch import JSearchAdapter
from app.services.adapters.job_sources.indeed import IndeedAdapter
from app.services.adapters.job_sources.theirstack import TheirStackAdapter
from app.services.adapters.job_sources.serpapi import SerpAPIAdapter
from app.services.adapters.job_sources.adzuna import AdzunaAdapter

__all__ = [
    "MockJobSourceAdapter", "JSearchAdapter", "IndeedAdapter",
    "TheirStackAdapter", "SerpAPIAdapter", "AdzunaAdapter",
]
