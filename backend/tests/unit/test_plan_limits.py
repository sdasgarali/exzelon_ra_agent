"""Plan-limit enforcement tests (ELR-011).

The shared `test_tenant` fixture is always ENTERPRISE, which short-circuits
`check_plan_limit` — so before this file the cap-enforcement branches had ZERO
coverage. These use the `starter_tenant` / `professional_capped_tenant` fixtures.
"""
import pytest
from fastapi import HTTPException

from app.api.deps.plan_limits import check_plan_limit
from app.db.models.contact import ContactDetails

pytestmark = pytest.mark.unit


def _add_contacts(db, tenant_id, n):
    for i in range(n):
        db.add(ContactDetails(
            tenant_id=tenant_id, client_name="C", first_name="F",
            last_name="L", email=f"c{i}-{tenant_id}@x.com",
        ))
    db.commit()


def test_starter_plan_blocks_paid_resource(db_session, starter_tenant):
    with pytest.raises(HTTPException) as exc:
        check_plan_limit(db_session, starter_tenant.tenant_id, "contacts")
    assert exc.value.status_code == 403


def test_enterprise_never_blocked(db_session, test_tenant):
    # test_tenant is ENTERPRISE — no cap regardless of count.
    check_plan_limit(db_session, test_tenant.tenant_id, "contacts")


def test_super_admin_bypass(db_session):
    check_plan_limit(db_session, None, "contacts")


def test_professional_cap_reached_raises_403(db_session, professional_capped_tenant):
    tid = professional_capped_tenant.tenant_id  # max_contacts = 2
    _add_contacts(db_session, tid, 2)
    with pytest.raises(HTTPException) as exc:
        check_plan_limit(db_session, tid, "contacts")
    assert exc.value.status_code == 403


def test_professional_under_cap_passes(db_session, professional_capped_tenant):
    tid = professional_capped_tenant.tenant_id  # max_contacts = 2
    _add_contacts(db_session, tid, 1)
    check_plan_limit(db_session, tid, "contacts")  # no raise
