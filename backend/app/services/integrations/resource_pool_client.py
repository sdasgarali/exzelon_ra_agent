"""Resource Pool ATS integration — Phase 1 lead hand-off connector.

On a qualified lead, the RA Agent pushes a Company + Contact + Job + Opportunity
into the Resource Pool ATS via its REST API (`POST /api/v1/leads`, Bearer key,
`leads:write` scope). The push is idempotent: Resource Pool keys the Job on
``externalRef = "ra-lead-<lead_id>"`` so re-pushing updates rather than duplicates.
"""
import json
import logging
from typing import Any, Dict, Optional

import httpx

from app.core.config import settings
from app.core.settings_resolver import get_tenant_setting, get_tenant_setting_bool

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

    def get_match_summary(self, external_ref: str, threshold: int = 80) -> Dict[str, Any]:
        """GET the candidate match summary for a job (by its jobCode / externalRef).
        Raises httpx.HTTPStatusError on non-2xx (e.g. 404 when the job isn't in RP yet)."""
        url = f"{self.base_url}/api/v1/jobs/by-code/{external_ref}/match-summary"
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.get(url, params={"threshold": threshold}, headers=self._headers())
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


# ── Shared push helpers (used by the endpoint AND the on-reply auto-push) ──

def _pick_contact(db, lead_id: int, tenant_id: Optional[int]):
    """Best client-side contact for the lead: a Valid-email POC first, else any."""
    from app.db.models.contact import ContactDetails
    q = db.query(ContactDetails).filter(ContactDetails.lead_id == lead_id)
    if tenant_id is not None:
        q = q.filter(ContactDetails.tenant_id == tenant_id)
    contacts = q.all()
    if not contacts:
        return None
    valid = [c for c in contacts if (c.validation_status or "").lower() == "valid" and c.email]
    return (valid or contacts)[0]


def _log_event(db, tenant_id, description: str, status: str = "success") -> None:
    from app.db.models.automation_event import AutomationEvent
    try:
        db.add(AutomationEvent(tenant_id=tenant_id or 1, event_type="resource_pool_push",
                               source="api", title=description[:255], status=status))
        db.commit()
    except Exception:  # logging must never break the caller
        db.rollback()


def push_lead_by_id(db, lead_id: int, tenant_id: Optional[int] = None, stage: str = "LEAD") -> Optional[Dict[str, Any]]:
    """Load a lead (+ its company/contact), push it to Resource Pool and record the
    RP ids back on the lead's ``metadata_json`` (cross-system id map).

    Returns the RP response dict, or ``None`` when the integration is not configured.
    Raises ``LookupError`` if the lead does not exist; httpx errors propagate.
    """
    from app.db.models.lead import LeadDetails
    from app.db.models.client import ClientInfo

    client = ResourcePoolClient.from_settings(db, tenant_id=tenant_id)
    if client is None:
        return None

    lq = db.query(LeadDetails).filter(LeadDetails.lead_id == lead_id)
    if tenant_id is not None:
        lq = lq.filter(LeadDetails.tenant_id == tenant_id)
    lead = lq.first()
    if not lead:
        raise LookupError(f"lead {lead_id} not found")

    company = None
    if lead.client_name:
        cq = db.query(ClientInfo).filter(ClientInfo.client_name == lead.client_name)
        if tenant_id is not None:
            cq = cq.filter(ClientInfo.tenant_id == tenant_id)
        company = cq.first()

    contact = _pick_contact(db, lead_id, tenant_id)
    payload = build_lead_payload(lead, company=company, contact=contact, stage=stage)
    rp = client.push_lead(payload)

    try:
        meta = json.loads(lead.metadata_json) if lead.metadata_json else {}
        if not isinstance(meta, dict):
            meta = {}
    except (ValueError, TypeError):
        meta = {}
    meta["resource_pool"] = {
        "external_ref": payload["externalRef"],
        "job_id": rp.get("jobId"), "company_id": rp.get("companyId"),
        "contact_id": rp.get("contactId"), "opportunity_id": rp.get("opportunityId"),
        "stage": payload["opportunity"]["stage"],
    }
    lead.metadata_json = json.dumps(meta)
    db.commit()
    return rp


def auto_push_lead_on_interested_reply(db, contact, tenant_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Best-effort hand-off to Resource Pool when a client reply is 'interested'.

    No-op (returns None) when: disabled via ``resourcepool_auto_push_on_reply``,
    the integration is unconfigured, the contact has no linked lead, or the push
    fails. NEVER raises — inbound reply processing must not break.
    """
    if contact is None:
        return None
    tid = tenant_id if tenant_id is not None else getattr(contact, "tenant_id", None)
    if not get_tenant_setting_bool(db, "resourcepool_auto_push_on_reply", tenant_id=tid, default=True):
        return None
    lead_id = getattr(contact, "lead_id", None)
    if not lead_id:
        return None
    try:
        rp = push_lead_by_id(db, lead_id, tenant_id=tid, stage="QUALIFIED")
        if rp:
            _log_event(db, tid, f"Handed lead {lead_id} to Resource Pool on interested reply "
                                f"(opportunity {rp.get('opportunityId')}, job {rp.get('jobId')})")
        return rp
    except Exception as e:  # noqa: BLE001 — best-effort, never break inbox sync
        try:
            db.rollback()
        except Exception:
            pass
        _log_event(db, tid, f"Resource Pool auto-push failed for lead {lead_id}: {str(e)[:200]}", status="error")
        logger.warning("Resource Pool auto-push failed for lead %s: %s", lead_id, e)
        return None
