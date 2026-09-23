"""Alembic baseline migration builds the full schema (ELR-026).

Runs `alembic upgrade head` against a throwaway SQLite DB in a subprocess (so it
exercises the real env.py + baseline revision) and checks the schema + stamp.
"""
import os
import sys
import sqlite3
import subprocess
import pathlib

import pytest

pytestmark = pytest.mark.integration

_BACKEND = pathlib.Path(__file__).resolve().parents[2]  # .../backend


def test_alembic_upgrade_head_builds_schema(tmp_path):
    dbfile = tmp_path / "mig.db"
    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{dbfile}",
        "ENCRYPTION_KEY": "kbt_mh7zLmsYjFAGgX_MAVtAousWEe7CQUtbNsi9m44=",
        "SECRET_KEY": "test-secret-key-not-for-production",
    }
    r = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(_BACKEND), env=env, capture_output=True, text=True, timeout=180,
    )
    assert r.returncode == 0, f"alembic failed:\n{r.stdout}\n{r.stderr}"

    con = sqlite3.connect(str(dbfile))
    tables = {row[0] for row in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    # Spot-check core + newer (Phase 1/2) tables all exist.
    for t in ("tenants", "invoices", "subscriptions", "suppression_list",
              "visitor_events", "soft_bounce_trackers", "processed_stripe_events",
              "alembic_version"):
        assert t in tables, f"{t} missing from migrated schema"
    # Stamped at whatever the current head is — asserting a literal revision id meant
    # this test failed on every new migration, which is noise rather than signal.
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    head = ScriptDirectory.from_config(Config(str(_BACKEND / "alembic.ini"))).get_current_head()
    assert con.execute("SELECT version_num FROM alembic_version").fetchone()[0] == head

    # max_lobs landed (0002) — the Max tier's line-of-business cap needs it.
    tenant_cols = {row[1] for row in con.execute("PRAGMA table_info(tenants)")}
    assert "max_lobs" in tenant_cols
