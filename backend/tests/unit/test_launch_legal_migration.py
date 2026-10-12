"""Alembic 0006_user_terms_acceptance upgrades and downgrades cleanly on SQLite.

Runs alembic in a subprocess against a throwaway DB (same pattern as
tests/integration/test_alembic_baseline.py) so the real env.py is exercised.
"""
import os
import pathlib
import sqlite3
import subprocess
import sys

import pytest

pytestmark = pytest.mark.unit

_BACKEND = pathlib.Path(__file__).resolve().parents[2]
REV = "0006_user_terms_acceptance"


def _alembic(dbfile, *args):
    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{dbfile}",
        "ENCRYPTION_KEY": "kbt_mh7zLmsYjFAGgX_MAVtAousWEe7CQUtbNsi9m44=",
        "SECRET_KEY": "test-secret-key-not-for-production",
    }
    r = subprocess.run([sys.executable, "-m", "alembic", *args], cwd=str(_BACKEND), env=env,
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, f"alembic {' '.join(args)} failed:\n{r.stdout}\n{r.stderr}"
    return r


def _user_columns(dbfile):
    con = sqlite3.connect(str(dbfile))
    try:
        return {row[1] for row in con.execute("PRAGMA table_info(users)")}
    finally:
        con.close()


def _version(dbfile):
    con = sqlite3.connect(str(dbfile))
    try:
        return con.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    finally:
        con.close()


def test_revision_chains_from_0005():
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    script = ScriptDirectory.from_config(Config(str(_BACKEND / "alembic.ini")))
    rev = script.get_revision(REV)
    assert rev.down_revision == "0005_credit_topup_lots"


def test_upgrade_downgrade_upgrade(tmp_path):
    dbfile = tmp_path / "terms.db"
    _alembic(dbfile, "upgrade", "head")
    cols = _user_columns(dbfile)
    assert {"terms_accepted_at", "terms_version"} <= cols

    _alembic(dbfile, "downgrade", "0005_credit_topup_lots")
    assert _version(dbfile) == "0005_credit_topup_lots"
    cols = _user_columns(dbfile)
    assert "terms_accepted_at" not in cols and "terms_version" not in cols
    assert "email" in cols  # the rest of the table survives

    _alembic(dbfile, "upgrade", REV)
    assert {"terms_accepted_at", "terms_version"} <= _user_columns(dbfile)
