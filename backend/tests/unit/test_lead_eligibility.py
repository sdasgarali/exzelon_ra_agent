"""Unit tests for the centralized LeadEligibilityGate.

The gate is the single source of truth for "is this lead in scope" and the
foolproof guard that prevents paid API spend on unwanted leads. These tests
prove each exclusion rule fires and that unknown metadata is never dropped.
"""
import pytest

from app.services.lead_eligibility import LeadEligibilityGate, check_lead_eligibility
from app.db.models.company_exclusion import (
    CompanyExclusion,
    normalize_company_for_exclusion,
)

pytestmark = pytest.mark.unit


def _lead(**over):
    base = {
        "client_name": "Northwind Traders",
        "job_title": "HR Manager",
        "industry": "Manufacturing",
        "company_size": "120",
        "salary_min": None,
        "salary_max": None,
        "lob_id": None,
    }
    base.update(over)
    return base


class TestGateRules:
    def test_eligible_lead_passes(self, db_session, test_tenant):
        gate = LeadEligibilityGate(db_session, tenant_id=test_tenant.tenant_id)
        eligible, reason = gate.check(_lead())
        assert eligible is True
        assert reason is None

    def test_placeholder_company_excluded(self, db_session, test_tenant):
        gate = LeadEligibilityGate(db_session, tenant_id=test_tenant.tenant_id)
        eligible, reason = gate.check(_lead(client_name="Confidential"))
        assert eligible is False
        assert reason == "placeholder_company"

    def test_blank_company_excluded(self, db_session, test_tenant):
        gate = LeadEligibilityGate(db_session, tenant_id=test_tenant.tenant_id)
        eligible, reason = gate.check(_lead(client_name=""))
        assert eligible is False
        assert reason == "placeholder_company"

    def test_it_industry_excluded(self, db_session, test_tenant):
        gate = LeadEligibilityGate(db_session, tenant_id=test_tenant.tenant_id)
        eligible, reason = gate.check(_lead(industry="Information Technology"))
        assert eligible is False
        assert reason == "industry_excluded"

    def test_oversized_company_excluded(self, db_session, test_tenant):
        gate = LeadEligibilityGate(db_session, tenant_id=test_tenant.tenant_id)
        eligible, reason = gate.check(_lead(company_size="5000+"))
        assert eligible is False
        assert reason == "size_ceiling"

    def test_self_reported_band_over_ceiling_excluded(self, db_session, test_tenant):
        """R1603: a company whose stored size is the self-reported band
        "1001-5000" must be dropped even though its tagged-member headcount is low."""
        gate = LeadEligibilityGate(db_session, tenant_id=test_tenant.tenant_id)
        eligible, reason = gate.check(_lead(company_size="1001-5000"))
        assert eligible is False
        assert reason == "size_ceiling"

    def test_conservative_across_headcount_and_band(self, db_session, test_tenant):
        """When both signals are present, the LARGEST wins the drop decision — an
        understated headcount of 156 must not rescue a 1001-5000 company."""
        gate = LeadEligibilityGate(db_session, tenant_id=test_tenant.tenant_id)
        eligible, reason = gate.check(
            _lead(company_size="1001-5000", _employee_count=156)
        )
        assert eligible is False
        assert reason == "size_ceiling"

    def test_band_just_over_200_ceiling_excluded(self, db_session, test_tenant):
        gate = LeadEligibilityGate(db_session, tenant_id=test_tenant.tenant_id)
        eligible, reason = gate.check(_lead(company_size="201-500"))
        assert eligible is False
        assert reason == "size_ceiling"

    def test_staffing_keyword_in_company_excluded(self, db_session, test_tenant):
        gate = LeadEligibilityGate(db_session, tenant_id=test_tenant.tenant_id)
        eligible, reason = gate.check(_lead(client_name="Acme Staffing Agency"))
        assert eligible is False
        assert reason == "keyword_excluded"

    def test_salary_below_floor_excluded(self, db_session, test_tenant):
        gate = LeadEligibilityGate(db_session, tenant_id=test_tenant.tenant_id)
        eligible, reason = gate.check(_lead(salary_min=20000, salary_max=28000))
        assert eligible is False
        assert reason == "salary_below_threshold"

    def test_unknown_industry_and_size_passes(self, db_session, test_tenant):
        """Recall preserved — unknown metadata is never dropped by the gate."""
        gate = LeadEligibilityGate(db_session, tenant_id=test_tenant.tenant_id)
        eligible, reason = gate.check(_lead(industry=None, company_size=None))
        assert eligible is True
        assert reason is None

    def test_job_type_excluded_fires(self, db_session, test_tenant):
        """Configured job type is dropped; matching is format/case-agnostic
        (raw 'PARTTIME' normalizes to the configured 'Part-time')."""
        gate = LeadEligibilityGate(db_session, tenant_id=test_tenant.tenant_id)
        gate.exclude_job_types = {"Part-time"}
        eligible, reason = gate.check(_lead(employment_type="PARTTIME"))
        assert eligible is False
        assert reason == "job_type_excluded"

    def test_job_type_unknown_not_dropped(self, db_session, test_tenant):
        """Blank/unknown employment type is never dropped (recall preserved)."""
        gate = LeadEligibilityGate(db_session, tenant_id=test_tenant.tenant_id)
        gate.exclude_job_types = {"Part-time"}
        eligible, reason = gate.check(_lead(employment_type=""))
        assert eligible is True
        assert reason is None

    def test_job_type_not_configured_passes(self, db_session, test_tenant):
        """No exclusions configured → every employment type passes the gate."""
        gate = LeadEligibilityGate(db_session, tenant_id=test_tenant.tenant_id)
        assert gate.exclude_job_types == set()
        eligible, reason = gate.check(_lead(employment_type="Part-time"))
        assert eligible is True
        assert reason is None

    def test_insurance_industry_excluded(self, db_session, test_tenant):
        gate = LeadEligibilityGate(db_session, tenant_id=test_tenant.tenant_id)
        eligible, reason = gate.check(_lead(industry="Insurance"))
        assert eligible is False
        assert reason == "industry_excluded"

    def test_insurance_company_name_excluded(self, db_session, test_tenant):
        gate = LeadEligibilityGate(db_session, tenant_id=test_tenant.tenant_id)
        eligible, reason = gate.check(_lead(client_name="Auto-Owners Insurance Company"))
        assert eligible is False
        assert reason == "keyword_excluded"

    def test_default_floor_keeps_small_company(self, db_session, test_tenant):
        """Default floor is 1 → tiny companies are still kept."""
        gate = LeadEligibilityGate(db_session, tenant_id=test_tenant.tenant_id)
        eligible, reason = gate.check(_lead(company_size="2-10 employees"))
        assert eligible is True
        assert reason is None

    def test_size_floor_drops_below_minimum(self, db_session, test_tenant):
        """Raising the floor drops companies under the minimum ICP size."""
        gate = LeadEligibilityGate(db_session, tenant_id=test_tenant.tenant_id)
        gate.min_employee_count = 50
        eligible, reason = gate.check(_lead(company_size="2-10 employees"))
        assert eligible is False
        assert reason == "size_floor"

    def test_needs_resolution_flags_unknowns(self, db_session, test_tenant):
        gate = LeadEligibilityGate(db_session, tenant_id=test_tenant.tenant_id)
        assert gate.needs_resolution(_lead(industry=None)) is True
        assert gate.needs_resolution(_lead(company_size=None)) is True
        assert gate.needs_resolution(_lead()) is False


