"""What each metered action costs in credits.

Prices are derived from measured cost of goods — the provider rates in
`services/cost_tracker.py` and the production spend in `API_Cost_Report.docx`
($201.75 over 10,671 API calls). See `Plan_Credit_System_And_Pricing.md` §4.

Anchor: **1 credit ≈ $0.01 of retail value.** Data actions carry a 2–3x markup over
COGS; AI actions carry more, because Groq's free tier means they cost us almost
nothing today and the prices are set so the economics survive switching to a paid
model.

Sends are deliberately absent: an email costs ~$0 to send (tenants bring their own
mailboxes) and is governed by the separate monthly send quota instead. Metering it in
credits would make people afraid to run campaigns, which is the entire product.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

import structlog

logger = structlog.get_logger()

#: Settings key holding per-tenant overrides, mirroring `provider_pricing`.
SETTINGS_KEY = "credit_costs"


@dataclass(frozen=True)
class CreditCost:
    """One metered action."""

    action: str
    credits: float
    category: str  # data | validation | ai | comms — how usage is grouped in reports
    label: str
    cogs_usd: float  # documented real unit cost, for margin reporting


def _c(action, credits, category, label, cogs_usd) -> CreditCost:
    return CreditCost(action=action, credits=credits, category=category,
                      label=label, cogs_usd=cogs_usd)


CREDIT_COSTS: dict[str, CreditCost] = {
    # --- data acquisition -------------------------------------------------
    "lead_sourced": _c(
        "lead_sourced", 1, "data", "Lead sourced", 0.003),
    "contact_enriched": _c(
        "contact_enriched", 3, "data", "Contact discovered", 0.015),
    "firmographic_lookup": _c(
        "firmographic_lookup", 3, "data", "Company firmographics", 0.01),
    "intent_scan": _c(
        "intent_scan", 1, "data", "Intent signal scan", 0.005),
    "applicant_scrape": _c(
        "applicant_scrape", 3, "data", "Job applicant scrape", 0.01),

    # --- validation -------------------------------------------------------
    "email_validated": _c(
        "email_validated", 1, "validation", "Email validated", 0.006),

    # --- AI ---------------------------------------------------------------
    "ai_personalization": _c(
        "ai_personalization", 1, "ai", "AI email personalisation", 0.0004),
    "ai_reply": _c(
        "ai_reply", 2, "ai", "AI reply classified and drafted", 0.001),
    "ai_sequence": _c(
        "ai_sequence", 5, "ai", "AI sequence generated", 0.003),
    "icp_wizard": _c(
        "icp_wizard", 10, "ai", "ICP Wizard run", 0.005),

    # --- communications ---------------------------------------------------
    "sms": _c(
        "sms", 2, "comms", "SMS sent", 0.0079),
}

#: Actions that are deliberately free. Named explicitly so an accidental
#: `cost_for("email_send")` is a documented zero and not a silent KeyError-to-1.
FREE_ACTIONS = frozenset({"email_send", "warmup_email"})

#: The six credits it takes to move one contact through the whole pipeline:
#: source (1) + enrich (3) + validate (1) + personalise (1). Every plan allowance is
#: sized against this, so it is asserted in the tests rather than left as a comment.
CREDITS_PER_FULL_CONTACT = (
    CREDIT_COSTS["lead_sourced"].credits
    + CREDIT_COSTS["contact_enriched"].credits
    + CREDIT_COSTS["email_validated"].credits
    + CREDIT_COSTS["ai_personalization"].credits
)


def _overrides(db) -> dict:
    """Per-deployment overrides from the settings table, like `provider_pricing`."""
    if db is None:
        return {}
    try:
        from app.db.models.settings import Settings
        row = db.query(Settings).filter(Settings.key == SETTINGS_KEY).first()
        if row and row.value_json:
            parsed = json.loads(row.value_json)
            if isinstance(parsed, dict):
                return parsed
    except Exception as e:
        logger.warning("Failed to load credit cost overrides", error=str(e))
    return {}


def cost_for(action: str, quantity: float = 1, db=None) -> float:
    """Credits for `quantity` of `action`.

    Unknown actions cost 1 credit rather than 0 — metering something we forgot to
    price should show up in the ledger, not vanish silently. Actions in
    :data:`FREE_ACTIONS` are always 0.
    """
    if action in FREE_ACTIONS:
        return 0.0

    override = _overrides(db).get(action)
    if override is not None:
        try:
            return float(override) * quantity
        except (TypeError, ValueError):
            logger.warning("Ignoring non-numeric credit cost override", action=action)

    spec = CREDIT_COSTS.get(action)
    if spec is None:
        logger.warning("Unpriced credit action — defaulting to 1", action=action)
        return 1.0 * quantity
    return spec.credits * quantity


def category_for(action: str) -> str:
    spec = CREDIT_COSTS.get(action)
    return spec.category if spec else "other"


def label_for(action: str) -> str:
    spec = CREDIT_COSTS.get(action)
    return spec.label if spec else action.replace("_", " ").title()


def price_list(db=None) -> list[dict]:
    """The whole price list, overrides applied — for the pricing page and docs."""
    out = []
    for action, spec in CREDIT_COSTS.items():
        credits = cost_for(action, db=db)
        out.append({
            "action": action,
            "label": spec.label,
            "category": spec.category,
            "credits": credits,
            "retail_usd": round(credits * 0.01, 4),
            "cogs_usd": spec.cogs_usd,
        })
    return sorted(out, key=lambda r: (r["category"], r["action"]))
