"""Centralized lead-eligibility gate — the single source of truth for whether a
lead/company is in scope for outreach.

Why this exists
---------------
Exclusion filters historically ran ONLY at lead sourcing (``_apply_company_gate``)
and worked by dropping jobs before DB insert. The contact-enrichment pipeline
then trusted the DB and re-checked nothing before calling paid contact-discovery
APIs — so any lead that entered via a different path (file import, ``POST
/leads``, bulk import, ad-hoc search) reached those paid APIs unfiltered.

This module re-applies the SAME rules as ``_apply_company_gate`` (plus keyword
and salary filters) at a choke-point immediately before any paid API call,
regardless of how the lead was created. That is what makes "no API spend on
unwanted leads" foolproof rather than best-effort.

Design
------
``LeadEligibilityGate`` loads all tenant settings and the company-exclusion set
ONCE (cheap for a 500-lead batch — avoids per-lead settings queries). ``check``
is then a pure, side-effect-free evaluation returning ``(eligible, reason)``.

Unknown industry/size never triggers a drop here — the caller is expected to run
the FREE metadata resolver first (see ``needs_resolution``) so unknowns are
filled before the final decision, preserving recall.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional, Tuple

import structlog

from app.core.config import settings
from app.core.settings_resolver import get_tenant_setting
from app.services.company_filters import (
    exceeds_size_ceiling,
    industry_is_excluded,
    is_placeholder_company,
    salary_below_threshold,
)

logger = structlog.get_logger()


def _field(obj: Any, key: str) -> Any:
    """Read ``key`` from an ORM object or a plain dict, tolerating either."""
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


class LeadEligibilityGate:
    """Reusable, batch-friendly exclusion gate.

    Build once per tenant/run, then call :meth:`check` per lead.
    """

    def __init__(self, db, tenant_id: Optional[int] = None, lob_id: Optional[int] = None):
        self.db = db
        self.tenant_id = tenant_id
        self.lob_id = lob_id

        # --- Company size / industry / placeholder ---
        self.max_employee_count = int(
            get_tenant_setting(
                db, "lead_sourcing_max_employee_count",
                tenant_id=tenant_id, default=settings.LEAD_SOURCING_MAX_EMPLOYEE_COUNT,
            )
        )
        self.drop_confidential = bool(
            get_tenant_setting(
                db, "lead_sourcing_drop_confidential",
                tenant_id=tenant_id, default=settings.LEAD_SOURCING_DROP_CONFIDENTIAL,
            )
        )
        excluded_industries = get_tenant_setting(
            db, "lead_sourcing_excluded_industries",
            tenant_id=tenant_id, default=settings.EXCLUDED_INDUSTRY_KEYWORDS,
        )
        if not isinstance(excluded_industries, list) or not excluded_industries:
            from app.services.company_filters import DEFAULT_EXCLUDED_INDUSTRY_KEYWORDS
            excluded_industries = DEFAULT_EXCLUDED_INDUSTRY_KEYWORDS
        self.excluded_industries = excluded_industries

        # --- Salary floor ---
        self.min_salary_threshold = int(
            get_tenant_setting(
                db, "min_salary_threshold",
                tenant_id=tenant_id, default=settings.MIN_SALARY_THRESHOLD,
            )
        )

        # --- Keyword exclusions (company + title + IT + staffing) ---
        it_kw = get_tenant_setting(
            db, "exclude_it_keywords", tenant_id=tenant_id, default=settings.EXCLUDE_IT_KEYWORDS
        )
        staffing_kw = get_tenant_setting(
            db, "exclude_staffing_keywords", tenant_id=tenant_id, default=settings.EXCLUDE_STAFFING_KEYWORDS
        )
        self.exclude_keywords = list(it_kw or []) + list(staffing_kw or [])
        self.exclude_company_keywords = get_tenant_setting(
            db, "exclude_company_keywords", tenant_id=tenant_id, default=settings.EXCLUDE_COMPANY_KEYWORDS
        )
        self.exclude_title_keywords = get_tenant_setting(
            db, "exclude_title_keywords", tenant_id=tenant_id, default=settings.EXCLUDE_TITLE_KEYWORDS
        )
        self.match_mode = get_tenant_setting(
            db, "exclude_match_mode", tenant_id=tenant_id, default="word_boundary"
        )

        # --- Manual company exclusion list (tenant + LOB scoped) ---
        # Loaded once, bucketed by lob_id so a batch spanning multiple LOBs (the
        # enrichment auto-path selects all NEW leads regardless of LOB) matches
        # each lead against global (lob_id NULL) + its own LOB's exclusions.
        self._excl_global, self._excl_by_lob, self._normalize = self._load_company_exclusions()

    def _load_company_exclusions(self):
        try:
            from app.db.models.company_exclusion import (
                CompanyExclusion,
                normalize_company_for_exclusion,
            )
        except Exception:  # pragma: no cover - defensive
            return set(), {}, (lambda s: (s or "").strip().lower())

        global_set: set = set()
        by_lob: dict = {}
        try:
            q = self.db.query(
                CompanyExclusion.company_name_normalized, CompanyExclusion.lob_id
            ).filter(
                CompanyExclusion.tenant_id == (self.tenant_id or 1),
                CompanyExclusion.is_active == True,  # noqa: E712
            )
            # If the gate is pinned to one LOB, only that LOB's rows are relevant.
            if self.lob_id:
                q = q.filter(
                    (CompanyExclusion.lob_id == self.lob_id)
                    | (CompanyExclusion.lob_id == None)  # noqa: E711
                )
            for norm, lob in q.all():
                if lob is None:
                    global_set.add(norm)
                else:
                    by_lob.setdefault(lob, set()).add(norm)
        except Exception as e:
            logger.warning("Failed to load company exclusions for gate", error=str(e))
        return global_set, by_lob, normalize_company_for_exclusion

    # ------------------------------------------------------------------
    def needs_resolution(self, lead: Any) -> bool:
        """True when the lead's industry/size is unknown AND could still flip the
        decision — i.e. resolving it (free) is worth doing before the paid call.
        """
        industry = _field(lead, "industry")
        size = _field(lead, "company_size") or _field(lead, "_employee_count")
        return not industry or not size

    def check(self, lead: Any) -> Tuple[bool, Optional[str]]:
        """Return ``(eligible, reason)``. ``reason`` is None when eligible.

        Unknown industry/size never causes a drop (recall preserved); resolve
        first via the metadata batch if you want unknowns decided.
        """
        client_name = _field(lead, "client_name")

        # 1) Placeholder / confidential / blank employer.
        if self.drop_confidential and is_placeholder_company(client_name):
            return False, "placeholder_company"

        # 2) Manually-excluded company (tenant global + this lead's LOB blacklist).
        if self._excl_global or self._excl_by_lob:
            norm = self._normalize(client_name or "")
            if norm:
                if norm in self._excl_global:
                    return False, "excluded_company_list"
                lob = _field(lead, "lob_id")
                if lob is not None and norm in self._excl_by_lob.get(lob, ()):
                    return False, "excluded_company_list"

        # 3) Keyword exclusions (IT/staffing on title+company, company-only, title-only).
        job_like = {
            "job_title": _field(lead, "job_title") or "",
            "client_name": client_name or "",
        }
        from app.services.adapters.base import JobSourceAdapter
        if JobSourceAdapter.filter_excluded(
            job_like,
            exclude_keywords=self.exclude_keywords,
            exclude_company_keywords=self.exclude_company_keywords,
            exclude_title_keywords=self.exclude_title_keywords,
            match_mode=self.match_mode,
        ):
            return False, "keyword_excluded"

        # 4) Salary floor (only drops on a KNOWN below-threshold salary).
        if salary_below_threshold(
            _field(lead, "salary_min"), _field(lead, "salary_max"), self.min_salary_threshold
        ):
            return False, "salary_below_threshold"

        # 5) Industry (unknown → not excluded).
        if industry_is_excluded(_field(lead, "industry"), self.excluded_industries):
            return False, "industry_excluded"

        # 6) Size ceiling (unknown → not excluded).
        size_signal = _field(lead, "_employee_count")
        if size_signal is None:
            size_signal = _field(lead, "company_size")
        if exceeds_size_ceiling(size_signal, self.max_employee_count):
            return False, "size_ceiling"

        return True, None


def check_lead_eligibility(
    db, lead: Any, tenant_id: Optional[int] = None, lob_id: Optional[int] = None
) -> Tuple[bool, Optional[str]]:
    """Convenience one-shot check for single-lead call sites (create endpoint,
    ad-hoc search). Builds a gate and evaluates one lead.

    For batches use :class:`LeadEligibilityGate` directly to avoid reloading
    settings/exclusions per lead.
    """
    return LeadEligibilityGate(db, tenant_id=tenant_id, lob_id=lob_id).check(lead)
