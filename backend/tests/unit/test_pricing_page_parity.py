"""The public pricing page must agree with PLAN_MATRIX.

This is the one place where a silent mismatch costs real money in both directions: a
limit advertised but not granted becomes a support ticket and a refund, and one granted
but not advertised is revenue left on the table. The marketing page is a `.tsx` file
nobody re-checks when a plan number changes, so it is asserted here instead of trusted.

Parsing TSX from Python is admittedly crude, but the alternative — trusting two hand-
maintained copies of the same numbers to stay in step — is how the old page ended up
advertising a $49 Starter tier that the code had never heard of.
"""
import pathlib
import re

import pytest

from app.core.plans import PLAN_MATRIX

pytestmark = pytest.mark.unit

_PRICING_TSX = (
    pathlib.Path(__file__).resolve().parents[2]  # backend/
    .parent / "frontend" / "src" / "components" / "marketing" / "PricingCards.tsx"
)

# label in the TSX  ->  attribute on PlanSpec
METER_TO_SPEC = {
    "Credits / month": "credits_per_month",
    "Emails / month": "send_quota_per_month",
    "Mailboxes": "max_mailboxes",
    "Active campaigns": "max_campaigns",
}

PRICE_RE = re.compile(
    r"key:\s*'(?P<key>free|pro|max)',.*?price:\s*(?P<price>\d+),"
    r"\s*annualPrice:\s*(?P<annual>\d+),",
    re.S,
)


@pytest.fixture(scope="module")
def tsx() -> str:
    if not _PRICING_TSX.exists():
        pytest.skip(f"pricing page not found at {_PRICING_TSX}")
    return _PRICING_TSX.read_text(encoding="utf-8")


def _row(tsx: str, label: str) -> dict:
    """Pull one `{ label: '...', free: '...', pro: '...', ... }` row out of the TSX."""
    m = re.search(
        r"\{\s*label:\s*'" + re.escape(label) + r"',\s*"
        r"free:\s*'(?P<free>[^']*)',\s*"
        r"pro:\s*'(?P<pro>[^']*)',\s*"
        r"max:\s*'(?P<max>[^']*)',\s*"
        r"custom:\s*'(?P<custom>[^']*)'",
        tsx,
    )
    assert m, f"no pricing row found for {label!r}"
    return m.groupdict()


def _as_int(value: str) -> int:
    return int(value.replace(",", "").replace("From ", "").strip())


@pytest.mark.parametrize("label,attr", sorted(METER_TO_SPEC.items()))
@pytest.mark.parametrize("plan_key", ["free", "pro", "max"])
def test_advertised_limits_match_the_plan_matrix(tsx, label, attr, plan_key):
    advertised = _as_int(_row(tsx, label)[plan_key])
    actual = getattr(PLAN_MATRIX[plan_key], attr)
    assert advertised == actual, (
        f"Pricing page advertises {label} = {advertised:,} for {plan_key}, "
        f"but PLAN_MATRIX grants {actual:,}"
    )


@pytest.mark.parametrize("label,attr", sorted(METER_TO_SPEC.items()))
def test_custom_tier_is_floored_at_max(tsx, label, attr):
    """Custom sits ABOVE Max, so it must advertise Max's figure as its floor."""
    custom = _row(tsx, label)["custom"]
    assert custom.startswith("From "), f"{label} custom value should read 'From N', got {custom!r}"
    assert _as_int(custom) == getattr(PLAN_MATRIX["max"], attr)


def test_advertised_prices_match_the_plan_matrix(tsx):
    found = {m["key"]: m for m in PRICE_RE.finditer(tsx)}
    assert set(found) == {"free", "pro", "max"}, f"missing price cards: {set(found)}"

    for key, m in found.items():
        spec = PLAN_MATRIX[key]
        assert int(m["price"]) * 100 == spec.monthly_price_cents, (
            f"{key}: page says ${m['price']}/mo, matrix says "
            f"${spec.monthly_price_cents / 100:.0f}/mo"
        )
        assert int(m["annual"]) * 100 == spec.annual_price_cents, (
            f"{key}: page says ${m['annual']}/mo annual, matrix says "
            f"${spec.annual_price_cents / 100:.0f}/mo"
        )


def test_the_retired_tier_names_are_gone(tsx):
    """A leftover 'Starter'/'Professional'/'Enterprise' card would sell a plan that
    no longer exists — the exact failure this page shipped with before the rename."""
    for dead in ("Starter", "Professional", "Enterprise"):
        assert f"name: '{dead}'" not in tsx, f"retired tier {dead!r} still on the pricing page"


def test_seats_and_lines_of_business_are_not_sold(tsx):
    """Every plan is one user and one workspace, managed by super admin (2026-09-23).
    A seat or LOB row on the pricing page would sell something customers cannot use."""
    for label in ("Team seats", "Lines of business"):
        assert f"label: '{label}'" not in tsx, f"{label!r} is advertised but not sold"


def test_annual_discount_is_the_advertised_twenty_percent(tsx):
    """The toggle says 'Save 20%'. Make the numbers actually do that."""
    assert "Save 20%" in tsx
    for key in ("pro", "max"):
        spec = PLAN_MATRIX[key]
        discount = 1 - (spec.annual_price_cents / spec.monthly_price_cents)
        assert 0.19 <= discount <= 0.21, (
            f"{key}: annual rate is {discount:.1%} off, page advertises 20%"
        )
