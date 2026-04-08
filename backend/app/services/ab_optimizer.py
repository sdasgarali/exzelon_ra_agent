"""A/B test auto-optimizer — uses chi-squared test to find winning variants.

When a variant reaches statistical significance (p < 0.05, min 100 sends each),
the losing variant(s) are disabled by setting weight to 0 (winner gets 100).
Includes open-rate and click-rate stats for deeper analytics.
"""
import json
import math
from typing import Dict, Any, List, Optional
import structlog
from sqlalchemy.orm import Session

from app.db.models.campaign import Campaign, SequenceStep, CampaignStatus
from app.db.models.outreach import OutreachEvent, OutreachStatus

logger = structlog.get_logger()

MIN_SENDS_PER_VARIANT = 100
SIGNIFICANCE_LEVEL = 0.05  # p < 0.05


def chi_squared_2x2(a_success: int, a_total: int, b_success: int, b_total: int) -> float:
    """Chi-squared test for 2x2 contingency table with Yates' correction.

    Returns approximate p-value (1 df).
    """
    if a_total == 0 or b_total == 0:
        return 1.0

    a_fail = a_total - a_success
    b_fail = b_total - b_success
    total = a_total + b_total
    total_success = a_success + b_success
    total_fail = a_fail + b_fail

    if total_success == 0 or total_fail == 0:
        return 1.0

    # Expected values
    e_a_s = a_total * total_success / total
    e_a_f = a_total * total_fail / total
    e_b_s = b_total * total_success / total
    e_b_f = b_total * total_fail / total

    # Chi-squared with Yates' correction
    chi2 = 0
    for observed, expected in [(a_success, e_a_s), (a_fail, e_a_f), (b_success, e_b_s), (b_fail, e_b_f)]:
        if expected > 0:
            correction = max(0, abs(observed - expected) - 0.5)
            chi2 += (correction ** 2) / expected

    return _chi2_p_value(chi2)


def chi_squared_kx2(stats: List[Dict]) -> float:
    """Chi-squared test for k variants (k x 2 table). Returns p-value."""
    total_sent = sum(s["sent"] for s in stats)
    total_replied = sum(s["replied"] for s in stats)

    if total_sent == 0 or total_replied == 0:
        return 1.0

    expected_rate = total_replied / total_sent
    chi2 = 0.0

    for s in stats:
        expected_success = s["sent"] * expected_rate
        expected_fail = s["sent"] * (1 - expected_rate)
        if expected_success > 0:
            chi2 += ((s["replied"] - expected_success) ** 2) / expected_success
        if expected_fail > 0:
            not_replied = s["sent"] - s["replied"]
            chi2 += ((not_replied - expected_fail) ** 2) / expected_fail

    # df = k - 1; approximate critical values
    df = len(stats) - 1
    critical_values = {1: 3.841, 2: 5.991, 3: 7.815, 4: 9.488, 5: 11.07}
    critical = critical_values.get(df, 3.841 + 2.0 * (df - 1))

    if chi2 >= critical:
        return 0.01  # below significance
    return 0.10  # above significance (approximate)


def _chi2_p_value(chi2: float) -> float:
    """Approximate p-value for chi-squared with 1 df using normal approximation."""
    if chi2 <= 0:
        return 1.0
    z = math.sqrt(chi2)
    # Rational approximation of erfc(z/sqrt(2))
    t = 1.0 / (1.0 + 0.2316419 * z / math.sqrt(2))
    d = 0.3989422804014327  # 1/sqrt(2*pi)
    poly = t * (0.319381530 + t * (-0.356563782 + t * (1.781477937 + t * (-1.821255978 + t * 1.330274429))))
    p = 2 * d * math.exp(-z * z / 2) * poly
    return max(0.0, min(1.0, p))


