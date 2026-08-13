"""Lead management endpoints."""
import csv
import io
import re
import logging
from typing import Optional, List, Literal
from datetime import date, datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File, BackgroundTasks, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, asc, desc, or_, and_, case

from app.api.deps import get_db, get_current_active_user, require_role, get_current_tenant_id, require_tenant_id
from app.api.deps.plan_limits import check_plan_limit
from app.db.query_helpers import (
    tenant_filter, SIZE_OPERATORS, effective_size_expr, size_operator_clause,
    effective_salary_bounds, salary_operator_clause,
)
from app.utils.text_filter import text_filter_from_params
from app.db.models.user import User, UserRole
from app.db.models.lead import LeadDetails, LeadStatus, CLOSED_STATUSES
from app.db.models.client import ClientInfo
from app.db.models.contact import ContactDetails
from app.db.models.lead_contact import LeadContactAssociation
from app.db.models.outreach import OutreachEvent, OutreachStatus
from app.db.models.inbox_message import InboxMessage, MessageDirection
from app.schemas.lead import LeadCreate, LeadUpdate, LeadResponse, LeadListResponse
from app.schemas.contact import ContactResponse
from app.schemas.outreach import OutreachEventResponse
from app.core.state_machine import validate_transition, get_allowed_transitions
from app.db.models.audit_log import AuditLog
from app.schemas.pipeline import BulkLeadIdsRequest, BulkLeadStatusRequest, BulkEnrichRequest, BulkOutreachRequest, ManageContactsRequest
import json

logger = logging.getLogger(__name__)


class GoogleSheetRequest(BaseModel):
    sheet_url: str
    skip_duplicates: bool = True

router = APIRouter(prefix="/leads", tags=["Leads"])


def _audit(db: Session, entity_type: str, entity_id: int, action: str,
           changed_fields: dict | None = None, changed_by: str | None = None, notes: str | None = None,
           tenant_id: int = 1):
    """Write an audit log entry."""
    log = AuditLog(
        tenant_id=tenant_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        changed_fields=json.dumps(changed_fields) if changed_fields else None,
        changed_by=changed_by,
        notes=notes,
    )
    db.add(log)

# Valid sort columns
SORT_COLUMNS = {
    "lead_id": LeadDetails.lead_id,
    "client_name": LeadDetails.client_name,
    "job_title": LeadDetails.job_title,
    "state": LeadDetails.state,
    "posting_date": LeadDetails.posting_date,
    "created_at": LeadDetails.created_at,
    "source": LeadDetails.source,
    "employment_type": LeadDetails.employment_type,
    "lead_status": LeadDetails.lead_status,
    "run_id": LeadDetails.run_id,
    "downloaded_at": LeadDetails.downloaded_at,
    "lob_id": LeadDetails.lob_id,
}

# Maps campaign lifecycle status -> user-facing "Mailing-Status" label.
_MAILING_STATUS_BY_CAMPAIGN = {
    "active": "Campaign-Active",
    "paused": "Campaign-Paused",
    "draft": "Campaign-Draft",
    "completed": "Campaign-Closed",
}


def mailing_status_label(campaign_status: Optional[str], downloaded_at) -> str:
    """Derive the lead's Mailing-Status from its campaign enrollment + download flag.

    A campaign-enrolled lead reflects the campaign's lifecycle; an un-enrolled lead
    that was exported/downloaded is treated as mailed offline; everything else is
    not yet mailed.
    """
    if campaign_status in _MAILING_STATUS_BY_CAMPAIGN:
        return _MAILING_STATUS_BY_CAMPAIGN[campaign_status]
    if downloaded_at is not None:
        return "Mailed-Offline"
    return "Not-Mailed"


# Response-column rollup: one lead has many contacts, each contact's inbound reply
# is classified on InboxMessage.category. We roll those up to a single lead-level
# label using a POSITIVE-FIRST precedence (an "interested" reply from ANY contact
# makes the whole lead "Interested"), because interested leads are the worklist RAs
# prioritize for candidate matching. Lower rank wins.
_RESPONSE_CATEGORY_PRIORITY = {
    "interested": 0,
    "referral": 1,
    "question": 2,
    "not_interested": 3,
    "do_not_contact": 4,
    "ooo": 5,
    "other": 6,
}
_RESPONSE_CATEGORY_LABEL = {
    "interested": "Interested",
    "referral": "Referral",
    "question": "Question",
    "not_interested": "Not-Interested",
    "do_not_contact": "Do-Not-Contact",
    "ooo": "OOO",
    "other": "Other",
}
# All classifiable categories, used by the filter to exclude "usable classification".
_RESPONSE_ALL_CATEGORIES = tuple(_RESPONSE_CATEGORY_LABEL.keys())


def response_status_label(best_category: Optional[str], has_reply: bool, has_outreach: bool) -> str:
    """Derive the lead-level Response label from its best (highest-precedence)
    classified reply category plus whether any reply / any outreach exists.

    Falls through classified category -> generic replied -> awaiting -> never contacted.
    """
    if best_category in _RESPONSE_CATEGORY_LABEL:
        return _RESPONSE_CATEGORY_LABEL[best_category]
    if has_reply:
        return "Replied"
    if has_outreach:
        return "No-Response"
    return "Not-Contacted"


# Values an RA may set by hand (bulk-update modal) for Mailed-Offline leads — leads
# with no campaign / inbox reply to derive from. A set override wins over the derived
# value everywhere (display, export, filter, sort).
MAILING_STATUS_OVERRIDE_OPTIONS = [
    "Not-Mailed", "Mailed-Offline", "Follow-Up-Sent", "Bounced", "No-Valid-Email",
]
RESPONSE_STATUS_OVERRIDE_OPTIONS = [
    "Interested", "Referral", "Question", "Not-Interested", "Do-Not-Contact", "OOO", "Other",
]
# Sort ordinals over the full Mailing-Status label space (derived + override-only labels).
_MAILING_SORT_ORDINAL = {
    "Campaign-Active": 0, "Campaign-Paused": 1, "Campaign-Draft": 2, "Campaign-Closed": 3,
    "Mailed-Offline": 4, "Follow-Up-Sent": 5, "Bounced": 6, "No-Valid-Email": 7, "Not-Mailed": 8,
}
# Response override label -> the same ordinal used for reply categories (0..6).
_RESPONSE_OVERRIDE_ORDINAL = {
    "Interested": 0, "Referral": 1, "Question": 2, "Not-Interested": 3,
    "Do-Not-Contact": 4, "OOO": 5, "Other": 6,
}


def effective_mailing_status(lead, campaign_status) -> str:
    """Override wins; otherwise the campaign/download-derived Mailing-Status."""
    return getattr(lead, "mailing_status_override", None) or mailing_status_label(
        campaign_status, lead.downloaded_at
    )


def effective_response_status(lead, best_category, has_reply, has_outreach) -> str:
    """Override wins; otherwise the reply-rollup-derived Response."""
    return getattr(lead, "response_status_override", None) or response_status_label(
        best_category, has_reply, has_outreach
    )


def _response_rollup_for_leads(db, lead_ids, tenant_id):
    """Batch-derive the Response inputs for a set of lead_ids (no N+1).

    Returns ``(category_map, replied_ids, outreach_ids)`` where ``category_map``
    holds each lead's best (highest-precedence) classified reply category, and the
    two sets flag leads with any reply / any outreach. Shared by the list view and
    the CSV export so both stay WYSIWYG.
    """
    category_map: dict[int, str] = {}
    replied_ids: set[int] = set()
    outreach_ids: set[int] = set()
    if not lead_ids:
        return category_map, replied_ids, outreach_ids

    # (A) Classified replies: RECEIVED InboxMessage.category, attributed to the lead
    #     the outreach was sent for via outreach_event_id -> OutreachEvent.lead_id.
    reply_q = db.query(OutreachEvent.lead_id, InboxMessage.category).join(
        InboxMessage, InboxMessage.outreach_event_id == OutreachEvent.event_id
    ).filter(
        OutreachEvent.lead_id.in_(lead_ids),
        InboxMessage.direction == MessageDirection.RECEIVED,
        InboxMessage.is_deleted == False,
        InboxMessage.category.isnot(None),
    )
    if tenant_id is not None:
        reply_q = reply_q.filter(OutreachEvent.tenant_id == tenant_id)
    for lid, cat in reply_q.all():
        if lid is None:
            continue
        replied_ids.add(lid)
        existing = category_map.get(lid)
        if existing is None or _RESPONSE_CATEGORY_PRIORITY.get(cat, 99) < _RESPONSE_CATEGORY_PRIORITY.get(existing, 99):
            category_map[lid] = cat

    # (B)+(C) Any outreach at all, plus reply-detected (status REPLIED) — one pass.
    ev_q = db.query(OutreachEvent.lead_id, OutreachEvent.status).filter(
        OutreachEvent.lead_id.in_(lead_ids)
    )
    if tenant_id is not None:
        ev_q = ev_q.filter(OutreachEvent.tenant_id == tenant_id)
    for lid, ev_status in ev_q.all():
        if lid is None:
            continue
        outreach_ids.add(lid)
        status_val = ev_status.value if hasattr(ev_status, 'value') else ev_status
        if status_val == OutreachStatus.REPLIED.value:
            replied_ids.add(lid)

    return category_map, replied_ids, outreach_ids


def _campaign_fields_for_lead(db, lead):
    """Return (campaign_status, campaign_id, mailing_status) for a single lead.

    Mirrors the batch logic in ``list_leads``: pick the highest-priority active
    campaign the lead is enrolled in (archived campaigns excluded).
    """
    from app.db.models.campaign import Campaign as _Camp, CampaignContact as _CC
    _priority = {'active': 0, 'paused': 1, 'draft': 2, 'completed': 3}
    rows = db.query(_CC.lead_id, _Camp.status, _Camp.campaign_id).join(
        _Camp, _CC.campaign_id == _Camp.campaign_id
    ).filter(
        _CC.lead_id == lead.lead_id,
        _Camp.is_archived == False,
    ).all()
    best_status, best_id = None, None
    for _lid, cstatus, cid in rows:
        cstatus_val = cstatus.value if hasattr(cstatus, 'value') else cstatus
        if best_status is None or _priority.get(cstatus_val, 99) < _priority.get(best_status, 99):
            best_status, best_id = cstatus_val, cid
    return best_status, best_id, mailing_status_label(best_status, lead.downloaded_at)


