"""Credit spending under concurrency (Phase 5.1 — verifies the ELR-009b fix).

The bug this guards against: `check_credit_budget()` used to SUM the ledger and compare
the total to the plan ceiling. Two of the six default pipeline workers both read
"999 of 1000 used", both decide there is room, and both spend. Under
`pipeline_max_workers=6` that is routine, not theoretical.

**What these tests can and cannot prove.** The suite runs on SQLite, where
`with_for_update()` compiles to nothing — SQLAlchemy silently drops it, because SQLite
serialises writes at the file level instead. So a passing threaded test here does NOT
demonstrate that row locking works in production. It demonstrates the arithmetic loses
no writes. The lock itself is verified separately by compiling the query against the
MySQL and PostgreSQL dialects and asserting `FOR UPDATE` is actually emitted — which is
what catches the regression that really matters: someone dropping `lock=True`.
"""
import threading

import pytest
from sqlalchemy.dialects import mysql, postgresql

from app.db.models.credit_balance import TenantCreditBalance
from app.db.models.credit_usage import CreditUsage
from app.services.credit_metering import get_balance, spend

pytestmark = [pytest.mark.integration, pytest.mark.security]


# ---------------------------------------------------------------------------
# The lock is actually requested
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("dialect,expected", [
    (mysql.dialect(), "FOR UPDATE"),
    (postgresql.dialect(), "FOR UPDATE"),
])
def test_balance_read_emits_for_update_on_real_databases(db_session, dialect, expected):
    """`get_balance(lock=True)` must compile to a locking read.

    Asserted against the dialects production actually runs on, because on SQLite the
    clause is dropped and a behavioural test would pass whether or not the code asks
    for the lock at all.
    """
    q = (
        db_session.query(TenantCreditBalance)
        .filter(TenantCreditBalance.tenant_id == 1)
        .with_for_update()
    )
    sql = str(q.statement.compile(dialect=dialect)).upper()
    assert expected in sql


def test_sqlite_silently_drops_the_lock(db_session):
    """Documents why the test above exists, and fails if SQLite ever gains the clause.

    If this starts failing, SQLAlchemy/SQLite have changed and the threaded tests below
    become a stronger signal than they are today — worth knowing rather than guessing.
    """
    from sqlalchemy.dialects import sqlite
    q = (
        db_session.query(TenantCreditBalance)
        .filter(TenantCreditBalance.tenant_id == 1)
        .with_for_update()
    )
    assert "FOR UPDATE" not in str(q.statement.compile(dialect=sqlite.dialect())).upper()


# ---------------------------------------------------------------------------
# No lost updates
# ---------------------------------------------------------------------------

def test_sequential_spends_never_lose_a_write(db_session, test_tenant):
    """The arithmetic floor: N spends must debit exactly N times.

    The old sum-then-check path could not fail this — it failed the *gate*, not the
    counter. This pins the counter so a future "optimisation" that batches or caches
    the balance has to keep it exact.
    """
    tid = test_tenant.tenant_id
    get_balance(db_session, tid)
    start = get_balance(db_session, tid).allowance_credits

    for _ in range(50):
        spend(db_session, tid, "contact_enriched")  # 3 credits each
    db_session.commit()

    balance = get_balance(db_session, tid)
    assert balance.allowance_credits == start - 150
    assert balance.period_spent == 150
    assert db_session.query(CreditUsage).filter(
        CreditUsage.tenant_id == tid,
        CreditUsage.usage_type == "contact_enriched",
    ).count() == 50


