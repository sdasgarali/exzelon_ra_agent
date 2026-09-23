"""Plan matrix — the single source of truth for what each subscription tier includes.

Every limit, credit allowance, send quota and feature flag for Free / Pro / Max lives
here. `plan_limits.py`, `credit_metering.py`, `tenant_service.py` and the billing layer
all read from this module rather than carrying their own copies.

Design rules (see `Plan_Credit_System_And_Pricing.md`):

* **No tier is ever "unlimited".** Every limit is a positive integer. That means the
  sentinel `0` has exactly ONE meaning — *not included in this plan* — instead of the
  old scheme where `0` meant "unlimited" on professional and "locked" on starter.
* **Two meters.** `credits_per_month` bills work with real external COGS (enrichment,
  validation, AI). `send_quota_per_month` is separate because a send's marginal cost is
  ~$0 — tenants bring their own mailboxes.
* **CUSTOM has no entry here.** A custom tenant's limits are read from its own `Tenant`
  row, floored at MAX's numbers. See :func:`limits_for_tenant`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Feature keys — used by the plan gate (Phase 3) and the pricing page.
# ---------------------------------------------------------------------------

# Available on every tier, including Free. The core loop must work or the free
# tier has no point: source leads, enrich, validate, write, send, track replies.
BASE_FEATURES = frozenset({
    "leads", "clients", "contacts", "validation", "templates", "campaigns",
    "inbox", "deals", "reports_basic", "mailboxes",
    "pipeline_lead_sourcing", "pipeline_contact_enrichment",
    "pipeline_email_validation", "pipeline_outreach",
    "ai_personalization",
})

# Added at Pro.
PRO_FEATURES = frozenset({
    "warmup", "ai_sales_agent", "ai_sequence_generator", "icp_wizard",
    "ai_reply_hitl", "ab_testing", "send_time_optimizer", "email_preview",
    "analytics", "reports_full", "webhooks", "crm_sync", "custom_roles",
    "automation",
})

# Added at Max.
MAX_FEATURES = frozenset({
    "ai_reply_autopilot", "attribution", "visitors", "intent_engine",
    "forecast", "ip_rotation", "white_label", "agency_mode", "backups",
    "dfy", "sso", "priority_support",
})


@dataclass(frozen=True)
class PlanSpec:
    """Everything one subscription tier grants."""

    key: str
    label: str
    # Pricing, in cents. `annual_price_cents` is the *per-month* rate when billed annually.
    monthly_price_cents: int
    annual_price_cents: int
    # The two meters.
    credits_per_month: int
    send_quota_per_month: int
    # Resource caps. All positive integers — never "unlimited".
    # max_users / max_lobs are 1 on EVERY tier (2026-09-23): team seats and lines of
    # business are not sold. Adding users or LOBs is a super_admin action only.
    max_users: int
    max_mailboxes: int
    max_campaigns: int  # counts ACTIVE + PAUSED only, see plan_limits.RESOURCE_COUNTERS
    max_lobs: int
    max_contacts: int
    max_leads: int
    features: frozenset = field(default_factory=frozenset)

    def has(self, feature: str) -> bool:
        return feature in self.features


# ---------------------------------------------------------------------------
# The matrix.
#
# Storage caps (`max_contacts` / `max_leads`) are deliberately set well above what
# the credit allowance can produce in a year, so credits stay the binding meter and
# storage is only a backstop:
#   Free  300 cr/mo  ->    50 contacts/mo ->    600/yr  vs  1,000 cap
#   Pro   6,000 cr/mo -> 1,000 contacts/mo -> 12,000/yr  vs 25,000 cap
#   Max  25,000 cr/mo -> 4,150 contacts/mo -> 50,000/yr  vs 150,000 cap
# ---------------------------------------------------------------------------

PLAN_MATRIX: dict[str, PlanSpec] = {
    "free": PlanSpec(
        key="free",
        label="Free",
        monthly_price_cents=0,
        annual_price_cents=0,
        credits_per_month=300,
        send_quota_per_month=500,
        max_users=1,
        max_mailboxes=1,
        max_campaigns=2,
        max_lobs=1,
        max_contacts=1_000,
        max_leads=2_000,
        features=BASE_FEATURES,
    ),
    "pro": PlanSpec(
        key="pro",
        label="Pro",
        monthly_price_cents=9_900,
        annual_price_cents=7_900,
        credits_per_month=6_000,
        send_quota_per_month=25_000,
        max_users=1,
        max_mailboxes=25,
        max_campaigns=25,
        max_lobs=1,
        max_contacts=25_000,
        max_leads=50_000,
        features=BASE_FEATURES | PRO_FEATURES,
    ),
    "max": PlanSpec(
        key="max",
        label="Max",
        monthly_price_cents=29_900,
        annual_price_cents=23_900,
        credits_per_month=25_000,
        send_quota_per_month=150_000,
        max_users=1,
        max_mailboxes=1_000,
        max_campaigns=100,
        max_lobs=1,
        max_contacts=150_000,
        max_leads=250_000,
        features=BASE_FEATURES | PRO_FEATURES | MAX_FEATURES,
    ),
}

#: Custom tenants get Max's feature set; their *numbers* come from the tenant row.
CUSTOM_FEATURES = BASE_FEATURES | PRO_FEATURES | MAX_FEATURES

#: Plan assigned to a self-service signup.
DEFAULT_PLAN = "free"

#: The resource names `limits_for_tenant()` and `plan_limits.py` understand.
LIMIT_FIELDS = (
    "max_users", "max_mailboxes", "max_campaigns",
    "max_lobs", "max_contacts", "max_leads",
)


# ---------------------------------------------------------------------------
# Legacy plan names.
#
# The tiers were starter / professional / enterprise before 2026-09. Old JWTs stay
# valid for their lifetime, old rows exist until the migration runs, and integrations
# may still POST the old strings — so every plan string entering the system is passed
# through `normalize_plan()` first. Remove one release after the migration ships.
# ---------------------------------------------------------------------------

LEGACY_PLAN_ALIASES = {
    "starter": "free",
    "professional": "pro",
    "enterprise": "max",
}


def normalize_plan(plan) -> str:
    """Coerce any plan representation to a canonical key.

    Accepts a `TenantPlan`, a canonical string, a legacy string, or None.
    Unknown values fall back to :data:`DEFAULT_PLAN` — never raises, because this
    runs on the request path where a stale JWT claim must not 500.
    """
    if plan is None:
        return DEFAULT_PLAN
    raw = getattr(plan, "value", plan)
    key = str(raw).strip().lower()
    key = LEGACY_PLAN_ALIASES.get(key, key)
    if key == "custom" or key in PLAN_MATRIX:
        return key
    return DEFAULT_PLAN


def get_plan(plan) -> PlanSpec:
    """PlanSpec for any plan representation.

    Custom resolves to MAX because Max is the *floor* for a custom contract — callers
    that need a custom tenant's real numbers use :func:`limits_for_tenant`.
    """
    key = normalize_plan(plan)
    if key == "custom":
        return PLAN_MATRIX["max"]
    return PLAN_MATRIX[key]


def is_custom(plan) -> bool:
    return normalize_plan(plan) == "custom"


def plan_features(plan) -> frozenset:
    if is_custom(plan):
        return CUSTOM_FEATURES
    return get_plan(plan).features


def credits_for_plan(plan) -> int:
    """Monthly credit allowance. Custom tenants override this on their tenant row."""
    return get_plan(plan).credits_per_month


def send_quota_for_plan(plan) -> int:
    return get_plan(plan).send_quota_per_month


def limits_for_tenant(tenant) -> dict[str, int]:
    """Effective resource limits for a tenant.

    Each `max_*` column has exactly two states, which is the whole point of the
    2026-09 sentinel change:

    * ``0`` — **not configured for this tenant**; the plan's number applies. A pricing
      change is then one edit to :data:`PLAN_MATRIX` and every customer on that tier
      picks it up with no backfill. Crucially, rows still carrying the old all-zero
      default self-heal instead of locking the tenant out — that was the bug that made
      every self-signup account unusable.
    * ``> 0`` — an explicit per-tenant limit (a support grant, a trial bump, or a
      deliberately restricted account). Used verbatim, above or below the plan.

    It never means "unlimited". No tier is unlimited; whether a tenant may touch a
    feature at all is a feature-gate question, not a limit of zero.

    **Custom** tenants are the exception: their row *is* the contract, so it is used
    directly but floored at Max's numbers — Custom exists to sit above Max, so a
    mis-set column can only ever be generous.
    """
    plan = getattr(tenant, "plan", None)

    if is_custom(plan):
        floor = PLAN_MATRIX["max"]
        return {
            f: max(int(getattr(tenant, f, 0) or 0), getattr(floor, f))
            for f in LIMIT_FIELDS
        }

    spec = get_plan(plan)
    resolved = {}
    for f in LIMIT_FIELDS:
        row = int(getattr(tenant, f, 0) or 0)
        resolved[f] = row if row > 0 else getattr(spec, f)
    return resolved


def custom_floor_violations(values: dict) -> dict[str, int]:
    """Which of `values` sit below Max's floor, mapped to the floor they must meet.

    Used by the admin tenant endpoints to reject a custom contract that would be
    *worse* than the self-serve tier above which it is supposed to sit.
    """
    floor = PLAN_MATRIX["max"]
    bad = {}
    for f in LIMIT_FIELDS:
        v = values.get(f)
        if v is not None and int(v) < getattr(floor, f):
            bad[f] = getattr(floor, f)
    return bad


#: Human labels for the plan gate's 402 body and the pricing page. Anything missing
#: falls back to a title-cased key, so a new feature is never a crash — just a
#: slightly clumsy message until someone names it.
FEATURE_LABELS = {
    "warmup": "Warmup Engine",
    "ai_sales_agent": "AI Sales Agent",
    "ai_sequence_generator": "AI Sequence Generator",
    "icp_wizard": "ICP Wizard",
    "ai_reply_hitl": "AI Reply Agent",
    "ai_reply_autopilot": "AI Reply Autopilot",
    "ab_testing": "A/B Testing",
    "send_time_optimizer": "Send-Time Optimiser",
    "email_preview": "Email Preview & Approval",
    "analytics": "Analytics",
    "reports_full": "Full Reports",
    "webhooks": "Webhooks",
    "crm_sync": "CRM Sync",
    "custom_roles": "Custom Roles & Permissions",
    "automation": "Automation Control",
    "attribution": "Attribution",
    "visitors": "Website Visitors",
    "intent_engine": "Intent Signals",
    "forecast": "Forecasting",
    "ip_rotation": "Dedicated IP Pool",
    "white_label": "White-Label Branding",
    "agency_mode": "Agency Mode",
    "backups": "Data Backups",
    "dfy": "Done-For-You Setup",
    "sso": "Single Sign-On",
    "priority_support": "Priority Support",
}

#: Tier order, cheapest first. Used to answer "what's the smallest plan with X?"
PLAN_ORDER = ("free", "pro", "max")


def feature_label(feature: str) -> str:
    return FEATURE_LABELS.get(feature, feature.replace("_", " ").title())


def minimum_plan_for(feature: str) -> Optional[str]:
    """The cheapest plan that includes `feature`, or None if no plan does.

    Derived from PLAN_MATRIX rather than hand-maintained, so the upgrade prompt can
    never drift from what the tiers actually grant.
    """
    for key in PLAN_ORDER:
        if feature in PLAN_MATRIX[key].features:
            return key
    return None


def plan_price_cents(plan, annual: bool = False) -> Optional[int]:
    """Sticker price. Custom returns None — those are quoted, not listed."""
    if is_custom(plan):
        return None
    spec = get_plan(plan)
    return spec.annual_price_cents if annual else spec.monthly_price_cents
