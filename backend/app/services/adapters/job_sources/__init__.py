"""Job source adapters package."""
from app.services.adapters.job_sources.mock import MockJobSourceAdapter
from app.services.adapters.job_sources.jsearch import JSearchAdapter
from app.services.adapters.job_sources.indeed import IndeedAdapter
from app.services.adapters.job_sources.apollo import ApolloJobSourceAdapter
from app.services.adapters.job_sources.theirstack import TheirStackAdapter
from app.services.adapters.job_sources.serpapi import SerpAPIAdapter
from app.services.adapters.job_sources.adzuna import AdzunaAdapter

__all__ = [
    "MockJobSourceAdapter", "JSearchAdapter", "IndeedAdapter", "ApolloJobSourceAdapter",
    "TheirStackAdapter", "SerpAPIAdapter", "AdzunaAdapter",
]
