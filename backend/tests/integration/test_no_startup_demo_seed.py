"""App startup must not seed demo data into existing tenants (user decision 2026-10-07).

Startup used to call seed_demo_data for the neuraforz/medeoan tenants on every boot, which
re-created demo rows in live workspaces after each deploy. Demo data is now only seeded for
a brand-new Starter tenant on email verification.
"""
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def test_main_startup_does_not_seed_demo_data():
    source = (Path(__file__).resolve().parents[2] / "app" / "main.py").read_text(encoding="utf-8")
    assert "seed_demo_data" not in source