def _apply_lead_filters(
    query,
    db: Session,
    tenant_id: Optional[int],
    *,
    status: Optional[str] = None,
    source: Optional[str] = None,
    state: Optional[List[str]] = None,
    client_name: Optional[str] = None,
    job_title: Optional[str] = None,
    industry: Optional[List[str]] = None,
    company_size_op: Optional[str] = None,
    company_size_value: Optional[int] = None,
    company_size_value2: Optional[int] = None,
    company_size_include_unknown: bool = False,
    salary_op: Optional[str] = None,
    salary_value: Optional[int] = None,
    salary_value2: Optional[int] = None,
    salary_include_unknown: bool = False,
    data_type: Optional[str] = None,
    employment_type: Optional[List[str]] = None,
    exclude_keywords: Optional[List[str]] = None,
    title: Optional[List[str]] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    extracted_from: Optional[date] = None,
    extracted_to: Optional[date] = None,
    downloaded: Optional[str] = None,
    mailing_status: Optional[str] = None,
    response_status: Optional[str] = None,
    lob_id: Optional[int] = None,
    search: Optional[str] = None,
    show_archived: bool = False,
    text_params=None,
):
    """Apply the shared Leads list/export WHERE filters to ``query``.

    Single source of truth for both ``list_leads`` (query params) and the CSV
    export (JSON body), so an export always matches exactly what the list shows.
    ``text_params`` is a Mapping used by the Excel-style text filters — either
    ``request.query_params`` (GET) or ``body.model_dump()`` (POST). Sorting,
    pagination and counts stay with the caller.
    """
    text_params = text_params if text_params is not None else {}

    if show_archived:
        query = query.filter(LeadDetails.is_archived == True)
    else:
        query = query.filter(LeadDetails.is_archived == False)

    if status:
        if status.startswith('campaign_'):
            # Filter leads enrolled in campaigns with this status
            camp_status_val = status.replace('campaign_', '')
            from app.db.models.campaign import Campaign as _Camp, CampaignContact as _CC
            camp_lead_ids_sq = db.query(_CC.lead_id).join(
                _Camp, _CC.campaign_id == _Camp.campaign_id
            ).filter(
                _CC.lead_id.isnot(None),
                _Camp.status == camp_status_val,
                _Camp.is_archived == False,
            ).distinct().subquery()
            query = query.filter(LeadDetails.lead_id.in_(db.query(camp_lead_ids_sq)))
        else:
            query = query.filter(LeadDetails.lead_status == status)

    # Mailing-Status filter — mirrors the derived column (mailing_status_label).
    # Priority active > paused > draft > completed, so e.g. "Campaign-Paused"
    # means the lead's *best* campaign status is paused (not also active).
    if mailing_status:
        from app.db.models.campaign import Campaign as _Camp, CampaignContact as _CC

        def _ids_in(*statuses):
            return db.query(_CC.lead_id).join(
                _Camp, _CC.campaign_id == _Camp.campaign_id
            ).filter(
                _CC.lead_id.isnot(None),
                _Camp.is_archived == False,
                _Camp.status.in_(statuses),
            ).distinct()

        # Override wins over the derived label: a lead matches L if override==L, or
        # (override is null AND the derived condition holds). Override-only labels
        # (Follow-Up-Sent/Bounced/No-Valid-Email) match on the override alone.
        _ovr = LeadDetails.mailing_status_override
        _no_ovr = _ovr.is_(None)
        ms = mailing_status
        if ms == "Campaign-Active":
            query = query.filter(_no_ovr, LeadDetails.lead_id.in_(_ids_in("active")))
        elif ms == "Campaign-Paused":
            query = query.filter(
                _no_ovr,
                LeadDetails.lead_id.in_(_ids_in("paused")),
                ~LeadDetails.lead_id.in_(_ids_in("active")),
            )
        elif ms == "Campaign-Draft":
            query = query.filter(
                _no_ovr,
                LeadDetails.lead_id.in_(_ids_in("draft")),
                ~LeadDetails.lead_id.in_(_ids_in("active", "paused")),
            )
        elif ms == "Campaign-Closed":
            query = query.filter(
                _no_ovr,
                LeadDetails.lead_id.in_(_ids_in("completed")),
                ~LeadDetails.lead_id.in_(_ids_in("active", "paused", "draft")),
            )
        elif ms == "Mailed-Offline":
            query = query.filter(or_(
                _ovr == "Mailed-Offline",
                and_(
                    _no_ovr,
                    ~LeadDetails.lead_id.in_(_ids_in("active", "paused", "draft", "completed")),
                    LeadDetails.downloaded_at.isnot(None),
                ),
            ))
        elif ms == "Not-Mailed":
            query = query.filter(or_(
                _ovr == "Not-Mailed",
                and_(
                    _no_ovr,
                    ~LeadDetails.lead_id.in_(_ids_in("active", "paused", "draft", "completed")),
                    LeadDetails.downloaded_at.is_(None),
                ),
            ))
        elif ms in ("Follow-Up-Sent", "Bounced", "No-Valid-Email"):
            query = query.filter(_ovr == ms)

    # Response filter — mirrors the derived Response column (response_status_label).
    # A classified label (e.g. "Referral") means the lead's *best* reply category is
    # that one, so higher-precedence categories are excluded (positive-first rollup).
    if response_status:
        def _cat_ids(*cats):
            """Lead ids that have >=1 received, classified reply in `cats`."""
            q = db.query(OutreachEvent.lead_id).join(
                InboxMessage, InboxMessage.outreach_event_id == OutreachEvent.event_id
            ).filter(
                OutreachEvent.lead_id.isnot(None),
                InboxMessage.direction == MessageDirection.RECEIVED,
                InboxMessage.is_deleted == False,
                InboxMessage.category.in_(cats),
            )
            if tenant_id is not None:
                q = q.filter(OutreachEvent.tenant_id == tenant_id)
            return q.distinct()

        def _replied_ids():
            """Lead ids with a reply detected (status REPLIED)."""
            q = db.query(OutreachEvent.lead_id).filter(
                OutreachEvent.lead_id.isnot(None),
                OutreachEvent.status == OutreachStatus.REPLIED,
            )
            if tenant_id is not None:
                q = q.filter(OutreachEvent.tenant_id == tenant_id)
            return q.distinct()

        def _outreach_ids():
            """Lead ids with any outreach event at all."""
            q = db.query(OutreachEvent.lead_id).filter(OutreachEvent.lead_id.isnot(None))
            if tenant_id is not None:
                q = q.filter(OutreachEvent.tenant_id == tenant_id)
            return q.distinct()

        # Override wins over the derived rollup: match override==L, or (override null
        # AND derived condition). The auto-only labels (Replied/No-Response/Not-Contacted)
        # only apply when there is no override.
        _rovr = LeadDetails.response_status_override
        _rno = _rovr.is_(None)
        rs = response_status
        if rs == "Interested":
            query = query.filter(or_(
                _rovr == "Interested",
                and_(_rno, LeadDetails.lead_id.in_(_cat_ids("interested"))),
            ))
        elif rs == "Referral":
            query = query.filter(or_(
                _rovr == "Referral",
                and_(_rno,
                     LeadDetails.lead_id.in_(_cat_ids("referral")),
                     ~LeadDetails.lead_id.in_(_cat_ids("interested"))),
            ))
        elif rs == "Question":
            query = query.filter(or_(
                _rovr == "Question",
                and_(_rno,
                     LeadDetails.lead_id.in_(_cat_ids("question")),
                     ~LeadDetails.lead_id.in_(_cat_ids("interested", "referral"))),
            ))
        elif rs == "Not-Interested":
            query = query.filter(or_(
                _rovr == "Not-Interested",
                and_(_rno,
                     LeadDetails.lead_id.in_(_cat_ids("not_interested")),
                     ~LeadDetails.lead_id.in_(_cat_ids("interested", "referral", "question"))),
            ))
        elif rs == "Do-Not-Contact":
            query = query.filter(or_(
                _rovr == "Do-Not-Contact",
                and_(_rno,
                     LeadDetails.lead_id.in_(_cat_ids("do_not_contact")),
                     ~LeadDetails.lead_id.in_(_cat_ids("interested", "referral", "question", "not_interested"))),
            ))
        elif rs == "OOO":
            query = query.filter(or_(
                _rovr == "OOO",
                and_(_rno,
                     LeadDetails.lead_id.in_(_cat_ids("ooo")),
                     ~LeadDetails.lead_id.in_(_cat_ids("interested", "referral", "question", "not_interested", "do_not_contact"))),
            ))
        elif rs == "Other":
            query = query.filter(or_(
                _rovr == "Other",
                and_(_rno,
                     LeadDetails.lead_id.in_(_cat_ids("other")),
                     ~LeadDetails.lead_id.in_(_cat_ids("interested", "referral", "question", "not_interested", "do_not_contact", "ooo"))),
            ))
        elif rs == "Replied":
            # Reply detected but no usable classification (and not overridden).
            query = query.filter(
                _rno,
                LeadDetails.lead_id.in_(_replied_ids()),
                ~LeadDetails.lead_id.in_(_cat_ids(*_RESPONSE_ALL_CATEGORIES)),
            )
        elif rs == "No-Response":
            query = query.filter(
                _rno,
                LeadDetails.lead_id.in_(_outreach_ids()),
                ~LeadDetails.lead_id.in_(_replied_ids()),
                ~LeadDetails.lead_id.in_(_cat_ids(*_RESPONSE_ALL_CATEGORIES)),
            )
        elif rs == "Not-Contacted":
            query = query.filter(_rno, ~LeadDetails.lead_id.in_(_outreach_ids()))

    if source:
        query = query.filter(LeadDetails.source == source)
    if state:
        query = query.filter(LeadDetails.state.in_(state))
    if client_name:
        query = query.filter(LeadDetails.client_name.ilike(f"%{client_name}%"))
    if job_title:
        query = query.filter(LeadDetails.job_title.ilike(f"%{job_title}%"))

    # Filter by industry/company_size — check both lead_details and client_info
    if industry:
        client_q = db.query(ClientInfo.client_name).filter(ClientInfo.industry.in_(industry))
        matching_names = [r[0] for r in client_q.all()]
        query = query.filter(
            (LeadDetails.industry.in_(industry)) |
            (LeadDetails.client_name.in_(matching_names) if matching_names else False)
        )
    if company_size_op in SIZE_OPERATORS and company_size_value is not None:
        # Effective numeric size: a lead's own parsed company_size wins; when it
        # is unknown, fall back to its client's authoritative size (employee_count
        # or parsed band) — mirroring the display COALESCE precedence.
        lead_expr = effective_size_expr(LeadDetails.company_size)
        client_expr = effective_size_expr(ClientInfo.company_size, ClientInfo.employee_count)

        lead_clause = size_operator_clause(lead_expr, company_size_op, company_size_value, company_size_value2)
        client_clause = size_operator_clause(client_expr, company_size_op, company_size_value, company_size_value2)

        conditions = []
        if lead_clause is not None:
            conditions.append(lead_clause)
            if client_clause is not None:
                cq = tenant_filter(
                    db.query(ClientInfo.client_name).filter(client_clause), ClientInfo, tenant_id
                )
                client_match_names = [r[0] for r in cq.all()]
                if client_match_names:
                    # Defer to the client's size only when the lead's own is unknown.
                    conditions.append(and_(lead_expr.is_(None), LeadDetails.client_name.in_(client_match_names)))

        if company_size_include_unknown:
            # Lead size unknown AND its client has no known size either.
            known_client_q = tenant_filter(
                db.query(ClientInfo.client_name).filter(client_expr.isnot(None)), ClientInfo, tenant_id
            )
            known_client_names = [r[0] for r in known_client_q.all()]
            unknown_cond = lead_expr.is_(None)
            if known_client_names:
                unknown_cond = and_(unknown_cond, ~LeadDetails.client_name.in_(known_client_names))
            conditions.append(unknown_cond)

        if conditions:
            query = query.filter(or_(*conditions))
    if salary_op in SIZE_OPERATORS and salary_value is not None:
        # Range-aware: compare against the lead's salary_min/salary_max band.
        sal_lo, sal_hi = effective_salary_bounds(LeadDetails.salary_min, LeadDetails.salary_max)
        clause = salary_operator_clause(sal_lo, sal_hi, salary_op, salary_value, salary_value2)
        if clause is not None:
            if salary_include_unknown:
                clause = or_(clause, sal_lo.is_(None))
            query = query.filter(clause)
    if data_type:
        query = query.filter(LeadDetails.data_type == data_type)
    if employment_type:
        query = query.filter(LeadDetails.employment_type.in_(employment_type))

    if exclude_keywords:
        excl_conditions = [LeadDetails.job_title.ilike(f"%{kw}%") for kw in exclude_keywords]
        excl_conditions += [LeadDetails.client_name.ilike(f"%{kw}%") for kw in exclude_keywords]
        query = query.filter(~or_(*excl_conditions))

    if title:
        query = query.filter(or_(*[LeadDetails.job_title.ilike(f"%{t}%") for t in title]))

    # ── Excel-style "Text Filters" (Equals / Contains / Begins With / … / Custom) ──
    # Server-side predicates so they work even when the typed text isn't a known
    # checklist value. Industry also spans the client_info firmographics.
    qp = text_params
    title_tc = text_filter_from_params(qp, "title", LeadDetails.job_title)
    if title_tc is not None:
        query = query.filter(title_tc)
    company_tc = text_filter_from_params(qp, "company", LeadDetails.client_name)
    if company_tc is not None:
        query = query.filter(company_tc)
    emp_tc = text_filter_from_params(qp, "employment_type", LeadDetails.employment_type)
    if emp_tc is not None:
        query = query.filter(emp_tc)
    ind_tc = text_filter_from_params(qp, "industry", LeadDetails.industry)
    if ind_tc is not None:
        client_ind_tc = text_filter_from_params(qp, "industry", ClientInfo.industry)
        cq = tenant_filter(db.query(ClientInfo.client_name).filter(client_ind_tc), ClientInfo, tenant_id)
        match_names = [r[0] for r in cq.all()]
        query = query.filter(or_(ind_tc, LeadDetails.client_name.in_(match_names) if match_names else False))

    if from_date:
        query = query.filter(LeadDetails.posting_date >= from_date)
    if to_date:
        query = query.filter(LeadDetails.posting_date <= to_date)
    if extracted_from:
        query = query.filter(func.date(LeadDetails.created_at) >= extracted_from)
    if extracted_to:
        query = query.filter(func.date(LeadDetails.created_at) <= extracted_to)
    if downloaded:
        if downloaded.lower() == 'yes':
            query = query.filter(LeadDetails.downloaded_at.isnot(None))
        elif downloaded.lower() == 'no':
            query = query.filter(LeadDetails.downloaded_at.is_(None))
    if lob_id is not None:
        query = query.filter(LeadDetails.lob_id == lob_id)
    if search:
        # Support searching by numeric ID, run ID, or campaign ID
        # (e.g. "42", "#42", "R42", "run:42", "campaign:42", "c:42").
        from app.db.models.campaign import CampaignContact as _CCSearch
        search_l = search.lower().strip()
        search_stripped = search.lstrip('#').strip()
        camp_prefix = search_l.startswith('campaign:') or search_l.startswith('c:')
        camp_num = search.split(':', 1)[1].strip() if (camp_prefix and ':' in search) else None
        run_prefix = search_l.startswith('r') or search_l.startswith('run:')
        run_num = search.lstrip('rRunRUN:').strip() if (run_prefix and not camp_prefix) else None

        def _campaign_lead_ids(cid):
            return db.query(_CCSearch.lead_id).filter(
                _CCSearch.campaign_id == cid, _CCSearch.lead_id.isnot(None)
            ).distinct()

        if camp_num and camp_num.isdigit():
            query = query.filter(LeadDetails.lead_id.in_(_campaign_lead_ids(int(camp_num))))
        elif run_num and run_num.isdigit():
            query = query.filter(LeadDetails.run_id == int(run_num))
        elif search_stripped.isdigit():
            # Plain number — match lead_id, run_id, or the associated campaign_id
            num_val = int(search_stripped)
            query = query.filter(
                (LeadDetails.lead_id == num_val) |
                (LeadDetails.run_id == num_val) |
                (LeadDetails.lead_id.in_(_campaign_lead_ids(num_val)))
            )
        else:
            # Find lead IDs that have contacts matching the search email
            contact_lead_ids = db.query(LeadContactAssociation.lead_id).join(
                ContactDetails, ContactDetails.contact_id == LeadContactAssociation.contact_id
            ).filter(ContactDetails.email.ilike(f"%{search}%")).distinct()

            query = query.filter(
                (LeadDetails.client_name.ilike(f"%{search}%")) |
                (LeadDetails.job_title.ilike(f"%{search}%")) |
                (LeadDetails.state.ilike(f"%{search}%")) |
                (LeadDetails.lead_id.in_(contact_lead_ids))
            )

    return query


