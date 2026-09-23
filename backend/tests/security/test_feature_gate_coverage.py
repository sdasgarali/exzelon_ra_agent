"""Audit of the plan gate across every mounted route (Phase 5.2).

`tests/integration/test_feature_gate_routes.py` checks a hand-picked sample end to end.
This walks the whole application instead, so the failures it catches are the ones a
sample never would:

* a `require_feature("warmupp")` typo — no plan grants it, so it locks out *every*
  tier including Max, and the 402 reads like a deliberate product decision;
* a new Pro/Max-only router mounted without a gate, silently shipping a paid feature
  to the free tier;
* a gate wired to a feature no plan includes, which is the same dead end as a typo.

The gate is discovered via the `__feature__` tag that `require_feature` sets, so this
stays accurate as routers move around — there is no list here to forget to update.
"""
import pytest

from app.core.plans import (
    BASE_FEATURES, MAX_FEATURES, PLAN_MATRIX, PRO_FEATURES, minimum_plan_for,
)
from app.main import app

pytestmark = [pytest.mark.integration, pytest.mark.security]

ALL_FEATURES = BASE_FEATURES | PRO_FEATURES | MAX_FEATURES


def _gated_features_for(route) -> set:
    """Every feature key guarding `route`, router-level and per-endpoint alike."""
    found = set()
    dependant = getattr(route, "dependant", None)
    if dependant is None:
        return found

    stack = [dependant]
    seen = set()
    while stack:
        dep = stack.pop()
        if id(dep) in seen:
            continue
        seen.add(id(dep))
        feature = getattr(getattr(dep, "call", None), "__feature__", None)
        if feature:
            found.add(feature)
        stack.extend(getattr(dep, "dependencies", []) or [])
    return found


@pytest.fixture(scope="module")
def gate_map() -> dict:
    """path -> set of features gating it, for every route that has one."""
    out = {}
    for route in app.routes:
        features = _gated_features_for(route)
        if features:
            out[getattr(route, "path", "?")] = features
    return out


def test_the_gate_is_actually_mounted_somewhere(gate_map):
    """A smoke check: if this is empty the audit below passes vacuously."""
    assert len(gate_map) > 20, f"only {len(gate_map)} gated routes found — is the gate wired?"


def test_every_gate_names_a_feature_some_plan_grants(gate_map):
    """The typo check.

    `require_feature("warmupp")` raises 402 for everyone forever, Max included, and
    nothing else in the system would ever notice.
    """
    unknown = {
        path: sorted(f for f in features if f not in ALL_FEATURES)
        for path, features in gate_map.items()
    }
    unknown = {p: f for p, f in unknown.items() if f}
    assert not unknown, (
        f"gates reference features no plan grants (typo?): {unknown}"
    )


def test_every_gate_resolves_to_an_upgrade_path(gate_map):
    """Each gate must be able to tell the customer which plan unlocks it.

    `minimum_plan_for()` returning None means the 402 falls back to "not available on
    your plan" with no upsell — a dead end for both the customer and revenue.
    """
    dead_ends = {
        path: sorted(f for f in features if minimum_plan_for(f) is None)
        for path, features in gate_map.items()
    }
    dead_ends = {p: f for p, f in dead_ends.items() if f}
    assert not dead_ends, f"gated routes with no upgrade path: {dead_ends}"


def test_base_features_are_never_used_as_a_gate(gate_map):
    """Gating on something every plan includes is a no-op that reads as protection.

    Someone adding `require_feature("leads")` would believe the route is restricted
    when it is wide open — worse than no gate, because it stops anyone looking again.
    """
    pointless = {
        path: sorted(f for f in features if f in BASE_FEATURES)
        for path, features in gate_map.items()
    }
    pointless = {p: f for p, f in pointless.items() if f}
    assert not pointless, (
        f"routes gated on a feature every plan already has: {pointless}"
    )


@pytest.mark.parametrize("prefix,feature", [
    ("/api/v1/warmup", "warmup"),
    ("/api/v1/webhooks", "webhooks"),
    ("/api/v1/automation", "automation"),
    ("/api/v1/crm-sync", "crm_sync"),
    ("/api/v1/roles", "custom_roles"),
    ("/api/v1/analytics", "analytics"),
    ("/api/v1/email-preview", "email_preview"),
    ("/api/v1/icp", "icp_wizard"),
    ("/api/v1/backups", "backups"),
    ("/api/v1/dfy", "dfy"),
])
def test_paid_areas_are_gated_on_every_route(gate_map, prefix, feature):
    """A paid area must be gated on ALL of its routes, not just the ones tested.

    Router-level mounting gives this for free; the test exists so that moving a route
    out to its own router, or adding one that bypasses the mount, fails loudly instead
    of quietly shipping a paid feature to Free.
    """
    routes = [p for p in gate_map if p.startswith(prefix)]
    assert routes, f"no gated routes found under {prefix} — did the gate get dropped?"

    ungated = [p for p in routes if feature not in gate_map[p]]
    assert not ungated, f"{prefix} routes missing the '{feature}' gate: {ungated}"


def test_the_public_tracking_pixel_is_never_gated():
    """The beacon and the pixel script must stay reachable without a plan.

    They are loaded by anonymous browsers on the CUSTOMER's website. A 402 there is a
    console error on their site that looks like our bug — so this is asserted
    explicitly rather than left to whoever next edits that router.
    """
    for route in app.routes:
        path = getattr(route, "path", "")
        if path in ("/api/v1/visitors/track", "/api/v1/visitors/pixel.js"):
            assert not _gated_features_for(route), (
                f"{path} is plan-gated; it must stay public"
            )


def test_pro_and_max_features_are_each_reachable_somewhere():
    """Every paid feature should gate something, or we are selling a phantom.

    Features with no route of their own are listed explicitly: they gate behaviour
    inside a service rather than an endpoint, so their absence here is expected and
    intentional rather than an oversight.
    """
    gated = set()
    for route in app.routes:
        gated |= _gated_features_for(route)

    # Enforced below the API surface, so they legitimately gate no route.
    NOT_ROUTE_GATED = {
        "ai_sales_agent",        # send-path decision inside campaign_engine
        "ai_reply_hitl",         # reply-agent mode, chosen in the service
        "ai_reply_autopilot",    # ditto
        "ab_testing",            # campaign engine variant assignment
        "send_time_optimizer",   # send scheduling
        "reports_full",          # report depth, not a separate route
        "ip_rotation",           # mailbox selection
        "white_label",           # tenant branding
        "agency_mode",           # tenant flag
        "sso",                   # ELR-020, not built yet
        "priority_support",      # commercial, not technical
        "attribution",           # gated inside integrations.py, not its own router
        "visitors",              # per-route inside visitor_tracking.py
        "intent_engine",         # per-route inside leads.py / lob.py
        "forecast",              # per-route inside analytics.py
        "ai_sequence_generator", # gated via the sequence_generator router
    }
    expected = (PRO_FEATURES | MAX_FEATURES) - NOT_ROUTE_GATED
    missing = sorted(expected - gated)
    assert not missing, (
        f"paid features that gate nothing — sold but not enforced: {missing}"
    )


def test_free_plan_really_is_missing_the_paid_features():
    """Guards the matrix itself: Free must not quietly acquire a paid feature."""
    free = PLAN_MATRIX["free"].features
    leaked = sorted((PRO_FEATURES | MAX_FEATURES) & free)
    assert not leaked, f"Free plan includes paid features: {leaked}"
