"""The plan-rename migration against real legacy rows (Phase 5.4).

`test_alembic_baseline.py` proves the chain builds a schema from nothing. This proves
it does the right thing to data that already exists — which is the only case that can
actually hurt a paying customer.

Each test seeds a database at revision 0001 with starter/professional/enterprise
tenants, runs `alembic upgrade head` in a subprocess against the real `env.py`, and
inspects the result. A subprocess rather than in-process so the migration runs exactly
as it will in production, with its own engine and no test fixtures in scope.
"""
import os
import pathlib
import sqlite3
import subprocess
import sys

import pytest

pytestmark = pytest.mark.integration

_BACKEND = pathlib.Path(__file__).resolve().parents[2]


def _alembic(dbfile: pathlib.Path, *args: str):
    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{dbfile}",
        "ENCRYPTION_KEY": "kbt_mh7zLmsYjFAGgX_MAVtAousWEe7CQUtbNsi9m44=",
        "SECRET_KEY": "test-secret-key-not-for-production",
    }
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=str(_BACKEND), env=env, capture_output=True, text=True, timeout=300,
    )


@pytest.fixture
def legacy_db(tmp_path):
    """A database at 0001_baseline holding pre-rename tenants.

    Limits are deliberately varied: one tenant carries hand-set values (the support
    grant case) and one carries the all-zero row that the old signup path produced —
    the bug this whole workstream started from.
    """
    dbfile = tmp_path / "legacy.db"

    r = _alembic(dbfile, "upgrade", "0001_baseline")
    assert r.returncode == 0, f"baseline failed:\n{r.stdout}\n{r.stderr}"

    rows = [
        # The broken self-signup row: every limit zero.
        dict(name="Zero Co", slug="zero-co", plan="starter", max_users=3,
             max_mailboxes=0, max_contacts=0, max_campaigns=0, max_leads=0),
        # A hand-tuned professional tenant — a support grant that must survive.
        dict(name="Granted Co", slug="granted-co", plan="professional", max_users=25,
             max_mailboxes=60, max_contacts=90_000, max_campaigns=40, max_leads=120_000),
        # A big enterprise tenant.
        dict(name="Big Co", slug="big-co", plan="enterprise", max_users=999,
             max_mailboxes=999, max_contacts=999_999, max_campaigns=999, max_leads=999_999),
    ]

    con = sqlite3.connect(str(dbfile))
    try:
        # Fill every other NOT NULL column from the schema rather than naming them
        # here. SQLAlchemy's Python-side `default=` does not apply to raw SQL, and a
        # hardcoded column list would break this test each time someone adds a NOT
        # NULL column to `tenants` — noise that has nothing to do with the rename.
        schema = [
            {"name": c[1], "type": (c[2] or "").upper(), "notnull": c[3], "default": c[4]}
            for c in con.execute("PRAGMA table_info(tenants)")
        ]
        for row in rows:
            for col in schema:
                if col["name"] in row or not col["notnull"] or col["default"] is not None:
                    continue
                if col["name"] in ("tenant_id",):
                    continue
                row[col["name"]] = (
                    "2026-01-01 00:00:00"
                    if "DATE" in col["type"] or "TIME" in col["type"]
                    else 0 if any(t in col["type"] for t in ("INT", "NUM", "FLOAT", "REAL", "BOOL"))
                    else ""
                )
            cols = ", ".join(row)
            placeholders = ", ".join("?" for _ in row)
            con.execute(
                f"INSERT INTO tenants ({cols}) VALUES ({placeholders})",
                list(row.values()),
            )
        con.commit()
    finally:
        con.close()
    return dbfile


def _tenants(dbfile) -> dict:
    con = sqlite3.connect(str(dbfile))
    try:
        cols = [c[1] for c in con.execute("PRAGMA table_info(tenants)")]
        rows = con.execute(f"SELECT {', '.join(cols)} FROM tenants").fetchall()
        return {r[cols.index("slug")]: dict(zip(cols, r)) for r in rows}
    finally:
        con.close()