def get_variant_stats(step_id: int, db: Session) -> List[Dict[str, Any]]:
    """Get per-variant statistics for an A/B test step."""
    step = db.query(SequenceStep).filter(SequenceStep.step_id == step_id).first()
    if not step or not step.variants_json:
        return []

    try:
        variants = json.loads(step.variants_json)
    except (json.JSONDecodeError, TypeError):
        return []

    results = []
    for idx, variant in enumerate(variants):
        sent = db.query(OutreachEvent).filter(
            OutreachEvent.step_id == step_id,
            OutreachEvent.variant_index == idx,
            OutreachEvent.status == OutreachStatus.SENT,
        ).count()

        opened = db.query(OutreachEvent).filter(
            OutreachEvent.step_id == step_id,
            OutreachEvent.variant_index == idx,
            OutreachEvent.opened_at.isnot(None),
        ).count()

        clicked = db.query(OutreachEvent).filter(
            OutreachEvent.step_id == step_id,
            OutreachEvent.variant_index == idx,
            OutreachEvent.clicked_at.isnot(None),
        ).count()

        replied = db.query(OutreachEvent).filter(
            OutreachEvent.step_id == step_id,
            OutreachEvent.variant_index == idx,
            OutreachEvent.reply_detected_at.isnot(None),
        ).count()

        bounced = db.query(OutreachEvent).filter(
            OutreachEvent.step_id == step_id,
            OutreachEvent.variant_index == idx,
            OutreachEvent.status == OutreachStatus.BOUNCED,
        ).count()

        results.append({
            "variant_index": idx,
            "subject": variant.get("subject", ""),
            "weight": variant.get("weight", 1),
            "sent": sent,
            "opened": opened,
            "open_rate": round(opened / sent * 100, 1) if sent > 0 else 0,
            "clicked": clicked,
            "click_rate": round(clicked / sent * 100, 1) if sent > 0 else 0,
            "replied": replied,
            "reply_rate": round(replied / sent * 100, 1) if sent > 0 else 0,
            "bounced": bounced,
            "bounce_rate": round(bounced / sent * 100, 1) if sent > 0 else 0,
        })

    # Tag leader/trailing
    if results:
        best = max(results, key=lambda v: v["reply_rate"])
        for v in results:
            if v["sent"] < MIN_SENDS_PER_VARIANT:
                v["status"] = "collecting_data"
            elif v["variant_index"] == best["variant_index"]:
                v["status"] = "leader"
            elif v["weight"] == 0:
                v["status"] = "disabled"
            else:
                v["status"] = "trailing"

    return results


def auto_optimize(step_id: int, db: Session) -> Dict[str, Any]:
    """Auto-optimize variant weights based on reply rate performance.

    After MIN_SENDS_PER_VARIANT per variant, uses chi-squared test.
    If p < 0.05, winner gets 100% weight; losers get 0%.
    """
    step = db.query(SequenceStep).filter(SequenceStep.step_id == step_id).first()
    if not step or not step.variants_json:
        return {"optimized": False, "reason": "No variants"}

    try:
        variants = json.loads(step.variants_json)
    except (json.JSONDecodeError, TypeError):
        return {"optimized": False, "reason": "Invalid variants JSON"}

    if len(variants) < 2:
        return {"optimized": False, "reason": "Need at least 2 variants"}

    # Skip if already optimized (only one variant has weight > 0)
    active_variants = [v for v in variants if v.get("weight", 1) > 0]
    if len(active_variants) <= 1:
        return {"optimized": False, "reason": "Already optimized"}

    stats = get_variant_stats(step_id, db)

    # Check minimum sends
    for s in stats:
        if s["weight"] > 0 and s["sent"] < MIN_SENDS_PER_VARIANT:
            return {
                "optimized": False,
                "reason": f"Variant {s['variant_index']} has {s['sent']}/{MIN_SENDS_PER_VARIANT} sends",
                "stats": stats,
            }

    total_replied = sum(s["replied"] for s in stats)
    if total_replied == 0:
        return {"optimized": False, "reason": "No replies yet", "stats": stats}

    # Run significance test
    if len(variants) == 2:
        a, b = stats[0], stats[1]
        p_value = chi_squared_2x2(a["replied"], a["sent"], b["replied"], b["sent"])
    else:
        p_value = chi_squared_kx2(stats)

    if p_value >= SIGNIFICANCE_LEVEL:
        return {
            "optimized": False,
            "reason": f"Not significant (p={round(p_value, 4)}, need p<{SIGNIFICANCE_LEVEL})",
            "p_value": round(p_value, 4),
            "stats": stats,
        }

    # Find winner and disable losers
    winner = max(stats, key=lambda s: s["reply_rate"])
    for i, variant in enumerate(variants):
        variant["weight"] = 100 if i == winner["variant_index"] else 0

    step.variants_json = json.dumps(variants)
    db.commit()

    logger.info(
        "ab_test_auto_optimized",
        step_id=step_id,
        winner=winner["variant_index"],
        winner_reply_rate=winner["reply_rate"],
        p_value=round(p_value, 4),
    )

    return {
        "optimized": True,
        "winner_index": winner["variant_index"],
        "winner_reply_rate": winner["reply_rate"],
        "p_value": round(p_value, 4),
        "stats": stats,
    }


def auto_optimize_all_campaigns(db: Session) -> Dict[str, Any]:
    """Run auto-optimization across all active campaigns with A/B tests.

    Called by scheduler daily or on-demand.
    """
    campaigns = db.query(Campaign).filter(
        Campaign.status == CampaignStatus.ACTIVE,
    ).all()

    steps_checked = 0
    winners_found = 0

    for campaign in campaigns:
        steps = db.query(SequenceStep).filter(
            SequenceStep.campaign_id == campaign.campaign_id,
            SequenceStep.variants_json.isnot(None),
        ).all()

        for step in steps:
            result = auto_optimize(step.step_id, db)
            steps_checked += 1
            if result.get("optimized"):
                winners_found += 1

    return {"steps_checked": steps_checked, "winners_found": winners_found}
