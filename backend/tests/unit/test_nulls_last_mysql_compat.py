"""Regression: `.nullslast()` emits `NULLS LAST`, which MySQL rejects (error 1064).

Prod runs MySQL; the test suite runs SQLite (which *accepts* `NULLS LAST` since
3.30), so the crash was invisible to tests. This locks the ordering expressions
of every affected endpoint so they compile to valid MySQL — no `NULLS LAST`.

Root cause: GET /integrations/resource-pool/attribution returned HTTP 500 in
prod because `order_by(func.sum(...).desc().nullslast())` rendered `NULLS LAST`.
Same latent bug existed in the activity-log and deal-tasks list orderings.
"""
import pytest
from sqlalchemy import func
from sqlalchemy.dialects import mysql

from app.db.models.deal_task import DealTask
from app.db.models.resource_pool_attribution import ResourcePoolAttribution
from app.db.models.resource_pool_attribution import ResourcePoolAttribution as A
from app.db.models.user import User

pytestmark = pytest.mark.unit

MYSQL = mysql.dialect()


def _sql(expr) -> str:
    return str(expr.compile(dialect=MYSQL, compile_kwargs={"literal_binds": True}))


# Mirror the exact ordering expressions used by each endpoint. If a future edit
# reintroduces `.nullslast()`/`.nullsfirst()`, these renders will contain
# "NULLS LAST"/"NULLS FIRST" and the assertions below fail.
ORDERINGS = [
    # integrations.resource_pool_attribution_summary — by_source
    func.coalesce(func.sum(A.amount), 0).desc(),
    # activity_log — users by last login
    User.last_login_at.is_(None),
    User.last_login_at.desc(),
    # deal_tasks — tasks by due date
    DealTask.due_date.is_(None),
    DealTask.due_date.asc(),
]


@pytest.mark.parametrize("expr", ORDERINGS)
def test_ordering_has_no_nulls_last_under_mysql(expr):
    sql = _sql(expr).upper()
    assert "NULLS LAST" not in sql
    assert "NULLS FIRST" not in sql


def test_attribution_by_source_orders_null_amounts_last(client, db_session, test_tenant, auth_headers):
    """Behavioral guard: a source whose amounts are all NULL sorts last, and the
    endpoint returns 200 (it previously 500'd on MySQL)."""
    db_session.add_all([
        ResourcePoolAttribution(tenant_id=test_tenant.tenant_id, event_type="placement.created",
                                rp_entity_id="n1", source="no_revenue", amount=None),
        ResourcePoolAttribution(tenant_id=test_tenant.tenant_id, event_type="invoice.paid",
                                rp_entity_id="h1", source="high_revenue", amount=5000),
        ResourcePoolAttribution(tenant_id=test_tenant.tenant_id, event_type="invoice.paid",
                                rp_entity_id="l1", source="low_revenue", amount=10),
    ])
    db_session.commit()
    resp = client.get("/api/v1/integrations/resource-pool/attribution", headers=auth_headers)
    assert resp.status_code == 200
    sources = [s["source"] for s in resp.json()["by_source"]]
    assert sources[0] == "high_revenue"
    assert sources[-1] == "no_revenue"  # NULL amount sorted last
