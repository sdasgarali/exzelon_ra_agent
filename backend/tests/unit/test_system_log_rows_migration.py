"""Alembic 0007_system_log_rows: nullable tenant_id on automation_events / cost_entries.

Runs alembic in a subprocess against a throwaway SQLite DB (same pattern as
test_launch_legal_migration.py) so the real env.py is exercised.
"""
import os
import pathlib
import sqlite3
import subprocess
import sys

import pytest

pytestmark = pytest.mark.unit

_BACKEND = pathlib.Path(__file__).resolve().parents[2]
REV = "0007_system_log_rows"
PREV = "0006_user_terms_acceptance"
TABLES = ("automation_events", "cost_entries")


def _alembic(dbfile, *args, expect_ok=True):
    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{dbfile}",
        "ENCRYPTION_KEY": "kbt_mh7zLmsYjFAGgX_MAVtAousWEe7CQUtbNsi9m44=",
        "SECRET_KEY": "test-secret-key-not-for-production",
    }
    r = subprocess.run([sys.executable, "-m", "alembic", *args], cwd=str(_BACKEND), env=env,
                       capture_output=True, text=True, timeout=300)
    if expect_ok:
        assert r.returncode == 0, f"alembic {' '.join(args)} failed:\n{r.stdout}\n{r.stderr}"
    return r


def _tenant_nullable(dbfile, table):
    con = sqlite3.connect(str(dbfile))
    try:
        for _cid, name, _type, notnull, _dflt, _pk in con.execute(f"PRAGMA table_info({table})"):
            if name == "tenant_id":
                return notnull == 0
    finally:
        con.close()
    raise AssertionError(f"{table}.tenant_id not found")


def _version(dbfile):
    con = sqlite3.connect(str(dbfile))
    try:
        return con.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    finally:
        con.close()


def test_revision_chains_from_0006():
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    script = ScriptDirectory.from_config(Config(str(_BACKEND / "alembic.ini")))
    assert script.get_revision(REV).down_revision == PREV


def test_downgrade_then_upgrade_toggles_nullability(tmp_path):
    dbfile = tmp_path / "logs.db"
    _alembic(dbfile, "upgrade", "head")
    for t in TABLES:
        assert _tenant_nullable(dbfile, t), t

    _alembic(dbfile, "downgrade", PREV)  # no NULL rows yet, so this is allowed
    assert _version(dbfile) == PREV
    for t in TABLES:
        assert not _tenant_nullable(dbfile, t), t

    _alembic(dbfile, "upgrade", REV)  # the real ALTER path: NOT NULL -> NULL
    for t in TABLES:
        assert _tenant_nullable(dbfile, t), t


def test_downgrade_refuses_while_system_rows_exist(tmp_path):
    dbfile = tmp_path / "logs-null.db"
    _alembic(dbfile, "upgrade", "head")
    con = sqlite3.connect(str(dbfile))
    try:
        # A system row: tenant_id NULL, every other required column filled neutrally.
        values = {"tenant_id": None}
        for _cid, name, type_, notnull, dflt, pk in con.execute("PRAGMA table_info(automation_events)"):
            if name in values or pk or not notnull or dflt is not None:
                continue
            t = (type_ or "").upper()
            values[name] = ("2026-11-06 00:00:00" if "DATE" in t or "TIME" in t
                            else 0 if any(k in t for k in ("INT", "BOOL", "NUM", "REAL"))
                            else "system")
        cols = ", ".join(values)
        marks = ", ".join("?" for _ in values)
        con.execute(f"INSERT INTO automation_events ({cols}) VALUES ({marks})", list(values.values()))
        con.commit()
    finally:
        con.close()

    r = _alembic(dbfile, "downgrade", PREV, expect_ok=False)
    assert r.returncode != 0
    assert "system rows" in (r.stdout + r.stderr)
    assert _version(dbfile) == REV