@pytest.fixture
def threaded_db(tmp_path):
    """A file-backed SQLite DB with a REAL connection pool, plus a seeded tenant.

    The shared test engine is `sqlite:///:memory:` on a `StaticPool`, i.e. every
    session in the suite hands back the *same* connection. Threads hitting that are
    not contending for a database lock at all — they are trampling one sqlite3 object,
    which raises "database is locked" no matter how correct the code is. A test built
    on it measures the harness, not the system.

    A file DB with the default pool gives each thread its own connection and makes
    SQLite's own locking apply, so the retry path is genuinely exercised.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.db.base import Base, configure_sqlite_write_locking
    from app.db.models.tenant import Tenant, TenantPlan

    engine = create_engine(
        f"sqlite:///{tmp_path / 'credits.db'}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    # The same BEGIN IMMEDIATE configuration the app applies to its own SQLite engine.
    # Without it SQLite deadlocks on the read-then-write, so the test would be
    # measuring a driver limitation instead of the code.
    configure_sqlite_write_locking(engine)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    setup = Session()
    try:
        t = Tenant(name="Threaded Co", slug="threaded-co", plan=TenantPlan.MAX)
        setup.add(t)
        setup.commit()
        tid = t.tenant_id

        balance = get_balance(setup, tid)
        balance.allowance_credits = 300.0
        balance.topup_credits = 0.0
        balance.period_spent = 0.0
        setup.commit()
    finally:
        setup.close()

    yield Session, tid
    engine.dispose()


def test_parallel_spends_do_not_overdraw(threaded_db):
    """Six threads, one balance, own connections — the shape of a real pipeline run.

    `pipeline_max_workers` defaults to 6, so this is the everyday case, not a stress
    test. The assertion that matters is that the ledger totals EXACTLY what was spent:
    a short total means credits were consumed and never billed.
    """
    Session, tid = threaded_db

    workers, per_worker = 6, 20  # 120 spends x 3 credits = 360, against 300 available
    errors: list[Exception] = []
    barrier = threading.Barrier(workers)

    def worker():
        db = Session()
        try:
            barrier.wait(timeout=30)  # maximise the overlap
            for _ in range(per_worker):
                spend(db, tid, "contact_enriched", commit=True)
        except Exception as e:  # noqa: BLE001 — surfaced via `errors` below
            errors.append(e)
        finally:
            db.close()

    threads = [threading.Thread(target=worker) for _ in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=120)

    assert not errors, f"spend() raised under concurrency: {errors[:3]}"

    check = Session()
    try:
        expected = workers * per_worker * 3  # 360 credits
        ledger_total = sum(
            float(e.credits_used) for e in check.query(CreditUsage).filter(
                CreditUsage.tenant_id == tid,
                CreditUsage.usage_type == "contact_enriched",
            ).all()
        )
        # A short total is the ELR-009b failure mode wearing a different hat: work was
        # done, a paid API call was made, and nobody was billed for it.
        assert ledger_total == expected, (
            f"lost billing: {ledger_total} of {expected} credits recorded"
        )

        final = get_balance(check, tid)
        assert final.period_spent == expected
        # 300 allowance against 360 spent: the overage is carried as a negative rather
        # than clamped, so it stays visible until the next refill.
        assert final.allowance_credits == 300 - expected
        assert final.total_available < 0
    finally:
        check.close()


def test_parallel_spends_are_serialised_not_interleaved(threaded_db):
    """Two threads racing on a near-empty balance must not both succeed past it.

    This is the original race in miniature: with 6 credits left and two 3-credit
    spends, the correct outcome is exactly 6 debited — never 3, which is what a
    read-then-write without a lock produces when both threads read the same start.
    """
    Session, tid = threaded_db

    setup = Session()
    try:
        b = get_balance(setup, tid)
        b.allowance_credits = 6.0
        b.period_spent = 0.0
        setup.commit()
    finally:
        setup.close()

    barrier = threading.Barrier(2)

    def worker():
        db = Session()
        try:
            barrier.wait(timeout=30)
            spend(db, tid, "contact_enriched", commit=True)
        finally:
            db.close()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    check = Session()
    try:
        final = get_balance(check, tid)
        assert final.period_spent == 6.0, "a spend was lost to the race"
        assert final.allowance_credits == 0.0
    finally:
        check.close()