class TestCompanyExclusionList:
    def test_globally_excluded_company(self, db_session, test_tenant):
        name = "Globex Corporation"
        db_session.add(CompanyExclusion(
            tenant_id=test_tenant.tenant_id,
            lob_id=None,
            company_name=name,
            company_name_normalized=normalize_company_for_exclusion(name),
            is_active=True,
        ))
        db_session.commit()

        gate = LeadEligibilityGate(db_session, tenant_id=test_tenant.tenant_id)
        eligible, reason = gate.check(_lead(client_name="Globex Corp"))  # normalizes equal
        assert eligible is False
        assert reason == "excluded_company_list"

    def test_inactive_exclusion_ignored(self, db_session, test_tenant):
        name = "Initech"
        db_session.add(CompanyExclusion(
            tenant_id=test_tenant.tenant_id,
            lob_id=None,
            company_name=name,
            company_name_normalized=normalize_company_for_exclusion(name),
            is_active=False,
        ))
        db_session.commit()

        gate = LeadEligibilityGate(db_session, tenant_id=test_tenant.tenant_id)
        eligible, _ = gate.check(_lead(client_name="Initech"))
        assert eligible is True


class TestConvenienceHelper:
    def test_check_lead_eligibility_one_shot(self, db_session, test_tenant):
        eligible, reason = check_lead_eligibility(
            db_session, _lead(industry="IT Services"), tenant_id=test_tenant.tenant_id
        )
        assert eligible is False
        assert reason == "industry_excluded"
