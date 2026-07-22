"""Resource Pool ATS integration — Phase 1 lead hand-off connector.

On a qualified lead, the RA Agent pushes a Company + Contact + Job + Opportunity
into the Resource Pool ATS via its REST API (`POST /api/v1/leads`, Bearer key,
`leads:write` scope). The push is idempotent: Resource Pool keys the Job on
``externalRef = "ra-lead-<lead_id>"`` so re-pushing updates rather than duplicates.
"""
import logging
from typing import Any, Dict, Optional

import httpx

from app.core.config import settings
from app.core.settings_resolver import get_tenant_setting

logger = logging.getLogger(__name__)

# Opportunity stages accepted by Resource Pool.
_VALID_STAGES = {"LEAD", "QUALIFIED", "PROPOSAL", "WON", "LOST"}


class ResourcePoolClient:
    """Thin HTTP client for the Resource Pool public API."""

    def __init__(self, base_url: str, api_key: str, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    @classmethod
    def from_settings(cls, db, tenant_id: Optional[int] = None) -> Optional["ResourcePoolClient"]:
        """Build a client from tenant settings (falls back to env config).
        Returns None when the integration is not configured."""
        url = (get_tenant_setting(db, "resourcepool_api_url", tenant_id=tenant_id,
                                  default=settings.RESOURCE_POOL_API_URL) or "").strip()
        key = (get_tenant_setting(db, "resourcepool_api_key", tenant_id=tenant_id,
                                  default=settings.RESOURCE_POOL_API_KEY) or "").strip()
        if not url or not key:
            return None
        return cls(base_url=url, api_key=key)

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def push_lead(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """POST a lead payload to Resource Pool. Raises httpx.HTTPStatusError on non-2xx."""
        url = f"{self.base_url}/api/v1/leads"
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(url, json=payload, headers=self._headers())
        resp.raise_for_status()
        return resp.json()


def _clean(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    v = str(v).strip()
    return v or None


def build_lead_payload(lead, company=None, contact=None, stage: str = "LEAD") -> Dict[str, Any]:
    """Map a LeadDetails (+ optional ClientInfo, ContactDetails) to the RP intake payload.

    - ``company`` is the matching ClientInfo (firmographics), if available.
    - ``contact`` is the chosen ContactDetails (client-side POC), if available.
    - ``stage`` is the Opportunity stage (LEAD when just handed off, QUALIFIED on
      a positive client reply).
    """
    stage = stage if stage in _VALID_STAGES else "LEAD"
    client_name = _clean(getattr(lead, "client_name", None)) or "Unknown Company"

    location = ", ".join([p for p in [_clean(getattr(lead, "city", None)),
                                       _clean(getattr(lead, "state", None))] if p]) or None

    payload: Dict[str, Any] = {
        "externalRef": f"ra-lead-{lead.lead_id}",
        "company": {
            "name": (_clean(getattr(company, "client_name", None)) if company else None) or client_name,
            "industry": (_clean(getattr(company, "industry", None)) if company else None)
            or _clean(getattr(lead, "industry", None)),
            "website": (_clean(getattr(company, "website", None)) if company else None)
            or (_clean(getattr(company, "domain", None)) if company else None)
            or _clean(getattr(lead, "employer_website", None)),
            "location": (_clean(getattr(company, "location_state", None)) if company else None)
            or _clean(getattr(lead, "state", None)),
        },
        "job": {
            "jobTitle": _clean(getattr(lead, "job_title", None)) or "Open Role",
            "location": location,
            "requiredSkills": None,
            "description": _clean(getattr(lead, "job_description", None)),
            "billRate": None,
            "status": "OPEN",
        },
        "opportunity": {"stage": stage, "value": None},
    }

    if contact is not None:
        name = " ".join([p for p in [_clean(getattr(contact, "first_name", None)),
                                     _clean(getattr(contact, "last_name", None))] if p]).strip()
        payload["contact"] = {
            "name": name or _clean(getattr(contact, "client_name", None)) or "Contact",
            "email": _clean(getattr(contact, "email", None)),
            "phone": _clean(getattr(contact, "phone", None)),
            "title": _clean(getattr(contact, "title", None)),
        }

    return payload
