"""Dedup must ignore archived leads so the pipeline can re-source and
re-evaluate previously-archived postings as fresh leads."""
import pytest

from app.services.pipelines.lead_sourcing import deduplicate_jobs
from app.db.models.lead import LeadDetails, LeadStatus

pytestmark = pytest.mark.unit


def _mk_lead(db, tenant_id, ext_id, archived):
    lead = LeadDetails(
        tenant_id=tenant_id,
        client_name="Acme Corp",
        job_title="Operations Manager",
        state="TX",
        external_job_id=ext_id,
        job_link=f"https://jobs.example.com/{ext_id}",
        is_archived=archived,
        lead_status=LeadStatus.NEW,
    )
    db.add(lead)
    db.commit()
    return lead


def _job(ext_id):
    return {
        "external_job_id": ext_id,
        "client_name": "Acme Corp",
        "job_title": "Operations Manager",
        "state": "TX",
        "job_link": f"https://jobs.example.com/{ext_id}",
    }


def test_archived_lead_does_not_block_new(db_session, test_tenant):
    """An archived lead is ignored by all dedup layers → the matching incoming
    posting survives and can be re-sourced."""
    _mk_lead(db_session, test_tenant.tenant_id, "EXT-ARCH", archived=True)
    out = deduplicate_jobs([_job("EXT-ARCH")], db_session, tenant_id=test_tenant.tenant_id)
    assert len(out) == 1


def test_active_lead_still_blocks_new(db_session, test_tenant):
    """A non-archived lead still de-duplicates the matching incoming posting."""
    _mk_lead(db_session, test_tenant.tenant_id, "EXT-ACTIVE", archived=False)
    out = deduplicate_jobs([_job("EXT-ACTIVE")], db_session, tenant_id=test_tenant.tenant_id)
    assert len(out) == 0
