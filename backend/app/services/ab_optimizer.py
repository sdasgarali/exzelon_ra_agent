"""A/B test optimizer for campaign sequence steps."""
import json
import math
from typing import Dict, Any, List
import structlog
from sqlalchemy.orm import Session

from app.db.models.campaign import SequenceStep
from app.db.models.outreach import OutreachEvent, OutreachStatus

logger = structlog.get_logger()

MIN_SENDS_FOR_SIGNIFICANCE = 100


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

        replied = db.query(OutreachEvent).filter(
            OutreachEvent.step_id == step_id,
            OutreachEvent.variant_index == idx,
            OutreachEvent.reply_detected_at.isnot(None),
        ).count()

        reply_rate = round(replied / sent * 100, 1) if sent > 0 else 0

        results.append({
            "variant_index": idx,
            "subject": variant.get("subject", ""),
            "weight": variant.get("weight", 1),
            "sent": sent,
            "replied": replied,
            "reply_rate": reply_rate,
            "status": "leader" if idx == 0 else "trailing",
        })

    # Determine leader
    if results:
        best = max(results, key=lambda v: v["reply_rate"])
        for v in results:
            if v["sent"] < MIN_SENDS_FOR_SIGNIFICANCE:
                v["status"] = "insufficient_data"
            elif v["variant_index"] == best["variant_index"]:
                v["status"] = "leader"
            else:
                v["status"] = "trailing"

    return results


def auto_optimize(step_id: int, db: Session) -> Dict[str, Any]:
    """Auto-optimize variant weights based on performance.

    After MIN_SENDS_FOR_SIGNIFICANCE sends per variant, uses chi-squared test.
    If p < 0.05, shifts 90% weight to winner.
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

    stats = get_variant_stats(step_id, db)

    # Check if all variants have enough data
    for s in stats:
        if s["sent"] < MIN_SENDS_FOR_SIGNIFICANCE:
            return {"optimized": False, "reason": f"Variant {s['variant_index']} has only {s['sent']} sends (need {MIN_SENDS_FOR_SIGNIFICANCE})"}

    # Chi-squared test for reply rates
    total_sent = sum(s["sent"] for s in stats)
    total_replied = sum(s["replied"] for s in stats)

    if total_replied == 0:
        return {"optimized": False, "reason": "No replies yet"}

    expected_rate = total_replied / total_sent
    chi_sq = 0

    for s in stats:
        expected = s["sent"] * expected_rate
        if expected > 0:
            chi_sq += ((s["replied"] - expected) ** 2) / expected
            not_replied = s["sent"] - s["replied"]
            expected_not = s["sent"] * (1 - expected_rate)
            if expected_not > 0:
                chi_sq += ((not_replied - expected_not) ** 2) / expected_not

    # Chi-squared critical value for p < 0.05, df = len(variants) - 1
    df = len(variants) - 1
    # Approximate critical values
    critical_values = {1: 3.841, 2: 5.991, 3: 7.815, 4: 9.488}
    critical = critical_values.get(df, 3.841)

    if chi_sq < critical:
        return {"optimized": False, "reason": f"Not significant (chi²={round(chi_sq, 2)}, p > 0.05)"}

    # Find winner and shift weights
    winner = max(stats, key=lambda s: s["reply_rate"])
    total_weight = 100

    for i, variant in enumerate(variants):
        if i == winner["variant_index"]:
            variant["weight"] = 90
        else:
            variant["weight"] = max(1, 10 // (len(variants) - 1))

    step.variants_json = json.dumps(variants)
    db.commit()

    logger.info("A/B test auto-optimized",
                step_id=step_id,
                winner=winner["variant_index"],
                chi_sq=round(chi_sq, 2))

    return {
        "optimized": True,
        "winner_index": winner["variant_index"],
        "winner_reply_rate": winner["reply_rate"],
        "chi_squared": round(chi_sq, 2),
    }
