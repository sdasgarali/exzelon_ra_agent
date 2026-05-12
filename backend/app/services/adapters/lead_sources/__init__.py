"""LOB-specific lead source adapters package.

These adapters fetch business/organization leads from non-job-board sources,
designed for specific Lines of Business (RCM, Software Dev, AI Services,
Digital Marketing). They extend LeadSourceAdapter instead of JobSourceAdapter.
"""
from app.services.adapters.lead_sources.npi_registry import NPIRegistryAdapter
from app.services.adapters.lead_sources.google_business import GoogleBusinessAdapter
from app.services.adapters.lead_sources.crunchbase import CrunchbaseAdapter
from app.services.adapters.lead_sources.builtwith import BuiltWithAdapter
from app.services.adapters.lead_sources.pagespeed import PageSpeedAdapter
from app.services.adapters.lead_sources.github_org import GitHubOrgAdapter

__all__ = [
    "NPIRegistryAdapter",
    "GoogleBusinessAdapter",
    "CrunchbaseAdapter",
    "BuiltWithAdapter",
    "PageSpeedAdapter",
    "GitHubOrgAdapter",
]