def test_legacy_plans_map_to_the_new_names(legacy_db):
    r = _alembic(legacy_db, "upgrade", "head")
    assert r.returncode == 0, f"upgrade failed:\n{r.stdout}\n{r.stderr}"

    tenants = _tenants(legacy_db)
    assert tenants["zero-co"]["plan"] == "free"
    assert tenants["granted-co"]["plan"] == "pro"
    assert tenants["big-co"]["plan"] == "max"


def test_hand_set_limits_survive_the_migration(legacy_db):
    """A support grant must not be silently reset by a rename.

    The migration deliberately does not backfill limits — `limits_for_tenant()` treats
    a positive column as an explicit per-tenant value — so these have to come through
    untouched.
    """
    _alembic(legacy_db, "upgrade", "head")
    granted = _tenants(legacy_db)["granted-co"]

    assert granted["max_users"] == 25
    assert granted["max_mailboxes"] == 60
    assert granted["max_contacts"] == 90_000
    assert granted["max_campaigns"] == 40
    assert granted["max_leads"] == 120_000


def test_the_all_zero_row_is_left_alone_and_self_heals(legacy_db):
    """The signup-lockout row must stay zero in the DB and resolve to Free in code.

    Rewriting it during the migration would have been the obvious fix and the wrong
    one: it would freeze today's Free numbers into every old row, so the next pricing
    change would skip exactly the customers who never had explicit limits.
    """
    from app.core.plans import PLAN_MATRIX, limits_for_tenant

    _alembic(legacy_db, "upgrade", "head")
    row = _tenants(legacy_db)["zero-co"]

    assert row["max_mailboxes"] == 0
    assert row["max_lobs"] == 0, "new limit columns must default to 'use the plan'"

    class _Row:
        pass
    tenant = _Row()
    for k, v in row.items():
        setattr(tenant, k, v)

    resolved = limits_for_tenant(tenant)
    free = PLAN_MATRIX["free"]
    assert resolved["max_mailboxes"] == free.max_mailboxes > 0
    assert resolved["max_lobs"] == free.max_lobs > 0
    assert resolved["max_campaigns"] == free.max_campaigns > 0


def test_max_lobs_does_not_cap_existing_max_tenants(legacy_db):
    """Regression for the bug found in Phase 4.

    The column originally shipped with `server_default="1"`, which stamped an explicit
    one-LOB cap onto every existing row — capping Max customers entitled to 25.
    """
    from app.core.plans import PLAN_MATRIX, limits_for_tenant

    _alembic(legacy_db, "upgrade", "head")
    row = _tenants(legacy_db)["big-co"]
    assert row["max_lobs"] == 0

    class _Row:
        pass
    tenant = _Row()
    for k, v in row.items():
        setattr(tenant, k, v)

    assert limits_for_tenant(tenant)["max_lobs"] == PLAN_MATRIX["max"].max_lobs == 25


def test_migration_is_reversible(legacy_db):
    """Downgrade has to work, or a bad deploy cannot be rolled back.

    `custom` has no pre-rename equivalent and collapses onto `enterprise`; every other
    plan must round-trip exactly.
    """
    _alembic(legacy_db, "upgrade", "head")
    before = _tenants(legacy_db)

    r = _alembic(legacy_db, "downgrade", "0001_baseline")
    assert r.returncode == 0, f"downgrade failed:\n{r.stdout}\n{r.stderr}"

    after = _tenants(legacy_db)
    assert after["zero-co"]["plan"] == "starter"
    assert after["granted-co"]["plan"] == "professional"
    assert after["big-co"]["plan"] == "enterprise"
    assert "max_lobs" not in after["big-co"], "max_lobs should be dropped on downgrade"

    # And back up again — limits still intact after a full round trip.
    r = _alembic(legacy_db, "upgrade", "head")
    assert r.returncode == 0, f"re-upgrade failed:\n{r.stdout}\n{r.stderr}"
    again = _tenants(legacy_db)
    assert again["granted-co"]["max_mailboxes"] == before["granted-co"]["max_mailboxes"]
    assert again["big-co"]["plan"] == "max"


def test_upgrade_is_idempotent(legacy_db):
    """Running the chain twice must not double-apply anything."""
    assert _alembic(legacy_db, "upgrade", "head").returncode == 0
    first = _tenants(legacy_db)
    assert _alembic(legacy_db, "upgrade", "head").returncode == 0
    assert _tenants(legacy_db) == first