@router.get("", response_model=LeadListResponse)
async def list_leads(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    limit: Optional[int] = Query(None, ge=1, le=500),
    status: Optional[str] = Query(None, description="Lead status or campaign_* prefix for campaign statuses"),
    source: Optional[str] = None,
    state: Optional[List[str]] = Query(None),
    client_name: Optional[str] = None,
    job_title: Optional[str] = None,
    industry: Optional[List[str]] = Query(None),
    company_size_op: Optional[str] = Query(None, description="Numeric size operator: eq, ne, lt, lte, gt, gte, between"),
    company_size_value: Optional[int] = Query(None, ge=0, description="Employee-count comparison value"),
    company_size_value2: Optional[int] = Query(None, ge=0, description="Upper bound for the 'between' operator"),
    company_size_include_unknown: bool = Query(False, description="Include leads with unknown size when a size filter is active"),
    salary_op: Optional[str] = Query(None, description="Numeric salary operator: eq, ne, lt, lte, gt, gte, between (range-aware)"),
    salary_value: Optional[int] = Query(None, ge=0, description="Salary comparison value"),
    salary_value2: Optional[int] = Query(None, ge=0, description="Upper bound for the 'between' salary operator"),
    salary_include_unknown: bool = Query(False, description="Include leads with unknown salary when a salary filter is active"),
    data_type: Optional[str] = Query(None, description="Filter by data type: 'test' or 'prod'"),
    employment_type: Optional[List[str]] = Query(None, description="Position type filter (e.g. Full-time, Contract)"),
    exclude_keywords: Optional[List[str]] = Query(None, description="Exclude leads matching these keywords in title/company"),
    title: Optional[List[str]] = Query(None, description="Include leads matching these job titles"),
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    extracted_from: Optional[date] = Query(None, description="Filter leads extracted (created) on or after this date"),
    extracted_to: Optional[date] = Query(None, description="Filter leads extracted (created) on or before this date"),
    downloaded: Optional[str] = Query(None, description="Filter by downloaded status: 'yes' or 'no'"),
    mailing_status: Optional[str] = Query(None, description="Filter by Mailing-Status label (e.g. Campaign-Active, Mailed-Offline, Not-Mailed)"),
    response_status: Optional[str] = Query(None, description="Filter by Response label (e.g. Interested, No-Response, Not-Contacted)"),
    lob_id: Optional[int] = Query(None, description="Filter by Line of Business ID"),
    search: Optional[str] = None,
    sort_by: Optional[str] = Query("created_at", description="Column to sort by"),
    sort_order: Optional[Literal["asc", "desc"]] = Query("desc", description="Sort direction"),
    show_archived: bool = Query(False, description="Include archived leads"),
    request: Request = None,  # type: ignore[assignment]
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """List leads with filtering, sorting, and pagination."""
    if limit:
        page_size = limit

    query = db.query(LeadDetails)
    query = tenant_filter(query, LeadDetails, tenant_id)

    query = _apply_lead_filters(
        query, db, tenant_id,
        status=status, source=source, state=state,
        client_name=client_name, job_title=job_title, industry=industry,
        company_size_op=company_size_op, company_size_value=company_size_value,
        company_size_value2=company_size_value2,
        company_size_include_unknown=company_size_include_unknown,
        salary_op=salary_op, salary_value=salary_value, salary_value2=salary_value2,
        salary_include_unknown=salary_include_unknown,
        data_type=data_type, employment_type=employment_type,
        exclude_keywords=exclude_keywords, title=title,
        from_date=from_date, to_date=to_date,
        extracted_from=extracted_from, extracted_to=extracted_to,
        downloaded=downloaded, mailing_status=mailing_status,
        response_status=response_status,
        lob_id=lob_id, search=search,
        show_archived=show_archived,
        text_params=request.query_params,
    )

    total = query.count()

    # Total lead-contact associations across ALL filtered leads (not just current page).
    # Counts each (lead, contact) pair separately — e.g. one contact linked to 3 leads = 3.
    filtered_lead_ids = query.with_entities(LeadDetails.lead_id)
    total_contact_associations = db.query(
        func.count(LeadContactAssociation.contact_id)
    ).filter(
        LeadContactAssociation.lead_id.in_(filtered_lead_ids)
    ).scalar() or 0

    if sort_by == "contact_count":
        # Subquery: count distinct contacts per lead from junction table
        count_sub = db.query(
            LeadContactAssociation.lead_id.label("lead_id"),
            func.count(func.distinct(LeadContactAssociation.contact_id)).label("cnt")
        ).group_by(LeadContactAssociation.lead_id).subquery()

        query = query.outerjoin(count_sub, LeadDetails.lead_id == count_sub.c.lead_id)
        count_expr = func.coalesce(count_sub.c.cnt, 0)

        if sort_order == "asc":
            query = query.order_by(asc(count_expr))
        else:
            query = query.order_by(desc(count_expr))
    elif sort_by in ("industry", "company_size"):
        # Sort by client_info columns via subquery JOIN
        ci_col = ClientInfo.industry if sort_by == "industry" else ClientInfo.company_size
        ci_sub = db.query(ClientInfo.client_name, ci_col.label("sort_val")).subquery()
        query = query.outerjoin(ci_sub, LeadDetails.client_name == ci_sub.c.client_name)
        sort_expr = func.coalesce(ci_sub.c.sort_val, "")
        if sort_order == "asc":
            query = query.order_by(asc(sort_expr))
        else:
            query = query.order_by(desc(sort_expr))
    elif sort_by in ("mailing_status", "campaign_id"):
        # Both derive from the lead's best (highest-priority) non-archived campaign.
        from app.db.models.campaign import Campaign as _Camp, CampaignContact as _CC
        _pri = case(
            (_Camp.status == "active", 0),
            (_Camp.status == "paused", 1),
            (_Camp.status == "draft", 2),
            (_Camp.status == "completed", 3),
            else_=99,
        )
        if sort_by == "mailing_status":
            # Order by an ordinal mirroring mailing_status_label precedence:
            # Campaign-Active(0)..Campaign-Closed(3) < Mailed-Offline(4) < Not-Mailed(5).
            camp_pri_sub = db.query(
                _CC.lead_id.label("lead_id"),
                func.min(_pri).label("best_pri"),
            ).join(_Camp, _CC.campaign_id == _Camp.campaign_id).filter(
                _CC.lead_id.isnot(None),
                _Camp.is_archived == False,
            ).group_by(_CC.lead_id).subquery()
            query = query.outerjoin(camp_pri_sub, LeadDetails.lead_id == camp_pri_sub.c.lead_id)
            # Override wins (incl. offline-only labels); else campaign(0-3)/offline(4)/not-mailed(8).
            mailing_ord = case(
                (LeadDetails.mailing_status_override == "Not-Mailed", 8),
                (LeadDetails.mailing_status_override == "Mailed-Offline", 4),
                (LeadDetails.mailing_status_override == "Follow-Up-Sent", 5),
                (LeadDetails.mailing_status_override == "Bounced", 6),
                (LeadDetails.mailing_status_override == "No-Valid-Email", 7),
                (camp_pri_sub.c.best_pri.isnot(None), camp_pri_sub.c.best_pri),
                (LeadDetails.downloaded_at.isnot(None), 4),
                else_=8,
            )
            primary = asc(mailing_ord) if sort_order == "asc" else desc(mailing_ord)
        else:
            # campaign_id: the displayed id is the best-priority campaign's id.
            best_campaign_id = db.query(_Camp.campaign_id).join(
                _CC, _CC.campaign_id == _Camp.campaign_id
            ).filter(
                _CC.lead_id == LeadDetails.lead_id,
                _Camp.is_archived == False,
            ).order_by(_pri.asc(), _Camp.campaign_id.asc()).limit(1).correlate(LeadDetails).scalar_subquery()
            # Leads with no campaign sort last in both directions.
            if sort_order == "asc":
                primary = asc(func.coalesce(best_campaign_id, 2147483647))
            else:
                primary = desc(func.coalesce(best_campaign_id, -1))
        query = query.order_by(primary, LeadDetails.lead_id.asc())
    elif sort_by == "response_status":
        # Order by an ordinal mirroring response_status_label precedence:
        # Interested(0)..Other(6) < Replied(7) < No-Response(8) < Not-Contacted(9).
        _cat_ord = case(
            (InboxMessage.category == "interested", 0),
            (InboxMessage.category == "referral", 1),
            (InboxMessage.category == "question", 2),
            (InboxMessage.category == "not_interested", 3),
            (InboxMessage.category == "do_not_contact", 4),
            (InboxMessage.category == "ooo", 5),
            (InboxMessage.category == "other", 6),
            else_=None,
        )
        resp_cat_sub = db.query(
            OutreachEvent.lead_id.label("lead_id"),
            func.min(_cat_ord).label("best_cat_ord"),
        ).join(InboxMessage, InboxMessage.outreach_event_id == OutreachEvent.event_id).filter(
            OutreachEvent.lead_id.isnot(None),
            InboxMessage.direction == MessageDirection.RECEIVED,
            InboxMessage.is_deleted == False,
            InboxMessage.category.isnot(None),
        ).group_by(OutreachEvent.lead_id).subquery()
        ev_sub = db.query(
            OutreachEvent.lead_id.label("lead_id"),
            func.max(case((OutreachEvent.status == OutreachStatus.REPLIED, 1), else_=0)).label("has_reply"),
            func.count(OutreachEvent.event_id).label("ev_count"),
        ).filter(OutreachEvent.lead_id.isnot(None)).group_by(OutreachEvent.lead_id).subquery()
        query = query.outerjoin(
            resp_cat_sub, LeadDetails.lead_id == resp_cat_sub.c.lead_id
        ).outerjoin(ev_sub, LeadDetails.lead_id == ev_sub.c.lead_id)
        resp_ord = case(
            (LeadDetails.response_status_override == "Interested", 0),
            (LeadDetails.response_status_override == "Referral", 1),
            (LeadDetails.response_status_override == "Question", 2),
            (LeadDetails.response_status_override == "Not-Interested", 3),
            (LeadDetails.response_status_override == "Do-Not-Contact", 4),
            (LeadDetails.response_status_override == "OOO", 5),
            (LeadDetails.response_status_override == "Other", 6),
            (resp_cat_sub.c.best_cat_ord.isnot(None), resp_cat_sub.c.best_cat_ord),
            (ev_sub.c.has_reply == 1, 7),
            (func.coalesce(ev_sub.c.ev_count, 0) > 0, 8),
            else_=9,
        )
        primary = asc(resp_ord) if sort_order == "asc" else desc(resp_ord)
        query = query.order_by(primary, LeadDetails.lead_id.asc())
    else:
        sort_column = SORT_COLUMNS.get(sort_by, LeadDetails.created_at)
        if sort_order == "asc":
            query = query.order_by(asc(sort_column))
        else:
            query = query.order_by(desc(sort_column))

    offset = (page - 1) * page_size
    leads = query.offset(offset).limit(page_size).all()

    pages = (total + page_size - 1) // page_size

    # Batch fetch contact counts via junction table + legacy FK
    lead_ids = [lead.lead_id for lead in leads]
    contact_counts = {}
    if lead_ids:
        # Junction table counts
        junc_counts = db.query(LeadContactAssociation).with_entities(
            LeadContactAssociation.lead_id,
            func.count(func.distinct(LeadContactAssociation.contact_id))
        ).filter(
            LeadContactAssociation.lead_id.in_(lead_ids)
        ).group_by(LeadContactAssociation.lead_id).all()
        for lid, cnt in junc_counts:
            contact_counts[lid] = cnt

        # Legacy FK counts (for leads not in junction table yet)
        legacy_counts = db.query(ContactDetails).with_entities(
            ContactDetails.lead_id,
            func.count(ContactDetails.contact_id)
        ).filter(
            ContactDetails.lead_id.in_(lead_ids)
        ).group_by(ContactDetails.lead_id).all()
        for lid, cnt in legacy_counts:
            contact_counts[lid] = max(contact_counts.get(lid, 0), cnt)

    # Batch fetch industry/company_size from client_info
    client_names = list({lead.client_name for lead in leads if lead.client_name})
    client_info_map = {}
    if client_names:
        client_rows = db.query(ClientInfo.client_name, ClientInfo.industry, ClientInfo.company_size, ClientInfo.website).filter(
            ClientInfo.client_name.in_(client_names)
        ).all()
        for name, ind, size, website in client_rows:
            client_info_map[name] = {"industry": ind, "company_size": size, "website": website}

    # Batch fetch campaign status + id for leads via campaign_contacts → campaigns
    campaign_status_map: dict[int, str] = {}
    campaign_id_map: dict[int, int] = {}
    if lead_ids:
        from app.db.models.campaign import Campaign as _Camp, CampaignContact as _CC
        camp_rows = db.query(
            _CC.lead_id,
            _Camp.status,
            _Camp.campaign_id,
        ).join(
            _Camp, _CC.campaign_id == _Camp.campaign_id
        ).filter(
            _CC.lead_id.in_(lead_ids),
            _CC.lead_id.isnot(None),
            _Camp.is_archived == False,
        ).all()

        # Pick highest-priority campaign status per lead (and its campaign id)
        _priority = {'active': 0, 'paused': 1, 'draft': 2, 'completed': 3}
        for lid, cstatus, cid in camp_rows:
            cstatus_val = cstatus.value if hasattr(cstatus, 'value') else cstatus
            existing = campaign_status_map.get(lid)
            if existing is None or _priority.get(cstatus_val, 99) < _priority.get(existing, 99):
                campaign_status_map[lid] = cstatus_val
                campaign_id_map[lid] = cid

    # Batch derive the Response rollup (per-contact replies -> one lead-level label)
    response_category_map, replied_lead_ids, outreach_lead_ids = _response_rollup_for_leads(
        db, lead_ids, tenant_id
    )

    lead_responses = []
    for lead in leads:
        lead_dict = LeadResponse.model_validate(lead).model_dump()
        lead_dict['contact_count'] = contact_counts.get(lead.lead_id, 0)
        ci = client_info_map.get(lead.client_name, {})
        lead_dict['industry'] = lead.industry or ci.get("industry")
        lead_dict['company_size'] = lead.company_size or ci.get("company_size")
        lead_dict['employer_website'] = lead.employer_website or ci.get("website")
        lead_dict['data_type'] = lead.data_type.value if hasattr(lead.data_type, 'value') else (lead.data_type or 'prod')
        _cstatus = campaign_status_map.get(lead.lead_id)
        lead_dict['campaign_status'] = _cstatus
        lead_dict['campaign_id'] = campaign_id_map.get(lead.lead_id)
        lead_dict['mailing_status'] = effective_mailing_status(lead, _cstatus)
        lead_dict['response_status'] = effective_response_status(
            lead,
            response_category_map.get(lead.lead_id),
            lead.lead_id in replied_lead_ids,
            lead.lead_id in outreach_lead_ids,
        )
        lead_dict['lob_id'] = lead.lob_id
        # Parse metadata_json into dict
        if lead.metadata_json:
            try:
                lead_dict['metadata'] = json.loads(lead.metadata_json)
            except (json.JSONDecodeError, TypeError):
                lead_dict['metadata'] = None
        lead_responses.append(lead_dict)

    return {
        "items": lead_responses,
        "total": total,
        "total_contact_associations": total_contact_associations,
        "page": page,
        "page_size": page_size,
        "pages": pages
    }


@router.get("/lookalike")
async def lookalike_search(
    domain: str = Query(..., description="Reference company domain"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Find companies similar to the given domain based on industry, size, and location."""
    # 1. Look up the reference company from ClientInfo by domain/website
    ref_client = db.query(ClientInfo).filter(
        (ClientInfo.domain == domain)
        | (ClientInfo.website.ilike(f"%{domain}%"))
    )
    ref_client = tenant_filter(ref_client, ClientInfo, tenant_id)
    ref = ref_client.first()

    if not ref:
        # Try matching by client_name containing the domain stem
        domain_stem = domain.split(".")[0] if "." in domain else domain
        ref_client2 = db.query(ClientInfo).filter(
            ClientInfo.client_name.ilike(f"%{domain_stem}%")
        )
        ref_client2 = tenant_filter(ref_client2, ClientInfo, tenant_id)
        ref = ref_client2.first()

    if not ref:
        return {
            "reference": {"domain": domain, "found": False},
            "similar": [],
            "total": 0,
        }

    # 2. Extract matching attributes
    ref_industry = ref.industry
    ref_size = ref.company_size
    ref_state = ref.location_state

    # 3. Query similar clients (exclude the reference company)
    similar_q = db.query(ClientInfo).filter(
        ClientInfo.client_id != ref.client_id,
        ClientInfo.is_archived == False,
    )
    similar_q = tenant_filter(similar_q, ClientInfo, tenant_id)

    # Build similarity conditions: at least industry OR size should match
    conditions = []
    if ref_industry:
        conditions.append(ClientInfo.industry == ref_industry)
    if ref_size:
        conditions.append(ClientInfo.company_size == ref_size)
    if ref_state:
        conditions.append(ClientInfo.location_state == ref_state)

    if conditions:
        similar_q = similar_q.filter(or_(*conditions))

    similar_clients = similar_q.limit(limit * 2).all()  # Over-fetch for scoring

    # 4. Score and rank by similarity
    scored = []
    for client in similar_clients:
        score = 0
        if ref_industry and client.industry == ref_industry:
            score += 40
        if ref_size and client.company_size == ref_size:
            score += 30
        if ref_state and client.location_state == ref_state:
            score += 20
        if ref.employee_count and client.employee_count:
            # Similarity bonus for close employee count
            ratio = min(ref.employee_count, client.employee_count) / max(ref.employee_count, client.employee_count, 1)
            score += int(ratio * 10)

        scored.append({
            "client_id": client.client_id,
            "client_name": client.client_name,
            "domain": client.domain,
            "website": client.website,
            "industry": client.industry,
            "company_size": client.company_size,
            "location_state": client.location_state,
            "employee_count": client.employee_count,
            "similarity_score": score,
        })

    # Sort by score descending, take top N
    scored.sort(key=lambda x: x["similarity_score"], reverse=True)
    top_similar = scored[:limit]

    return {
        "reference": {
            "domain": domain,
            "found": True,
            "client_id": ref.client_id,
            "client_name": ref.client_name,
            "industry": ref.industry,
            "company_size": ref.company_size,
            "location_state": ref.location_state,
        },
        "similar": top_similar,
        "total": len(top_similar),
    }


@router.get("/intent-scores")
async def lead_intent_scores(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Get intent/buying signal scores for leads, sorted by score descending."""
    from app.services.intent_data import enrich_leads_with_intent
    results = enrich_leads_with_intent(db, tenant_id, limit)
    return {"leads": results, "total": len(results)}


@router.get("/stats", tags=["Leads"])
async def get_lead_stats(
    show_archived: bool = Query(False, description="Include archived leads"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Get lead statistics summary."""
    stats_base = db.query(LeadDetails)
    stats_base = tenant_filter(stats_base, LeadDetails, tenant_id)
    if show_archived:
        stats_base = stats_base.filter(LeadDetails.is_archived == True)
    else:
        stats_base = stats_base.filter(LeadDetails.is_archived == False)
    total = stats_base.count()

    by_status = stats_base.with_entities(
        LeadDetails.lead_status,
        func.count(LeadDetails.lead_id)
    ).group_by(LeadDetails.lead_status).all()

    by_source = stats_base.with_entities(
        LeadDetails.source,
        func.count(LeadDetails.lead_id)
    ).group_by(LeadDetails.source).all()

    # Campaign status counts: count leads per campaign status (via campaign_contacts → campaigns)
    from app.db.models.campaign import Campaign as _Camp, CampaignContact as _CC
    camp_status_q = db.query(
        _Camp.status,
        func.count(func.distinct(_CC.lead_id))
    ).join(
        _Camp, _CC.campaign_id == _Camp.campaign_id
    ).filter(
        _CC.lead_id.isnot(None),
        _Camp.is_archived == False,
    )
    if tenant_id is not None:
        camp_status_q = camp_status_q.filter(_Camp.tenant_id == tenant_id)
    camp_status_rows = camp_status_q.group_by(_Camp.status).all()
    by_campaign_status = {}
    for cstatus, cnt in camp_status_rows:
        key = cstatus.value if hasattr(cstatus, 'value') else cstatus
        by_campaign_status[key] = cnt

    return {
        "total": total,
        "by_status": {s.value: c for s, c in by_status if s},
        "by_source": {s: c for s, c in by_source if s},
        "by_campaign_status": by_campaign_status,
    }



@router.get("/with-contact-counts")
async def list_leads_with_contact_counts(
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """List active leads with their linked contact counts (for campaign enrollment)."""
    query = db.query(LeadDetails).filter(LeadDetails.is_archived == False)
    query = tenant_filter(query, LeadDetails, tenant_id)

    if search:
        q = f"%{search}%"
        query = query.filter(
            LeadDetails.client_name.ilike(q)
            | LeadDetails.job_title.ilike(q)
            | LeadDetails.state.ilike(q)
        )

    total = query.count()
    leads = query.order_by(LeadDetails.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    # Batch-fetch contact counts via junction table
    lead_ids = [l.lead_id for l in leads]
    count_rows = (
        db.query(LeadContactAssociation.lead_id, func.count(LeadContactAssociation.contact_id))
        .filter(LeadContactAssociation.lead_id.in_(lead_ids))
        .group_by(LeadContactAssociation.lead_id)
        .all()
    ) if lead_ids else []
    count_map = {lid: cnt for lid, cnt in count_rows}

    items = []
    for l in leads:
        items.append({
            "lead_id": l.lead_id,
            "client_name": l.client_name,
            "job_title": l.job_title,
            "state": l.state,
            "lead_status": l.lead_status.value if l.lead_status else None,
            "source": l.source,
            "posting_date": l.posting_date.isoformat() if l.posting_date else None,
            "contact_count": count_map.get(l.lead_id, 0),
        })

    return {
        "items": items,
        "total": total,
        "page": page,
        "pages": (total + page_size - 1) // page_size,
    }


@router.get("/status-transitions")
async def get_status_transitions(
    current_status: Optional[LeadStatus] = None,
    current_user: User = Depends(get_current_active_user)
):
    """Get allowed status transitions. If current_status provided, returns allowed next statuses."""
    if current_status:
        return {
            "current": current_status.value,
            "allowed": get_allowed_transitions(current_status),
        }
    # Return full transition map
    from app.core.state_machine import LEAD_STATUS_TRANSITIONS
    return {
        s.value: sorted([t.value for t in targets])
        for s, targets in LEAD_STATUS_TRANSITIONS.items()
    }


@router.get("/export/csv")
async def export_leads_csv(
    lead_status: Optional[str] = Query(None, alias="status"),
    source: Optional[str] = None,
    state: Optional[List[str]] = Query(None),
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    search: Optional[str] = None,
    mailing_status: Optional[str] = Query(None, description="Filter by Mailing-Status label"),
    response_status: Optional[str] = Query(None, description="Filter by Response label"),
    show_archived: bool = Query(False, description="Include archived leads"),
    lob_id: Optional[int] = Query(None, description="Filter by Line of Business ID"),
    lead_ids: Optional[List[int]] = Query(None, description="Export only these lead IDs (selected leads)"),
    request: Request = None,  # type: ignore[assignment]
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Export leads with all associated contacts to CSV.

    Each row is a Lead+Contact combination. A lead with 4 contacts produces
    4 rows, all sharing the same lead fields but with different contact fields.
    Leads with no contacts still produce one row with empty contact columns.

    Filtering mirrors the leads list (via ``_apply_lead_filters``) so an export
    matches exactly what the user is viewing. GET is retained for backward compat;
    the leads page uses the POST route. Any list query param (including numeric
    size/salary and Excel text filters) applies here too via ``request``.
    """
    # Build lead query with filters
    lead_query = db.query(LeadDetails)
    lead_query = tenant_filter(lead_query, LeadDetails, tenant_id)

    # If specific lead IDs requested, filter to just those (ignore other filters)
    if lead_ids:
        lead_query = lead_query.filter(LeadDetails.lead_id.in_(lead_ids))
    else:
        lead_query = _apply_lead_filters(
            lead_query, db, tenant_id,
            status=lead_status, source=source, state=state,
            from_date=from_date, to_date=to_date, search=search,
            mailing_status=mailing_status, response_status=response_status,
            lob_id=lob_id, show_archived=show_archived,
            text_params=request.query_params if request is not None else {},
        )

    return _export_leads_stream(db, lead_query)


def _export_leads_stream(db: Session, lead_query):
    """Stamp downloaded_at and stream Lead×Contact rows as CSV.

    Shared by the GET (query-param) and POST (JSON-body) export routes. Large
    "selected" exports must use the POST route so lead_ids travel in the body
    instead of the URL — a GET with hundreds of lead_ids query params exceeds
    the proxy's request-line limit and the request is rejected.
    """
    # Stamp downloaded_at on all exported leads
    now = datetime.now()
    export_query = lead_query.with_entities(LeadDetails.lead_id)
    exported_ids = [row[0] for row in export_query.all()]
    if exported_ids:
        # Batch update in chunks of 500
        for i in range(0, len(exported_ids), 500):
            chunk = exported_ids[i:i + 500]
            db.query(LeadDetails).filter(LeadDetails.lead_id.in_(chunk)).update(
                {LeadDetails.downloaded_at: now}, synchronize_session=False
            )
        db.commit()

    def generate_csv():
        """Stream Lead×Contact CSV rows in batches."""
        output = io.StringIO()
        writer = csv.writer(output)

        # Header: all lead fields + all contact fields
        writer.writerow([
            # Lead fields
            "Lead ID", "Company Name", "Job Title", "State", "City",
            "Position Type", "Posting Date", "Job Link", "Source",
            "Lead Status", "Salary Min", "Salary Max", "Industry",
            "Company Size", "Employer LinkedIn", "Employer Website",
            "Lead Created At", "Downloaded At", "Mailing Status", "Response", "Campaign ID",
            # Contact fields
            "Contact ID", "Contact First Name", "Contact Last Name",
            "Contact Title", "Contact Email", "Contact Phone",
            "Contact LinkedIn", "Contact Location State",
            "Contact Source", "Priority Level", "Validation Status",
            "Outreach Status", "Contact Created At",
        ])
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)

        batch_size = 500
        offset = 0
        ordered_query = lead_query.order_by(LeadDetails.created_at.desc())
        while True:
            leads = ordered_query.offset(offset).limit(batch_size).all()
            if not leads:
                break

            lead_ids = [ld.lead_id for ld in leads]

            # Fetch all contacts linked to this batch via junction table
            assocs = db.query(
                LeadContactAssociation.lead_id,
                LeadContactAssociation.contact_id,
            ).filter(
                LeadContactAssociation.lead_id.in_(lead_ids),
                LeadContactAssociation.is_archived == False,
            ).all()

            contact_ids = list({a.contact_id for a in assocs})

            # Build lead_id -> [contact_id, ...] map
            lead_contact_map: dict[int, list[int]] = {}
            for a in assocs:
                lead_contact_map.setdefault(a.lead_id, []).append(a.contact_id)

            # Fetch contact objects in bulk
            contacts_by_id: dict[int, ContactDetails] = {}
            if contact_ids:
                contacts = db.query(ContactDetails).filter(
                    ContactDetails.contact_id.in_(contact_ids),
                    ContactDetails.is_archived == False,
                ).all()
                contacts_by_id = {c.contact_id: c for c in contacts}

            # Campaign status + id per lead (for Mailing Status / Campaign ID columns)
            from app.db.models.campaign import Campaign as _Camp, CampaignContact as _CC
            _priority = {'active': 0, 'paused': 1, 'draft': 2, 'completed': 3}
            camp_status_map: dict[int, str] = {}
            camp_id_map: dict[int, int] = {}
            camp_rows = db.query(_CC.lead_id, _Camp.status, _Camp.campaign_id).join(
                _Camp, _CC.campaign_id == _Camp.campaign_id
            ).filter(
                _CC.lead_id.in_(lead_ids),
                _CC.lead_id.isnot(None),
                _Camp.is_archived == False,
            ).all()
            for _lid, _cstatus, _cid in camp_rows:
                _cval = _cstatus.value if hasattr(_cstatus, 'value') else _cstatus
                _existing = camp_status_map.get(_lid)
                if _existing is None or _priority.get(_cval, 99) < _priority.get(_existing, 99):
                    camp_status_map[_lid] = _cval
                    camp_id_map[_lid] = _cid

            # Response rollup per lead (for the Response column) — tenant scope is
            # already enforced by lead_query; pass None to avoid re-filtering.
            resp_category_map, batch_replied_ids, batch_outreach_ids = _response_rollup_for_leads(
                db, lead_ids, None
            )

            for lead in leads:
                cids = lead_contact_map.get(lead.lead_id, [])
                lead_row = [
                    lead.lead_id,
                    lead.client_name,
                    lead.job_title,
                    lead.state,
                    lead.city or "",
                    lead.employment_type or "",
                    lead.posting_date.isoformat() if lead.posting_date else "",
                    lead.job_link or "",
                    lead.source or "",
                    lead.lead_status.value if lead.lead_status else "",
                    lead.salary_min or "",
                    lead.salary_max or "",
                    lead.industry or "",
                    lead.company_size or "",
                    lead.employer_linkedin_url or "",
                    lead.employer_website or "",
                    lead.created_at.isoformat() if lead.created_at else "",
                    lead.downloaded_at.isoformat() if lead.downloaded_at else "",
                    effective_mailing_status(lead, camp_status_map.get(lead.lead_id)),
                    effective_response_status(
                        lead,
                        resp_category_map.get(lead.lead_id),
                        lead.lead_id in batch_replied_ids,
                        lead.lead_id in batch_outreach_ids,
                    ),
                    camp_id_map.get(lead.lead_id) or "",
                ]

                if not cids:
                    # Lead with no contacts — one row, empty contact columns
                    writer.writerow(lead_row + [""] * 13)
                else:
                    for cid in cids:
                        c = contacts_by_id.get(cid)
                        if not c:
                            writer.writerow(lead_row + [""] * 13)
                            continue
                        writer.writerow(lead_row + [
                            c.contact_id,
                            c.first_name or "",
                            c.last_name or "",
                            c.title or "",
                            c.email or "",
                            c.phone or "",
                            c.linkedin_url or "",
                            c.location_state or "",
                            c.source or "",
                            c.priority_level.value if c.priority_level else "",
                            c.validation_status or "",
                            c.outreach_status or "",
                            c.created_at.isoformat() if c.created_at else "",
                        ])

            yield output.getvalue()
            output.seek(0)
            output.truncate(0)
            offset += batch_size

    filename = f"leads_contacts_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    return StreamingResponse(
        generate_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


class LeadExportRequest(BaseModel):
    """Body for POST /leads/export/csv — filters and/or an explicit lead_ids set.

    Mirrors the full leads-list filter set so an "export all" matches exactly
    what the user is viewing (WYSIWYG). Sending these in the body (rather than
    GET query params) lets large "selected" exports work — the URL length limit
    no longer applies. ``extra='allow'`` carries the dynamic Excel-style text
    filter keys (e.g. ``industry_op`` / ``industry_val``) straight to
    ``text_filter_from_params`` via ``model_dump()``.
    """
    model_config = {"extra": "allow"}

    lead_ids: Optional[List[int]] = None
    status: Optional[str] = None
    source: Optional[str] = None
    state: Optional[List[str]] = None
    client_name: Optional[str] = None
    job_title: Optional[str] = None
    industry: Optional[List[str]] = None
    company_size_op: Optional[str] = None
    company_size_value: Optional[int] = None
    company_size_value2: Optional[int] = None
    company_size_include_unknown: bool = False
    salary_op: Optional[str] = None
    salary_value: Optional[int] = None
    salary_value2: Optional[int] = None
    salary_include_unknown: bool = False
    data_type: Optional[str] = None
    employment_type: Optional[List[str]] = None
    exclude_keywords: Optional[List[str]] = None
    title: Optional[List[str]] = None
    from_date: Optional[date] = None
    to_date: Optional[date] = None
    extracted_from: Optional[date] = None
    extracted_to: Optional[date] = None
    downloaded: Optional[str] = None
    mailing_status: Optional[str] = None
    response_status: Optional[str] = None
    lob_id: Optional[int] = None
    search: Optional[str] = None
    show_archived: bool = False


@router.post("/export/csv")
async def export_leads_csv_post(
    body: LeadExportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Export leads to CSV via JSON body (mirrors the GET route).

    Applies the same filters as the leads list (via ``_apply_lead_filters``) so
    the export set equals the on-screen set. Used for "selected" exports of many
    leads, whose ids would overflow the URL if sent as GET query params.
    """
    lead_query = db.query(LeadDetails)
    lead_query = tenant_filter(lead_query, LeadDetails, tenant_id)

    if body.lead_ids:
        # Explicit selection wins — ignore the other filters.
        lead_query = lead_query.filter(LeadDetails.lead_id.in_(body.lead_ids))
    else:
        lead_query = _apply_lead_filters(
            lead_query, db, tenant_id,
            status=body.status, source=body.source, state=body.state,
            client_name=body.client_name, job_title=body.job_title,
            industry=body.industry,
            company_size_op=body.company_size_op,
            company_size_value=body.company_size_value,
            company_size_value2=body.company_size_value2,
            company_size_include_unknown=body.company_size_include_unknown,
            salary_op=body.salary_op, salary_value=body.salary_value,
            salary_value2=body.salary_value2,
            salary_include_unknown=body.salary_include_unknown,
            data_type=body.data_type, employment_type=body.employment_type,
            exclude_keywords=body.exclude_keywords, title=body.title,
            from_date=body.from_date, to_date=body.to_date,
            extracted_from=body.extracted_from, extracted_to=body.extracted_to,
            downloaded=body.downloaded, mailing_status=body.mailing_status,
            response_status=body.response_status,
            lob_id=body.lob_id, search=body.search,
            show_archived=body.show_archived,
            text_params=body.model_dump(),
        )

    return _export_leads_stream(db, lead_query)


@router.get("/filter-options")
async def get_lead_filter_options(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Get distinct values for lead filter dropdowns (industry/company_size from client_info)."""
    from app.core.config import settings as app_settings
    from app.core.settings_resolver import get_tenant_setting

    industry_query = db.query(ClientInfo.industry).filter(
        ClientInfo.industry.isnot(None), ClientInfo.industry != ""
    )
    industry_query = tenant_filter(industry_query, ClientInfo, tenant_id)
    industries = [r[0] for r in industry_query.distinct().order_by(ClientInfo.industry).all()]

    size_query = db.query(ClientInfo.company_size).filter(
        ClientInfo.company_size.isnot(None), ClientInfo.company_size != ""
    )
    size_query = tenant_filter(size_query, ClientInfo, tenant_id)
    sizes = [r[0] for r in size_query.distinct().order_by(ClientInfo.company_size).all()]

    # Distinct position types (employment_type) for the Excel-style Position Type filter
    emp_query = db.query(LeadDetails.employment_type).filter(
        LeadDetails.employment_type.isnot(None), LeadDetails.employment_type != ""
    )
    emp_query = tenant_filter(emp_query, LeadDetails, tenant_id)
    employment_types = [r[0] for r in emp_query.distinct().order_by(LeadDetails.employment_type).all()]

    # Exclusion keywords from tenant settings — fall back to config defaults when DB has empty list
    it_kw = get_tenant_setting(db, "exclude_it_keywords", tenant_id=tenant_id, default=None)
    if not it_kw:
        it_kw = app_settings.EXCLUDE_IT_KEYWORDS
    elif isinstance(it_kw, str):
        import json as _json
        try:
            it_kw = _json.loads(it_kw) or app_settings.EXCLUDE_IT_KEYWORDS
        except (ValueError, TypeError):
            it_kw = app_settings.EXCLUDE_IT_KEYWORDS

    staffing_kw = get_tenant_setting(db, "exclude_staffing_keywords", tenant_id=tenant_id, default=None)
    if not staffing_kw:
        staffing_kw = app_settings.EXCLUDE_STAFFING_KEYWORDS
    elif isinstance(staffing_kw, str):
        import json as _json
        try:
            staffing_kw = _json.loads(staffing_kw) or app_settings.EXCLUDE_STAFFING_KEYWORDS
        except (ValueError, TypeError):
            staffing_kw = app_settings.EXCLUDE_STAFFING_KEYWORDS

    # Job title categories from tenant settings (preferred) or config default
    job_cats = get_tenant_setting(db, "job_title_categories", tenant_id=tenant_id, default=None)
    if not job_cats or not isinstance(job_cats, dict):
        job_cats = app_settings.JOB_TITLE_CATEGORIES
    elif isinstance(job_cats, str):
        import json as _json
        try:
            job_cats = _json.loads(job_cats)
            if not isinstance(job_cats, dict):
                job_cats = app_settings.JOB_TITLE_CATEGORIES
        except (ValueError, TypeError):
            job_cats = app_settings.JOB_TITLE_CATEGORIES

    # Available job titles: flatten categories, merge with any stored flat list
    avail_titles = get_tenant_setting(db, "available_job_titles", tenant_id=tenant_id, default=None)
    if not avail_titles:
        avail_titles = []
    elif isinstance(avail_titles, str):
        import json as _json
        try:
            avail_titles = _json.loads(avail_titles) or []
        except (ValueError, TypeError):
            avail_titles = []

    # Merge: all titles from categories + any standalone titles
    cat_titles = set(t for ts in job_cats.values() for t in ts)
    all_titles = sorted(cat_titles | set(avail_titles))

    # Industry categories: match DB industries to configured categories
    industry_cats = app_settings.INDUSTRY_CATEGORIES
    categorized_industries: dict[str, list[str]] = {}
    categorized_set: set[str] = set()
    for cat, cat_industries in sorted(industry_cats.items()):
        matched = sorted([ind for ind in industries if ind in cat_industries])
        if matched:
            categorized_industries[cat] = matched
            categorized_set.update(matched)
    # Any industries not in a category go to "Other"
    uncategorized = sorted([ind for ind in industries if ind not in categorized_set])
    if uncategorized:
        categorized_industries["Other"] = uncategorized

    return {
        "industries": industries,
        "industry_categories": categorized_industries,
        "company_sizes": sizes,
        "data_types": ["test", "prod"],
        "exclusion_keywords": {
            "it_keywords": sorted(it_kw) if it_kw else [],
            "staffing_keywords": sorted(staffing_kw) if staffing_kw else [],
        },
        "job_titles": all_titles,
        "job_title_categories": {k: sorted(v) for k, v in sorted(job_cats.items())},
        "employment_types": employment_types,
    }


@router.get("/campaign-eligible")
async def check_campaign_eligible(
    lead_ids: List[int] = Query(..., description="Lead IDs to check eligibility for"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Check which leads are eligible for campaign enrollment.

    A lead is eligible if it has at least one contact AND is not already
    enrolled in an active/draft campaign.
    """
    from app.db.models.campaign import Campaign, CampaignContact, CampaignStatus

    if not lead_ids:
        return {"eligible_lead_ids": [], "ineligible": {}}

    # Subquery: leads enrolled in active/draft campaigns
    enrolled_lead_ids_subq = db.query(CampaignContact.lead_id).join(
        Campaign, CampaignContact.campaign_id == Campaign.campaign_id
    ).filter(
        Campaign.status.in_([CampaignStatus.ACTIVE, CampaignStatus.DRAFT]),
        Campaign.is_archived == False,
        CampaignContact.lead_id.isnot(None),
    ).distinct().subquery()

    # Subquery: leads that have at least one contact
    leads_with_contacts_subq = db.query(
        LeadContactAssociation.lead_id
    ).distinct().subquery()

    # Fetch the leads
    leads_q = db.query(LeadDetails).filter(LeadDetails.lead_id.in_(lead_ids))
    leads_q = tenant_filter(leads_q, LeadDetails, tenant_id)
    leads_found = leads_q.all()

    # Build sets for fast lookup
    enrolled_set = set(
        r[0] for r in db.query(enrolled_lead_ids_subq.c.lead_id).all()
    )
    has_contacts_set = set(
        r[0] for r in db.query(leads_with_contacts_subq.c.lead_id).filter(
            leads_with_contacts_subq.c.lead_id.in_(lead_ids)
        ).all()
    )

    eligible = []
    ineligible = {}
    for lead in leads_found:
        lid = lead.lead_id
        is_test_lead = getattr(lead, 'data_type', None) == 'test'
        if lid in enrolled_set and not is_test_lead:
            ineligible[lid] = "Already in active campaign"
        elif lid not in has_contacts_set:
            ineligible[lid] = "No contacts"
        else:
            eligible.append(lid)

    return {"eligible_lead_ids": eligible, "ineligible": ineligible}


@router.post("/import/preview")
async def preview_csv_import(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Preview CSV import: show first 10 rows, total count, and duplicate count."""
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="File must be a CSV")

    content = await file.read()
    decoded = content.decode('utf-8')
    reader = csv.DictReader(io.StringIO(decoded))

    rows = list(reader)
    total_rows = len(rows)

    # Check for duplicates
    dup_query = db.query(LeadDetails).with_entities(
        LeadDetails.job_link
    ).filter(
        LeadDetails.job_link.isnot(None)
    )
    dup_query = tenant_filter(dup_query, LeadDetails, tenant_id)
    existing_links = {
        link for (link,) in dup_query.all()
    }

    duplicate_count = 0
    preview_rows = []
    for i, row in enumerate(rows):
        row_lower = {k.lower().strip(): v for k, v in row.items()}
        job_link = (row_lower.get('job link') or row_lower.get('job_link') or
                    row_lower.get('link') or row_lower.get('url') or "").strip()

        is_duplicate = bool(job_link and job_link in existing_links)
        if is_duplicate:
            duplicate_count += 1

        if i < 10:
            # Extract contact name from various column formats
            contact_name = (
                row_lower.get('contact name') or row_lower.get('name') or ""
            ).strip()
            first_name = (
                row_lower.get('first name') or row_lower.get('first_name') or
                row_lower.get('contact first name') or ""
            ).strip()
            last_name = (
                row_lower.get('last name') or row_lower.get('last_name') or
                row_lower.get('contact last name') or ""
            ).strip()
            if contact_name and not first_name:
                parts = contact_name.split(None, 1)
                first_name = parts[0] if parts else ""
                last_name = parts[1] if len(parts) > 1 else ""
            display_name = f"{first_name} {last_name}".strip()

            email = (
                row_lower.get('contact email') or row_lower.get('email') or
                row_lower.get('email id') or ""
            ).strip()

            preview_rows.append({
                "row_number": i + 2,
                "company_name": (row_lower.get('company name') or row_lower.get('client_name') or
                                row_lower.get('company') or "").strip(),
                "job_title": (row_lower.get('job title') or row_lower.get('job_title') or
                             row_lower.get('title') or "").strip(),
                "state": (row_lower.get('state') or "").strip(),
                "contact_name": display_name,
                "email": email,
                "source": (row_lower.get('source') or "import").strip(),
                "is_duplicate": is_duplicate,
            })

    return {
        "filename": file.filename,
        "total_rows": total_rows,
        "duplicate_count": duplicate_count,
        "new_count": total_rows - duplicate_count,
        "preview": preview_rows,
        "columns": list(rows[0].keys()) if rows else [],
    }


def _parse_and_import_lead_rows(
    rows: list[dict],
    existing_links: set,
    skip_duplicates: bool,
    source_default: str,
    tenant_id: Optional[int],
    db: Session,
) -> dict:
    """Shared helper to parse CSV/Google Sheet rows and import leads.

    Returns dict with imported, skipped, errors, imported_lead_ids.
    """
    imported = 0
    skipped = 0
    excluded = 0
    contacts_created = 0
    errors = []
    imported_lead_ids = []

    from app.services.lead_eligibility import LeadEligibilityGate
    gate = LeadEligibilityGate(db, tenant_id=tenant_id)

    for row_num, row in enumerate(rows, start=2):
        try:
            row_lower = {k.lower().strip(): v for k, v in row.items()}

            client_name = (
                row_lower.get('company name') or
                row_lower.get('client_name') or
                row_lower.get('company') or ""
            ).strip()

            job_title = (
                row_lower.get('job title') or
                row_lower.get('job_title') or
                row_lower.get('title') or ""
            ).strip()

            if not client_name or not job_title:
                errors.append(f"Row {row_num}: Missing company name or job title")
                skipped += 1
                continue

            # Exclusion gate — never import out-of-scope companies (they would
            # otherwise be handed to enrichment via imported_lead_ids).
            eligible, reason = gate.check({"client_name": client_name, "job_title": job_title})
            if not eligible:
                excluded += 1
                errors.append(f"Row {row_num}: Excluded ({reason}): {client_name}")
                continue

            job_link = (
                row_lower.get('job link') or
                row_lower.get('job_link') or
                row_lower.get('link') or
                row_lower.get('url') or ""
            ).strip()

            if skip_duplicates and job_link:
                if job_link in existing_links:
                    skipped += 1
                    continue
                existing_links.add(job_link)

            posting_date_str = (
                row_lower.get('posting date') or
                row_lower.get('posting_date') or
                row_lower.get('date') or ""
            ).strip()
            posting_date = None
            if posting_date_str:
                try:
                    posting_date = datetime.strptime(posting_date_str, "%Y-%m-%d").date()
                except ValueError:
                    try:
                        posting_date = datetime.strptime(posting_date_str, "%m/%d/%Y").date()
                    except ValueError:
                        posting_date = date.today()

            status_str = (
                row_lower.get('status') or
                row_lower.get('lead_status') or "open"
            ).strip().lower()
            status_map = {
                'open': LeadStatus.OPEN,
                'hunting': LeadStatus.HUNTING,
                'closed_hired': LeadStatus.CLOSED_HIRED,
                'closed-hired': LeadStatus.CLOSED_HIRED,
                'closed_not_hired': LeadStatus.CLOSED_NOT_HIRED,
                'closed-not-hired': LeadStatus.CLOSED_NOT_HIRED,
                'new': LeadStatus.OPEN,
                'closed_test': LeadStatus.CLOSED_TEST,
                'closed-test': LeadStatus.CLOSED_TEST,
            }
            lead_status_val = status_map.get(status_str, LeadStatus.OPEN)

            salary_min = None
            salary_max = None
            try:
                salary_min_str = row_lower.get('salary min') or row_lower.get('salary_min') or ""
                if salary_min_str:
                    salary_min = float(salary_min_str.replace(',', '').replace('$', ''))
            except ValueError:
                pass
            try:
                salary_max_str = row_lower.get('salary max') or row_lower.get('salary_max') or ""
                if salary_max_str:
                    salary_max = float(salary_max_str.replace(',', '').replace('$', ''))
            except ValueError:
                pass

            # Extract contact fields
            contact_email = (
                row_lower.get('contact email') or
                row_lower.get('email') or
                row_lower.get('email id') or ""
            ).strip()
            contact_first = (
                row_lower.get('first name') or
                row_lower.get('first_name') or
                row_lower.get('contact first name') or ""
            ).strip()
            contact_last = (
                row_lower.get('last name') or
                row_lower.get('last_name') or
                row_lower.get('contact last name') or ""
            ).strip()
            # Support a single "Contact Name" / "Name" column — split into first/last
            contact_full = (
                row_lower.get('contact name') or
                row_lower.get('name') or ""
            ).strip()
            if contact_full and not contact_first:
                parts = contact_full.split(None, 1)
                contact_first = parts[0] if parts else ""
                contact_last = parts[1] if len(parts) > 1 else ""
            contact_phone = (
                row_lower.get('phone') or
                row_lower.get('contact phone') or
                row_lower.get('phone number') or ""
            ).strip()
            contact_title = (
                row_lower.get('contact title') or
                row_lower.get('designation') or ""
            ).strip()

            # Employment / position type
            employment_type_raw = (
                row_lower.get('position type') or
                row_lower.get('employment type') or
                row_lower.get('employment_type') or
                row_lower.get('job type') or
                row_lower.get('contract type') or ""
            ).strip()
            from app.services.adapters.base import normalize_employment_type
            employment_type_val = normalize_employment_type(employment_type_raw) or None

            lead = LeadDetails(
                client_name=client_name,
                job_title=job_title,
                state=(row_lower.get('state') or "").strip()[:2].upper(),
                posting_date=posting_date or date.today(),
                job_link=job_link or None,
                source=(row_lower.get('source') or source_default).strip(),
                employment_type=employment_type_val,
                lead_status=lead_status_val,
                salary_min=salary_min,
                salary_max=salary_max,
                contact_email=contact_email or None,
            )
            lead.tenant_id = tenant_id or 1
            db.add(lead)
            db.flush()
            imported_lead_ids.append(lead.lead_id)
            imported += 1

            # Create contact if email is provided
            if contact_email:
                try:
                    contact = ContactDetails(
                        tenant_id=tenant_id or 1,
                        lead_id=lead.lead_id,
                        client_name=client_name,
                        first_name=contact_first or "Unknown",
                        last_name=contact_last or "Contact",
                        email=contact_email,
                        phone=contact_phone or None,
                        title=contact_title or job_title,
                        source=source_default,
                    )
                    db.add(contact)
                    db.flush()
                    # Also create the junction table link
                    assoc = LeadContactAssociation(
                        lead_id=lead.lead_id,
                        contact_id=contact.contact_id,
                    )
                    db.add(assoc)
                    contacts_created += 1
                except Exception:
                    pass  # Contact creation is best-effort

        except Exception as e:
            errors.append(f"Row {row_num}: {str(e)}")
            skipped += 1

    db.commit()

    return {
        "imported": imported,
        "skipped": skipped,
        "excluded": excluded,
        "contacts_created": contacts_created,
        "errors": errors[:10] if errors else [],
        "imported_lead_ids": imported_lead_ids,
    }


def _get_existing_links(db: Session, tenant_id: Optional[int]) -> set:
    """Pre-load existing job_links for duplicate checking."""
    dup_query = db.query(LeadDetails).with_entities(
        LeadDetails.job_link
    ).filter(
        LeadDetails.job_link.isnot(None)
    )
    dup_query = tenant_filter(dup_query, LeadDetails, tenant_id)
    return {link for (link,) in dup_query.all()}


@router.post("/import/csv")
async def import_leads_csv(
    file: UploadFile = File(...),
    skip_duplicates: bool = Query(True, description="Skip leads with duplicate job_link"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Import leads from CSV file."""
    if not file.filename.endswith('.csv'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a CSV"
        )

    content = await file.read()
    decoded = content.decode('utf-8')
    rows = list(csv.DictReader(io.StringIO(decoded)))

    existing_links = _get_existing_links(db, tenant_id) if skip_duplicates else set()

    result = _parse_and_import_lead_rows(
        rows=rows,
        existing_links=existing_links,
        skip_duplicates=skip_duplicates,
        source_default="import",
        tenant_id=tenant_id,
        db=db,
    )

    return {
        "message": f"Import complete: {result['imported']} leads imported, {result['skipped']} skipped",
        **result,
    }



@router.get("/import/template")
async def download_import_template(
    current_user: User = Depends(get_current_active_user),
):
    """Download a CSV template for lead+contact import."""
    headers = [
        "Company Name", "Job Title", "State", "Position Type", "Job Link", "Source",
        "Posting Date", "Salary Min", "Salary Max", "Status",
        "First Name", "Last Name", "Email", "Phone", "Contact Title",
    ]
    sample = [
        "Acme Corp", "Software Engineer", "TX", "Full-time", "https://example.com/job/123", "import",
        "2026-04-10", "80000", "120000", "open",
        "Jane", "Doe", "jane.doe@acmecorp.com", "555-123-4567", "HR Manager",
    ]
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerow(sample)
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=lead_import_template.csv"},
    )


def _extract_google_sheet_id(url: str) -> tuple[str, str]:
    """Extract sheet ID and optional gid from Google Sheets URL.

    Returns (sheet_id, gid) where gid may be '0' for default.
    """
    match = re.search(r'/spreadsheets/d/([a-zA-Z0-9_-]+)', url)
    if not match:
        raise HTTPException(status_code=400, detail="Invalid Google Sheets URL. Expected format: https://docs.google.com/spreadsheets/d/SHEET_ID/...")
    sheet_id = match.group(1)
    gid_match = re.search(r'[?&]gid=(\d+)', url)
    gid = gid_match.group(1) if gid_match else '0'
    return sheet_id, gid


async def _fetch_google_sheet_csv(sheet_id: str, gid: str) -> str:
    """Fetch CSV export of a public Google Sheet."""
    import httpx
    export_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        resp = await client.get(export_url)
    if resp.status_code == 404:
        raise HTTPException(status_code=400, detail="Sheet not found. Make sure it is publicly accessible (File → Share → Anyone with the link).")
    if resp.status_code != 200:
        raise HTTPException(status_code=400, detail=f"Failed to fetch sheet (HTTP {resp.status_code}). Ensure the sheet is publicly accessible.")
    return resp.text


@router.post("/import/google-sheet/preview")
async def preview_google_sheet_import(
    request: GoogleSheetRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Preview Google Sheet import: show first 10 rows, total count, and duplicate count."""
    sheet_id, gid = _extract_google_sheet_id(request.sheet_url)
    csv_text = await _fetch_google_sheet_csv(sheet_id, gid)

    reader = csv.DictReader(io.StringIO(csv_text))
    rows = list(reader)
    total_rows = len(rows)

    if total_rows == 0:
        return {
            "total_rows": 0,
            "duplicate_count": 0,
            "new_count": 0,
            "preview": [],
            "columns": [],
        }

    existing_links = _get_existing_links(db, tenant_id)

    duplicate_count = 0
    preview_rows = []
    for i, row in enumerate(rows):
        row_lower = {k.lower().strip(): v for k, v in row.items()}
        job_link = (row_lower.get('job link') or row_lower.get('job_link') or
                    row_lower.get('link') or row_lower.get('url') or "").strip()

        is_duplicate = bool(job_link and job_link in existing_links)
        if is_duplicate:
            duplicate_count += 1

        if i < 10:
            contact_name = (
                row_lower.get('contact name') or row_lower.get('name') or ""
            ).strip()
            first_name = (
                row_lower.get('first name') or row_lower.get('first_name') or
                row_lower.get('contact first name') or ""
            ).strip()
            last_name = (
                row_lower.get('last name') or row_lower.get('last_name') or
                row_lower.get('contact last name') or ""
            ).strip()
            if contact_name and not first_name:
                parts = contact_name.split(None, 1)
                first_name = parts[0] if parts else ""
                last_name = parts[1] if len(parts) > 1 else ""
            display_name = f"{first_name} {last_name}".strip()

            email = (
                row_lower.get('contact email') or row_lower.get('email') or
                row_lower.get('email id') or ""
            ).strip()

            preview_rows.append({
                "row_number": i + 2,
                "company_name": (row_lower.get('company name') or row_lower.get('client_name') or
                                row_lower.get('company') or "").strip(),
                "job_title": (row_lower.get('job title') or row_lower.get('job_title') or
                             row_lower.get('title') or "").strip(),
                "state": (row_lower.get('state') or "").strip(),
                "contact_name": display_name,
                "email": email,
                "source": (row_lower.get('source') or "google_sheet").strip(),
                "is_duplicate": is_duplicate,
            })

    return {
        "total_rows": total_rows,
        "duplicate_count": duplicate_count,
        "new_count": total_rows - duplicate_count,
        "preview": preview_rows,
        "columns": list(rows[0].keys()) if rows else [],
    }


@router.post("/import/google-sheet")
async def import_google_sheet(
    request: GoogleSheetRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Import leads from a public Google Sheet."""
    sheet_id, gid = _extract_google_sheet_id(request.sheet_url)
    csv_text = await _fetch_google_sheet_csv(sheet_id, gid)

    rows = list(csv.DictReader(io.StringIO(csv_text)))
    existing_links = _get_existing_links(db, tenant_id) if request.skip_duplicates else set()

    result = _parse_and_import_lead_rows(
        rows=rows,
        existing_links=existing_links,
        skip_duplicates=request.skip_duplicates,
        source_default="google_sheet",
        tenant_id=tenant_id,
        db=db,
    )

    return {
        "message": f"Import complete: {result['imported']} leads imported, {result['skipped']} skipped",
        **result,
    }


@router.delete("/bulk")
async def bulk_delete_leads(
    request: BulkLeadIdsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Archive multiple leads by IDs (soft delete). Admin only."""
    lead_ids = request.lead_ids
    if not lead_ids:
        raise HTTPException(status_code=400, detail="No lead IDs provided")

    bulk_del_query = db.query(LeadDetails).filter(
        LeadDetails.lead_id.in_(lead_ids)
    )
    bulk_del_query = tenant_filter(bulk_del_query, LeadDetails, tenant_id)
    leads = bulk_del_query.all()

    if not leads:
        raise HTTPException(status_code=404, detail="No leads found with provided IDs")

    found_ids = [l.lead_id for l in leads]

    try:
        # Soft delete: archive leads only — contacts and companies are preserved
        archived_count = db.query(LeadDetails).filter(
            LeadDetails.lead_id.in_(found_ids)
        ).update({LeadDetails.is_archived: True}, synchronize_session=False)

        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Bulk delete failed: {str(e)}")

    return {
        "message": f"Successfully archived {archived_count} lead(s)",
        "archived_count": archived_count,
        "archived_ids": found_ids
    }

@router.put('/bulk/unarchive', tags=['Leads'])
async def bulk_unarchive_leads(
    request: BulkLeadIdsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Restore archived leads (unarchive)."""
    lead_ids = request.lead_ids
    if not lead_ids:
        raise HTTPException(status_code=400, detail='No lead IDs provided')

    try:
        unarchive_query = db.query(LeadDetails).filter(
            LeadDetails.lead_id.in_(lead_ids),
            LeadDetails.is_archived == True
        )
        unarchive_query = tenant_filter(unarchive_query, LeadDetails, tenant_id)
        restored_count = unarchive_query.update({LeadDetails.is_archived: False}, synchronize_session=False)

        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Bulk unarchive failed: {str(e)}")

    return {
        'message': f'Successfully restored {restored_count} lead(s)',
        'restored_count': restored_count,
        'restored_ids': lead_ids
    }






@router.put("/bulk/status")
async def bulk_update_status(
    request: BulkLeadStatusRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Update status of multiple leads at once. Admin/Operator only."""
    lead_ids = request.lead_ids
    new_status = request.status

    if not lead_ids:
        raise HTTPException(status_code=400, detail="No lead IDs provided")
    if not new_status:
        raise HTTPException(status_code=400, detail="No status provided")

    # Validate status
    try:
        status_enum = LeadStatus(new_status)
    except ValueError:
        valid = [s.value for s in LeadStatus]
        raise HTTPException(status_code=400, detail=f"Invalid status. Valid: {valid}")

    # Validate transitions per lead and audit
    status_query = db.query(LeadDetails).filter(LeadDetails.lead_id.in_(lead_ids))
    status_query = tenant_filter(status_query, LeadDetails, tenant_id)
    leads = status_query.all()
    updated = 0
    rejected = []
    for lead in leads:
        if not validate_transition(lead.lead_status, status_enum):
            rejected.append({
                "lead_id": lead.lead_id,
                "current": lead.lead_status.value,
                "requested": new_status,
                "allowed": get_allowed_transitions(lead.lead_status),
            })
            continue
        old_status = lead.lead_status.value
        lead.lead_status = status_enum
        _audit(db, "lead", lead.lead_id, "status_change",
               {"lead_status": {"old": old_status, "new": new_status}},
               changed_by=current_user.email)
        updated += 1
    db.commit()

    result = {
        "message": f"Updated {updated} lead(s) to status '{new_status}'",
        "updated_count": updated,
        "status": new_status,
    }
    if rejected:
        result["rejected"] = rejected
        result["message"] += f"; {len(rejected)} rejected (invalid transition)"
    return result


@router.put("/bulk/update")
async def bulk_update_leads(
    request: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.SUPER_ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Bulk update multiple leads. Super Admin only.

    Body: { "lead_ids": [...], "updates": { "field": "value", ... } }

    ``data_type`` applies to every selected lead. The Mailed-Offline fields
    (``mailing_status_override``, ``response_status_override``, ``enroll_campaign_id``)
    apply ONLY to selected leads whose current Mailing-Status is Mailed-Offline
    (downloaded, no campaign); other leads are skipped and reported.
    """
    lead_ids = request.get("lead_ids", [])
    updates = request.get("updates", {})

    if not lead_ids:
        raise HTTPException(status_code=400, detail="No lead IDs provided")
    if not updates:
        raise HTTPException(status_code=400, detail="No update fields provided")

    # Global field(s) — applied to every selected lead.
    global_fields = {k: v for k, v in updates.items() if k == "data_type" and v not in (None, "")}

    # Mailed-Offline-scoped fields.
    mailing_override = updates.get("mailing_status_override") or None
    response_override = updates.get("response_status_override") or None
    enroll_campaign_id = updates.get("enroll_campaign_id") or None

    if mailing_override and mailing_override not in MAILING_STATUS_OVERRIDE_OPTIONS:
        raise HTTPException(status_code=400, detail=f"Invalid Mailing-Status value: {mailing_override}")
    if response_override and response_override not in RESPONSE_STATUS_OVERRIDE_OPTIONS:
        raise HTTPException(status_code=400, detail=f"Invalid Response value: {response_override}")
    if enroll_campaign_id is not None:
        try:
            enroll_campaign_id = int(enroll_campaign_id)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="enroll_campaign_id must be an integer")

    offline_fields_requested = bool(mailing_override or response_override or enroll_campaign_id)
    if not global_fields and not offline_fields_requested:
        raise HTTPException(status_code=400, detail="No valid update fields provided")

    query = db.query(LeadDetails).filter(LeadDetails.lead_id.in_(lead_ids))
    query = tenant_filter(query, LeadDetails, tenant_id)
    leads = query.all()
    if not leads:
        raise HTTPException(status_code=404, detail="No leads found with provided IDs")

    # If enrolling, validate the campaign belongs to this tenant up front.
    if enroll_campaign_id is not None:
        from app.db.models.campaign import Campaign as _Camp
        camp = db.query(_Camp).filter(_Camp.campaign_id == enroll_campaign_id).first()
        if not camp or (tenant_id is not None and camp.tenant_id != tenant_id):
            raise HTTPException(status_code=404, detail="Campaign not found")

    # Determine which selected leads are currently Mailed-Offline (downloaded, no
    # non-archived campaign) — the eligible set for the scoped fields.
    eligible_ids: set[int] = set()
    if offline_fields_requested:
        from app.db.models.campaign import Campaign as _Camp2, CampaignContact as _CC2
        leads_with_campaign = {
            r[0] for r in db.query(_CC2.lead_id).join(
                _Camp2, _CC2.campaign_id == _Camp2.campaign_id
            ).filter(
                _CC2.lead_id.in_(lead_ids),
                _CC2.lead_id.isnot(None),
                _Camp2.is_archived == False,
            ).distinct().all()
        }
        eligible_ids = {
            ld.lead_id for ld in leads
            if ld.downloaded_at is not None and ld.lead_id not in leads_with_campaign
        }

    enrolled_count = 0
    changed_ids: set[int] = set()
    try:
        # Global fields on every selected lead.
        for lead in leads:
            for field, value in global_fields.items():
                setattr(lead, field, value)
                changed_ids.add(lead.lead_id)

        # Scoped overrides on eligible leads only.
        if mailing_override or response_override:
            for lead in leads:
                if lead.lead_id not in eligible_ids:
                    continue
                if mailing_override:
                    lead.mailing_status_override = mailing_override
                if response_override:
                    lead.response_status_override = response_override
                changed_ids.add(lead.lead_id)
                _audit(
                    db, "lead", lead.lead_id, "bulk_update_offline",
                    changed_fields={
                        k: v for k, v in {
                            "mailing_status_override": mailing_override,
                            "response_status_override": response_override,
                        }.items() if v
                    },
                    changed_by=getattr(current_user, "email", None),
                    tenant_id=tenant_id or 1,
                )

        # Real campaign enrollment for eligible leads' contacts.
        if enroll_campaign_id is not None and eligible_ids:
            contact_ids: set[int] = set()
            for r in db.query(LeadContactAssociation.contact_id).filter(
                LeadContactAssociation.lead_id.in_(eligible_ids)
            ).all():
                contact_ids.add(r[0])
            for r in db.query(ContactDetails.contact_id).filter(
                ContactDetails.lead_id.in_(eligible_ids)
            ).all():
                contact_ids.add(r[0])
            if contact_ids:
                from app.services.campaign_engine import enroll_contacts as _enroll
                result = _enroll(enroll_campaign_id, list(contact_ids), db)
                enrolled_count = result.get("enrolled", 0) if isinstance(result, dict) else 0
                changed_ids.update(eligible_ids)

        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Bulk update failed: {str(e)}")

    skipped_count = (len(leads) - len(eligible_ids)) if offline_fields_requested else 0
    msg = f"Updated {len(changed_ids)} lead(s)"
    if offline_fields_requested and skipped_count:
        msg += f" — {skipped_count} skipped (not Mailed-Offline)"
    if enroll_campaign_id is not None:
        msg += f"; enrolled {enrolled_count} contact(s)"
    return {
        "message": msg,
        "updated_count": len(changed_ids),
        "offline_eligible_count": len(eligible_ids) if offline_fields_requested else 0,
        "skipped_count": skipped_count,
        "enrolled_count": enrolled_count,
    }


@router.post("/bulk/enrich/preview")
async def preview_bulk_enrichment(
    request: BulkLeadIdsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Preview enrichment plan: show leads, existing contacts, reusable contacts, API needs."""
    lead_ids = request.lead_ids
    if not lead_ids:
        raise HTTPException(status_code=400, detail="No lead IDs provided")

    from app.core.config import settings as app_settings
    from app.core.settings_resolver import get_tenant_setting
    _mc = get_tenant_setting(db, "max_contacts_per_company_job", tenant_id=tenant_id, default=None)
    max_contacts = int(_mc) if _mc is not None else app_settings.MAX_CONTACTS_PER_COMPANY_PER_JOB

    previews = []
    summary = {
        "total_leads": len(lead_ids),
        "will_enrich": 0,
        "will_skip": 0,
        "contacts_from_cache": 0,
        "leads_needing_api": 0
    }

    for lid in lead_ids:
        enrich_lead_q = db.query(LeadDetails).filter(LeadDetails.lead_id == lid)
        if tenant_id is not None:
            enrich_lead_q = enrich_lead_q.filter(LeadDetails.tenant_id == tenant_id)
        lead = enrich_lead_q.first()
        if not lead:
            previews.append({"lead_id": lid, "error": "Lead not found", "status": "skip", "skip_reason": "Not found"})
            summary["will_skip"] += 1
            continue

        # Count existing contacts for this lead (junction + FK)
        existing_cids = set()
        for row in db.query(LeadContactAssociation).with_entities(
            LeadContactAssociation.contact_id
        ).filter(
            LeadContactAssociation.lead_id == lid
        ).all():
            existing_cids.add(row[0])
        for c in db.query(ContactDetails).with_entities(
            ContactDetails.contact_id
        ).filter(
            ContactDetails.lead_id == lid
        ).all():
            existing_cids.add(c[0])
        current_contacts = len(existing_cids)

        if current_contacts >= max_contacts:
            previews.append({
                "lead_id": lid, "client_name": lead.client_name, "job_title": lead.job_title,
                "current_contacts": current_contacts, "reusable_count": 0, "api_needed": 0,
                "status": "skip", "skip_reason": f"Already has {current_contacts}/{max_contacts} contacts"
            })
            summary["will_skip"] += 1
            continue

        # Count reusable contacts at same company not linked to this lead
        reusable_q = db.query(ContactDetails).filter(
            ContactDetails.client_name == lead.client_name
        )
        if existing_cids:
            reusable_q = reusable_q.filter(~ContactDetails.contact_id.in_(list(existing_cids)))
        reusable_count = reusable_q.count()

        needed = max_contacts - current_contacts
        from_cache = min(reusable_count, needed)
        api_needed = max(0, needed - from_cache)

        previews.append({
            "lead_id": lid, "client_name": lead.client_name, "job_title": lead.job_title,
            "current_contacts": current_contacts, "reusable_count": from_cache,
            "api_needed": api_needed, "status": "enrich", "skip_reason": None
        })
        summary["will_enrich"] += 1
        summary["contacts_from_cache"] += from_cache
        if api_needed > 0:
            summary["leads_needing_api"] += 1

    # Auto-enrich sibling preview: find other unenriched leads at the same companies
    enriching_companies = set()
    for p in previews:
        if p.get("status") == "enrich" and p.get("client_name"):
            enriching_companies.add(p["client_name"])

    selected_id_set = set(lead_ids)
    auto_enrich_previews = []
    for company in enriching_companies:
        siblings = db.query(LeadDetails).filter(
            LeadDetails.client_name == company,
            LeadDetails.first_name.is_(None),
            ~LeadDetails.lead_status.in_(CLOSED_STATUSES),
            LeadDetails.is_archived == False,
            ~LeadDetails.lead_id.in_(list(selected_id_set))
        ).all()
        for sib in siblings:
            # Check if there are reusable contacts at this company
            sib_existing_cids = set()
            for row in db.query(LeadContactAssociation).with_entities(
                LeadContactAssociation.contact_id
            ).filter(
                LeadContactAssociation.lead_id == sib.lead_id
            ).all():
                sib_existing_cids.add(row[0])
            for c in db.query(ContactDetails).with_entities(
                ContactDetails.contact_id
            ).filter(
                ContactDetails.lead_id == sib.lead_id
            ).all():
                sib_existing_cids.add(c[0])

            sib_reusable_q = db.query(ContactDetails).filter(
                ContactDetails.client_name == company
            )
            if sib_existing_cids:
                sib_reusable_q = sib_reusable_q.filter(~ContactDetails.contact_id.in_(list(sib_existing_cids)))
            reusable_count = sib_reusable_q.count()

            if reusable_count > 0:
                auto_enrich_previews.append({
                    "lead_id": sib.lead_id,
                    "client_name": sib.client_name,
                    "job_title": sib.job_title,
                    "reusable_count": min(reusable_count, max_contacts - len(sib_existing_cids)),
                })

    summary["auto_enrich_siblings"] = len(auto_enrich_previews)

    return {"previews": previews, "summary": summary, "auto_enrich_previews": auto_enrich_previews}


@router.post("/bulk/enrich")
async def bulk_enrich_leads(
    request: BulkEnrichRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.OPERATOR])),
    tenant_id: int = Depends(require_tenant_id),
):
    """Trigger contact enrichment for selected leads (runs in background)."""
    lead_ids = request.lead_ids
    if not lead_ids:
        raise HTTPException(status_code=400, detail="No lead IDs provided")
    if len(lead_ids) > 200:
        raise HTTPException(status_code=400, detail="Maximum 200 leads per batch")

    from app.services.pipelines.contact_enrichment import run_contact_enrichment_pipeline
    from app.db.models.job_run import JobRun, JobStatus

    # Pre-create job run so we can return run_id immediately
    job_run = JobRun(
        tenant_id=tenant_id or 1,
        pipeline_name="contact_enrichment",
        status=JobStatus.PENDING,
        triggered_by=current_user.email,
    )
    db.add(job_run)
    db.commit()
    db.refresh(job_run)
    created_run_id = job_run.run_id

    background_tasks.add_task(
        run_contact_enrichment_pipeline,
        triggered_by=current_user.email,
        lead_ids=lead_ids,
        run_id=created_run_id,
        tenant_id=tenant_id,
    )

    return {
        "message": f"Contact enrichment started for {len(lead_ids)} lead(s)",
        "status": "processing",
        "lead_count": len(lead_ids),
        "run_id": created_run_id
    }


@router.post("/bulk/outreach/preview")
async def preview_bulk_outreach(
    request: BulkLeadIdsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Preview outreach plan: show leads, contacts, eligibility, and sender assignments."""
    lead_ids = request.lead_ids
    if not lead_ids:
        raise HTTPException(status_code=400, detail="No lead IDs provided")

    from app.db.models.sender_mailbox import SenderMailbox
    from app.services.pipelines.outreach import check_send_eligibility

    # Get available Cold Ready / Active mailboxes, least loaded first
    available_mailboxes = db.query(SenderMailbox).filter(
        SenderMailbox.is_active == True,
        SenderMailbox.warmup_status.in_(["cold_ready", "active"]),
        SenderMailbox.emails_sent_today < SenderMailbox.daily_send_limit
    ).order_by(SenderMailbox.emails_sent_today.asc()).all()

    mailbox_list = [
        {"mailbox_id": m.mailbox_id, "email": m.email, "display_name": m.display_name,
         "warmup_status": m.warmup_status.value if hasattr(m.warmup_status, 'value') else str(m.warmup_status),
         "sent_today": m.emails_sent_today, "daily_limit": m.daily_send_limit}
        for m in available_mailboxes
    ]

    assignments = []
    mailbox_idx = 0

    for lid in lead_ids:
        outreach_lead_q = db.query(LeadDetails).filter(LeadDetails.lead_id == lid)
        if tenant_id is not None:
            outreach_lead_q = outreach_lead_q.filter(LeadDetails.tenant_id == tenant_id)
        lead = outreach_lead_q.first()
        if not lead:
            assignments.append({"lead_id": lid, "error": "Lead not found", "contacts": [], "sender": None})
            continue

        # Get contacts
        junction_cids = [row[0] for row in db.query(LeadContactAssociation).with_entities(
            LeadContactAssociation.contact_id
        ).filter(
            LeadContactAssociation.lead_id == lid
        ).all()]

        if junction_cids:
            contacts = db.query(ContactDetails).filter(
                (ContactDetails.lead_id == lid) | (ContactDetails.contact_id.in_(junction_cids))
            ).all()
        else:
            contacts = db.query(ContactDetails).filter(ContactDetails.lead_id == lid).all()

        contact_previews = []
        eligible_count = 0
        for c in contacts:
            eligible, reason = check_send_eligibility(db, c)
            contact_previews.append({
                "contact_id": c.contact_id,
                "name": f"{c.first_name} {c.last_name}".strip(),
                "email": c.email,
                "validation_status": c.validation_status,
                "eligible": eligible,
                "skip_reason": reason if not eligible else None
            })
            if eligible:
                eligible_count += 1

        # Round-robin mailbox assignment for this lead
        sender = None
        if eligible_count > 0 and available_mailboxes:
            mb = available_mailboxes[mailbox_idx % len(available_mailboxes)]
            sender = {"mailbox_id": mb.mailbox_id, "email": mb.email, "display_name": mb.display_name}
            mailbox_idx += 1

        assignments.append({
            "lead_id": lid,
            "client_name": lead.client_name,
            "job_title": lead.job_title,
            "contacts": contact_previews,
            "eligible_count": eligible_count,
            "sender": sender
        })

    return {
        "assignments": assignments,
        "available_mailboxes": mailbox_list,
        "total_leads": len(lead_ids)
    }


@router.post("/bulk/outreach")
async def bulk_outreach_leads(
    request: BulkOutreachRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Trigger outreach for contacts of multiple leads."""
    lead_ids = request.lead_ids
    dry_run = request.dry_run

    if not lead_ids:
        raise HTTPException(status_code=400, detail="No lead IDs provided")
    if len(lead_ids) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 leads per batch")

    from app.services.pipelines.outreach import run_outreach_for_lead as _run

    results = []
    total_sent = 0
    total_skipped = 0
    total_errors = 0

    for lid in lead_ids:
        try:
            # Verify tenant ownership
            if tenant_id is not None:
                owner_check = db.query(LeadDetails).filter(
                    LeadDetails.lead_id == lid,
                    LeadDetails.tenant_id == tenant_id
                ).first()
                if not owner_check:
                    results.append({"lead_id": lid, "error": "Lead not found", "sent": 0, "skipped": 0, "errors": 1})
                    total_errors += 1
                    continue
            result = _run(lead_id=lid, dry_run=dry_run, triggered_by=current_user.email)
            sent = result.get("sent", 0)
            skipped = result.get("skipped", 0)
            errors = result.get("errors", 0)
            entry = {"lead_id": lid, "sent": sent, "skipped": skipped, "errors": errors}
            if "error" in result:
                entry["error"] = result["error"]
            if "message" in result:
                entry["message"] = result["message"]
            results.append(entry)
            total_sent += sent
            total_skipped += skipped
            total_errors += errors
        except Exception as e:
            results.append({"lead_id": lid, "error": str(e), "sent": 0, "skipped": 0, "errors": 1})
            total_errors += 1

    return {
        "total_leads": len(lead_ids),
        "results": results,
        "summary": {"total_sent": total_sent, "total_skipped": total_skipped, "total_errors": total_errors},
        "dry_run": dry_run
    }


@router.get("/{lead_id}/detail")
async def get_lead_detail(
    lead_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Get detailed lead info including contacts and outreach events."""
    detail_q = db.query(LeadDetails).filter(LeadDetails.lead_id == lead_id)
    if tenant_id is not None:
        detail_q = detail_q.filter(LeadDetails.tenant_id == tenant_id)
    lead = detail_q.first()
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found"
        )

    # Get contacts via junction table + legacy FK
    junction_cids = [row[0] for row in db.query(LeadContactAssociation).with_entities(
        LeadContactAssociation.contact_id
    ).filter(
        LeadContactAssociation.lead_id == lead_id
    ).all()]

    if junction_cids:
        contacts = db.query(ContactDetails).filter(
            (ContactDetails.lead_id == lead_id) |
            (ContactDetails.contact_id.in_(junction_cids))
        ).order_by(ContactDetails.priority_level, ContactDetails.created_at).all()
    else:
        contacts = db.query(ContactDetails).filter(
            ContactDetails.lead_id == lead_id
        ).order_by(ContactDetails.priority_level, ContactDetails.created_at).all()

    # Get outreach events for this lead
    outreach_events = db.query(OutreachEvent).filter(
        OutreachEvent.lead_id == lead_id
    ).order_by(OutreachEvent.sent_at.desc()).all()

    # Build lookup dicts for enrichment
    contact_lookup = {c.contact_id: c for c in contacts}
    # Fetch any additional contacts referenced by events but not in junction
    event_contact_ids = {e.contact_id for e in outreach_events if e.contact_id not in contact_lookup}
    if event_contact_ids:
        extra_contacts = db.query(ContactDetails).filter(
            ContactDetails.contact_id.in_(list(event_contact_ids))
        ).all()
        for c in extra_contacts:
            contact_lookup[c.contact_id] = c

    # Sender mailbox lookup
    from app.db.models.sender_mailbox import SenderMailbox
    mailbox_ids = {e.sender_mailbox_id for e in outreach_events if e.sender_mailbox_id}
    mailbox_lookup = {}
    if mailbox_ids:
        mailboxes = db.query(SenderMailbox).filter(
            SenderMailbox.mailbox_id.in_(list(mailbox_ids))
        ).all()
        mailbox_lookup = {m.mailbox_id: m for m in mailboxes}

    # Enrich events
    enriched_events = []
    for e in outreach_events:
        evt = OutreachEventResponse.model_validate(e).model_dump()
        contact = contact_lookup.get(e.contact_id)
        if contact:
            evt["contact_name"] = f"{contact.first_name or ''} {contact.last_name or ''}".strip() or None
            evt["contact_email"] = contact.email
        else:
            evt["contact_name"] = None
            evt["contact_email"] = None
        mailbox = mailbox_lookup.get(e.sender_mailbox_id) if e.sender_mailbox_id else None
        if mailbox:
            evt["sender_email"] = mailbox.email
            evt["sender_name"] = mailbox.display_name or mailbox.email
        else:
            evt["sender_email"] = None
            evt["sender_name"] = None
        enriched_events.append(evt)

    lead_dict = LeadResponse.model_validate(lead).model_dump()
    lead_dict['contact_count'] = len(contacts)
    lead_dict['contacts'] = [ContactResponse.model_validate(c).model_dump() for c in contacts]
    lead_dict['outreach_events'] = enriched_events

    # Enrich with industry/company_size (prefer lead, fallback to client_info)
    if not lead.industry or not lead.company_size:
        ci = db.query(ClientInfo).filter(ClientInfo.client_name == lead.client_name).first()
        if ci:
            lead_dict['industry'] = lead.industry or ci.industry
            lead_dict['company_size'] = lead.company_size or ci.company_size
        else:
            lead_dict['industry'] = lead.industry
            lead_dict['company_size'] = lead.company_size
    else:
        lead_dict['industry'] = lead.industry
        lead_dict['company_size'] = lead.company_size

    _cstatus, _cid, _mstatus = _campaign_fields_for_lead(db, lead)
    lead_dict['campaign_status'] = _cstatus
    lead_dict['campaign_id'] = _cid
    lead_dict['mailing_status'] = _mstatus

    return lead_dict



@router.post("/{lead_id}/contacts")
async def manage_lead_contacts(
    lead_id: int,
    request: ManageContactsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Add or remove contact associations for a lead."""
    manage_q = db.query(LeadDetails).filter(LeadDetails.lead_id == lead_id)
    if tenant_id is not None:
        manage_q = manage_q.filter(LeadDetails.tenant_id == tenant_id)
    lead = manage_q.first()
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found"
        )

    add_ids = request.add_contact_ids
    remove_ids = request.remove_contact_ids

    added = 0
    removed = 0

    for cid in add_ids:
        contact = db.query(ContactDetails).filter(ContactDetails.contact_id == cid).first()
        if not contact:
            continue
        existing = db.query(LeadContactAssociation).filter(
            LeadContactAssociation.lead_id == lead_id,
            LeadContactAssociation.contact_id == cid
        ).first()
        if not existing:
            assoc = LeadContactAssociation(lead_id=lead_id, contact_id=cid)
            db.add(assoc)
            added += 1

    for cid in remove_ids:
        deleted = db.query(LeadContactAssociation).filter(
            LeadContactAssociation.lead_id == lead_id,
            LeadContactAssociation.contact_id == cid
        ).delete(synchronize_session=False)
        removed += deleted

    db.commit()

    return {
        "message": f"Added {added}, removed {removed} contact associations",
        "added": added,
        "removed": removed,
        "lead_id": lead_id
    }


@router.post("/{lead_id}/outreach")
async def run_outreach_for_lead(
    lead_id: int,
    dry_run: bool = Query(True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Trigger outreach for contacts of a specific lead."""
    outreach_q = db.query(LeadDetails).filter(LeadDetails.lead_id == lead_id)
    if tenant_id is not None:
        outreach_q = outreach_q.filter(LeadDetails.tenant_id == tenant_id)
    lead = outreach_q.first()
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found"
        )

    from app.services.pipelines.outreach import run_outreach_for_lead as _run
    result = _run(lead_id=lead_id, dry_run=dry_run, triggered_by=current_user.email, tenant_id=tenant_id)

    return result


@router.get("/{lead_id}", response_model=LeadResponse)
async def get_lead(
    lead_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Get lead by ID."""
    get_q = db.query(LeadDetails).filter(LeadDetails.lead_id == lead_id)
    if tenant_id is not None:
        get_q = get_q.filter(LeadDetails.tenant_id == tenant_id)
    lead = get_q.first()
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found"
        )
    resp = LeadResponse.model_validate(lead)
    resp.campaign_status, resp.campaign_id, resp.mailing_status = _campaign_fields_for_lead(db, lead)
    return resp


@router.post("", response_model=LeadResponse, status_code=status.HTTP_201_CREATED)
async def create_lead(
    lead_in: LeadCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Create a new lead."""
    check_plan_limit(db, tenant_id, "leads")

    if lead_in.job_link:
        dup_check_q = db.query(LeadDetails).filter(LeadDetails.job_link == lead_in.job_link)
        dup_check_q = tenant_filter(dup_check_q, LeadDetails, tenant_id)
        existing = dup_check_q.first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Lead with this job link already exists"
            )

    lead = LeadDetails(**lead_in.model_dump())
    lead.tenant_id = tenant_id or 1  # fallback for super admin without X-Tenant-ID

    # Exclusion gate — an out-of-scope lead is recorded (auditable) but marked
    # terminal (EXCLUDED) so contact enrichment never spends API on it.
    from app.services.lead_eligibility import check_lead_eligibility
    eligible, reason = check_lead_eligibility(
        db, lead, tenant_id=tenant_id, lob_id=getattr(lead, "lob_id", None)
    )
    if not eligible:
        lead.lead_status = LeadStatus.EXCLUDED
        lead.skip_reason = f"excluded: {reason}"

    db.add(lead)
    db.commit()
    db.refresh(lead)

    return LeadResponse.model_validate(lead)


@router.put("/{lead_id}", response_model=LeadResponse)
async def update_lead(
    lead_id: int,
    lead_in: LeadUpdate,
    force: bool = Query(
        False,
        description="Bypass the lead-status state-machine (admin/super_admin only). "
                    "Requires an explicit user confirmation on the frontend.",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Update lead."""
    update_q = db.query(LeadDetails).filter(LeadDetails.lead_id == lead_id)
    if tenant_id is not None:
        update_q = update_q.filter(LeadDetails.tenant_id == tenant_id)
    lead = update_q.first()
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found"
        )

    update_data = lead_in.model_dump(exclude_unset=True)

    # Validate status transition if status is changing
    forced_transition = False
    if "lead_status" in update_data and update_data["lead_status"] != lead.lead_status:
        new_status = update_data["lead_status"]
        if isinstance(new_status, str):
            new_status = LeadStatus(new_status)
        if not validate_transition(lead.lead_status, new_status):
            # Admins/super-admins may override a blocked transition when they
            # explicitly pass force=true (confirmed via a frontend popup).
            can_override = current_user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN)
            if force and can_override:
                forced_transition = True
            else:
                allowed = get_allowed_transitions(lead.lead_status)
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot transition from '{lead.lead_status.value}' to '{new_status.value}'. Allowed: {allowed}"
                )

    # Track changes for audit
    changes = {}
    for field, value in update_data.items():
        old_val = getattr(lead, field, None)
        if old_val != value:
            old_str = old_val.value if hasattr(old_val, 'value') else str(old_val) if old_val is not None else None
            new_str = value.value if hasattr(value, 'value') else str(value) if value is not None else None
            changes[field] = {"old": old_str, "new": new_str}
        setattr(lead, field, value)

    if forced_transition:
        changes["forced_transition"] = {"old": None, "new": True}

    if changes:
        _audit(db, "lead", lead.lead_id, "update", changes, changed_by=current_user.email)

    db.commit()
    db.refresh(lead)

    return LeadResponse.model_validate(lead)


@router.delete("/{lead_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lead(
    lead_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Archive lead (soft delete)."""
    delete_q = db.query(LeadDetails).filter(LeadDetails.lead_id == lead_id)
    if tenant_id is not None:
        delete_q = delete_q.filter(LeadDetails.tenant_id == tenant_id)
    lead = delete_q.first()
    if not lead:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found"
        )

    # Soft delete: archive instead of hard deleting
    lead.is_archived = True
    _audit(db, "lead", lead.lead_id, "archive",
           {"is_archived": {"old": False, "new": True}},
           changed_by=current_user.email)
    db.commit()
