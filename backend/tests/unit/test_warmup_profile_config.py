"""Warmup profile config_json must be a valid ramp.

Regression: the dashboard's "new profile" form defaulted to the literal
string '{{}}', so a saved profile ("demo") held invalid JSON.
"""
import json

import pytest
from pydantic import ValidationError

from app.schemas.warmup import WarmupProfileCreate, WarmupProfileUpdate

pytestmark = pytest.mark.unit

STANDARD = {
    "total_days": 30,
    "phase_1": {"days": 7, "min_emails": 2, "max_emails": 5},
    "phase_2": {"days": 7, "min_emails": 5, "max_emails": 15},
    "phase_3": {"days": 7, "min_emails": 15, "max_emails": 25},
    "phase_4": {"days": 9, "min_emails": 25, "max_emails": 35},
}


def _with(**changes):
    cfg = json.loads(json.dumps(STANDARD))
    cfg.update(changes)
    return json.dumps(cfg)


def test_standard_config_accepted():
    assert WarmupProfileCreate(name="x", config_json=json.dumps(STANDARD)).config_json


@pytest.mark.parametrize("bad,why", [
    ("{{}}", "not valid JSON"),
    ("[]", "JSON object"),
    ("{}", "total_days"),
    (_with(total_days=0), "at least 1"),
    (_with(total_days=31), "add up to 30"),
    (_with(phase_3=None), "phase_3"),
    (_with(phase_2={"days": 7, "min_emails": 9, "max_emails": 5}), "must not exceed"),
    (_with(phase_1={"days": 7, "min_emails": -1, "max_emails": 5}), "non-negative"),
    (_with(phase_1={"days": "7", "min_emails": 2, "max_emails": 5}), "non-negative integer"),
])
def test_invalid_configs_rejected(bad, why):
    with pytest.raises(ValidationError, match=why):
        WarmupProfileCreate(name="x", config_json=bad)
    with pytest.raises(ValidationError, match=why):
        WarmupProfileUpdate(config_json=bad)


def test_update_without_config_is_allowed():
    assert WarmupProfileUpdate(name="renamed").config_json is None
