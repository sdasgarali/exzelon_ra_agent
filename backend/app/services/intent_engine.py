"""Intent Engine — central orchestrator for intent-based lead generation.

Coordinates all intent operations:
1. Runs check_intent_signals() for configured LOBs
2. Batch recalculates LOB-aware intent scores for recent leads
3. Returns summary with signals checked, leads created, scores updated
"""
import json
import structlog
from datetime import datetime

from sqlalchemy.orm import Session

from app.db.base import SessionLocal
from app.db.models.lead import LeadDetails
from app.db.models.line_of_business import LineOfBusiness
from app.services.intent_signal_monitor import check_intent_signals
from app.services.intent_data import calculate_intent_score_v2

logger = structlog.get_logger()


def run_intent_engine(
    tenant_id: int,
    lob_id: int = None,
    schedule_type: str = "daily",
) -> dict:
    """Run the full intent engine pipeline.

    Args:
        tenant_id: Tenant scope
        lob_id: Optional specific LOB (runs all active LOBs if None)
        schedule_type: "daily" or "weekly" — controls which signal types run

    Returns:
        Summary dict: {signals_checked, leads_created, scores_updated, errors}
    """
    db = SessionLocal()
    results = {
        "signals_checked": 0,
        "leads_created": 0,
        "scores_updated": 0,
        "errors": 0,
        "schedule_type": schedule_type,
        "started_at": datetime.utcnow().isoformat(),
    }

    try:
        # Step 1: Check intent signals and create leads
        signal_results = check_intent_signals(
            tenant_id=tenant_id,
            lob_id=lob_id,
        )
        results["signals_checked"] = signal_results.get("signals_checked", 0)
        results["leads_created"] = signal_results.get("leads_created", 0)
        results["errors"] += signal_results.get("errors", 0)
        results["signal_details"] = signal_results.get("details", [])

        # Step 2: Batch update intent scores for recent leads
        scores_updated = _batch_update_intent_scores(
            db, tenant_id, lob_id=lob_id, limit=500
        )
        results["scores_updated"] = scores_updated

        db.commit()

        logger.info(
            "intent_engine_completed",
            tenant_id=tenant_id,
            lob_id=lob_id,
            signals_checked=results["signals_checked"],
            leads_created=results["leads_created"],
            scores_updated=results["scores_updated"],
        )

    except Exception as e:
        logger.error("intent_engine_failed", error=str(e), tenant_id=tenant_id)
        results["errors"] += 1
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        results["finished_at"] = datetime.utcnow().isoformat()
        db.close()

    return results


def _batch_update_intent_scores(
    db: Session,
    tenant_id: int,
    lob_id: int = None,
    limit: int = 500,
) -> int:
    """Recalculate LOB-aware intent scores for recent leads.

    Stores the result in the lead's metadata_json field under "intent" key.

    Args:
        db: Database session
        tenant_id: Tenant scope
        lob_id: Optional LOB scope
        limit: Max leads to process

    Returns:
        Count of leads with updated scores.
    """
    updated = 0

    try:
        query = db.query(LeadDetails).filter(
            LeadDetails.tenant_id == tenant_id,
            LeadDetails.is_archived == False,
        )
        if lob_id:
            query = query.filter(LeadDetails.lob_id == lob_id)

        leads = query.order_by(LeadDetails.created_at.desc()).limit(limit).all()

        # Build LOB type lookup for leads with lob_id
        lob_types = {}
        lob_ids = {lead.lob_id for lead in leads if lead.lob_id}
        if lob_ids:
            lobs = db.query(LineOfBusiness).filter(
                LineOfBusiness.lob_id.in_(lob_ids)
            ).all()
            lob_types = {lob.lob_id: lob.lob_type for lob in lobs}

        for lead in leads:
            try:
                lob_type = lob_types.get(lead.lob_id, "staffing") if lead.lob_id else "staffing"
                intent = calculate_intent_score_v2(lead, lob_type=lob_type)

                # Merge intent data into metadata_json
                existing_meta = {}
                if lead.metadata_json:
                    try:
                        existing_meta = json.loads(lead.metadata_json)
                    except (json.JSONDecodeError, TypeError):
                        existing_meta = {}

                existing_meta["intent"] = intent
                lead.metadata_json = json.dumps(existing_meta)
                updated += 1

            except Exception as e:
                logger.warning(
                    "intent_score_update_error",
                    lead_id=lead.lead_id,
                    error=str(e),
                )

    except Exception as e:
        logger.error("batch_intent_score_error", error=str(e))

    return updated
