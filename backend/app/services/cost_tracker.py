"""Cost tracking service — auto-records pipeline costs, budget alerts, monthly analysis.

Provider pricing registry with hardcoded defaults (overridable via settings).
"""
import json
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional
import structlog

from sqlalchemy.orm import Session
from sqlalchemy import func

logger = structlog.get_logger()


# Hardcoded default pricing — overridable via settings key "provider_pricing"
DEFAULT_PROVIDER_PRICING = {
    "jsearch":      {"model": "per_request", "cost_per_request": 0.005, "free_monthly": 500},
    "apollo":       {"model": "per_request", "cost_per_request": 0.01,  "free_monthly": 0},
    "theirstack":   {"model": "per_request", "cost_per_request": 0.005, "free_monthly": 100},
    "serpapi":       {"model": "per_request", "cost_per_request": 0.05,  "free_monthly": 100},
    "adzuna":        {"model": "per_request", "cost_per_request": 0.004, "free_monthly": 250},
    "searchapi":     {"model": "per_request", "cost_per_request": 0.04,  "free_monthly": 0},
    "usajobs":       {"model": "free",        "cost_per_request": 0,     "free_monthly": 0},
    "jooble":        {"model": "free",        "cost_per_request": 0,     "free_monthly": 0},
    "jobdatafeeds":  {"model": "monthly_flat", "cost_per_request": 0,    "monthly_base": 300},
}


def _get_pricing(db: Session = None) -> dict:
    """Get provider pricing, optionally merging overrides from settings."""
    pricing = dict(DEFAULT_PROVIDER_PRICING)
    if db:
        try:
            from app.db.models.settings import Settings
            row = db.query(Settings).filter(Settings.key == "provider_pricing").first()
            if row and row.value_json:
                overrides = json.loads(row.value_json)
                if isinstance(overrides, dict):
                    for source, config in overrides.items():
                        if source in pricing:
                            pricing[source].update(config)
                        else:
                            pricing[source] = config
        except Exception as e:
            logger.warning("Failed to load pricing overrides", error=str(e))
    return pricing


def estimate_run_cost(source: str, api_calls: int, results: int = 0, db: Session = None) -> float:
    """Estimate the cost for a pipeline run from a specific source.

    Args:
        source: Adapter name (e.g. 'jsearch', 'serpapi')
        api_calls: Number of API calls made
        results: Number of results returned (unused for per-request, used for monthly proration)
        db: Optional DB session for settings overrides

    Returns:
        Estimated cost in USD
    """
    pricing = _get_pricing(db)
    config = pricing.get(source, {})
    model = config.get("model", "per_request")

    if model == "free":
        return 0.0

    if model == "per_request":
        cost_per = config.get("cost_per_request", 0)
        free_monthly = config.get("free_monthly", 0)

        # Simple estimation: deduct free tier proportionally
        # In a full implementation, we'd track monthly usage across runs
        billable_calls = max(0, api_calls - (free_monthly // 30))  # rough daily free tier
        return round(billable_calls * cost_per, 4)

    if model == "monthly_flat":
        # Prorate monthly base cost across ~180 runs/month (6x/day * 30 days)
        monthly_base = config.get("monthly_base", 0)
        return round(monthly_base / 180, 4)

    return 0.0


def record_pipeline_cost(
    db: Session,
    source: str,
    api_calls: int,
    results: int,
    run_id: Optional[int] = None,
) -> Optional[object]:
    """Auto-record a cost entry after a pipeline adapter run.

    Args:
        db: Database session
        source: Adapter name
        api_calls: Number of API calls made
        results: Number of job results returned
        run_id: Optional job_run ID for linking

    Returns:
        Created CostEntry or None on error
    """
    try:
        from app.db.models.cost_tracking import CostEntry

        estimated_cost = estimate_run_cost(source, api_calls, results, db)

        entry = CostEntry(
            category="lead_sourcing",
            amount=estimated_cost,
            entry_date=date.today(),
            notes=f"Auto: {source} — {api_calls} API calls, {results} results" + (f", run #{run_id}" if run_id else ""),
            source_adapter=source,
            is_automated=True,
            api_calls_count=api_calls,
            results_count=results,
        )
        db.add(entry)
        db.flush()

        logger.info(
            "Recorded pipeline cost",
            source=source,
            api_calls=api_calls,
            results=results,
            estimated_cost=estimated_cost,
        )
        return entry

    except Exception as e:
        logger.error("Failed to record pipeline cost", source=source, error=str(e))
        return None


def get_costs_by_source(db: Session, days: int = 30) -> List[dict]:
    """Get cost breakdown grouped by source adapter."""
    from app.db.models.cost_tracking import CostEntry
    cutoff = (datetime.utcnow() - timedelta(days=days)).date()

    rows = db.query(
        CostEntry.source_adapter,
        func.sum(CostEntry.amount).label("total_cost"),
        func.sum(CostEntry.api_calls_count).label("total_api_calls"),
        func.sum(CostEntry.results_count).label("total_results"),
        func.count(CostEntry.cost_id).label("entry_count"),
    ).filter(
        CostEntry.entry_date >= cutoff,
        CostEntry.is_archived == False,
    ).group_by(CostEntry.source_adapter).all()

    sources = []
    for row in rows:
        total_cost = float(row.total_cost or 0)
        total_results = int(row.total_results or 0)
        cost_per_lead = total_cost / total_results if total_results > 0 else 0
        sources.append({
            "source": row.source_adapter or "manual",
            "total_cost": round(total_cost, 2),
            "total_api_calls": int(row.total_api_calls or 0),
            "total_results": total_results,
            "entry_count": row.entry_count,
            "cost_per_lead": round(cost_per_lead, 4),
        })

    sources.sort(key=lambda x: x["total_cost"], reverse=True)
    return sources


def get_daily_trend(db: Session, days: int = 30) -> List[dict]:
    """Get daily cost totals for trend chart."""
    from app.db.models.cost_tracking import CostEntry
    cutoff = (datetime.utcnow() - timedelta(days=days)).date()

    rows = db.query(
        CostEntry.entry_date,
        func.sum(CostEntry.amount).label("total"),
        func.sum(CostEntry.results_count).label("results"),
    ).filter(
        CostEntry.entry_date >= cutoff,
        CostEntry.is_archived == False,
    ).group_by(CostEntry.entry_date).order_by(CostEntry.entry_date).all()

    return [
        {
            "date": str(row.entry_date),
            "total": round(float(row.total or 0), 2),
            "results": int(row.results or 0),
        }
        for row in rows
    ]


def get_budget_status(db: Session) -> dict:
    """Current month cost utilization per source vs configured budgets."""
    from app.db.models.cost_tracking import CostEntry

    # Get first day of current month
    today = date.today()
    month_start = today.replace(day=1)

    # Get monthly costs per source
    rows = db.query(
        CostEntry.source_adapter,
        func.sum(CostEntry.amount).label("spent"),
        func.sum(CostEntry.api_calls_count).label("api_calls"),
        func.sum(CostEntry.results_count).label("results"),
    ).filter(
        CostEntry.entry_date >= month_start,
        CostEntry.is_archived == False,
    ).group_by(CostEntry.source_adapter).all()

    pricing = _get_pricing(db)

    # Read total budget from settings
    total_budget = None
    try:
        from app.db.models.settings import Settings
        row = db.query(Settings).filter(Settings.key == "cost_monthly_budget_total").first()
        if row and row.value_json:
            total_budget = float(json.loads(row.value_json))
    except Exception:
        pass

    sources = []
    total_spent = 0
    for row in rows:
        spent = float(row.spent or 0)
        total_spent += spent
        source = row.source_adapter or "manual"
        config = pricing.get(source, {})

        # Estimate monthly budget from pricing model
        if config.get("model") == "monthly_flat":
            budget = config.get("monthly_base", 0)
        elif config.get("model") == "per_request":
            # Estimate: assume 6 runs/day * 30 days * avg calls
            budget = config.get("cost_per_request", 0) * 500  # rough monthly estimate
        else:
            budget = 0

        sources.append({
            "source": source,
            "spent": round(spent, 2),
            "budget": round(budget, 2),
            "utilization_pct": round(spent / budget * 100, 1) if budget > 0 else 0,
            "api_calls": int(row.api_calls or 0),
            "results": int(row.results or 0),
        })

    sources.sort(key=lambda x: x["spent"], reverse=True)

    return {
        "month": today.strftime("%Y-%m"),
        "total_spent": round(total_spent, 2),
        "total_budget": total_budget,
        "utilization_pct": round(total_spent / total_budget * 100, 1) if total_budget and total_budget > 0 else None,
        "sources": sources,
    }


def generate_monthly_analysis(db: Session) -> dict:
    """Generate monthly cost analysis with heuristic suggestions.

    Identifies: highest cost-per-lead sources, 0-result sources (wasted spend),
    month-over-month trends. Stores result as AutomationEvent.
    """
    from app.db.models.cost_tracking import CostEntry

    today = date.today()
    month_start = today.replace(day=1)
    prev_month_start = (month_start - timedelta(days=1)).replace(day=1)

    # Current month
    current = db.query(
        CostEntry.source_adapter,
        func.sum(CostEntry.amount).label("cost"),
        func.sum(CostEntry.api_calls_count).label("calls"),
        func.sum(CostEntry.results_count).label("results"),
    ).filter(
        CostEntry.entry_date >= month_start,
        CostEntry.is_archived == False,
    ).group_by(CostEntry.source_adapter).all()

    # Previous month
    previous = db.query(
        CostEntry.source_adapter,
        func.sum(CostEntry.amount).label("cost"),
        func.sum(CostEntry.results_count).label("results"),
    ).filter(
        CostEntry.entry_date >= prev_month_start,
        CostEntry.entry_date < month_start,
        CostEntry.is_archived == False,
    ).group_by(CostEntry.source_adapter).all()

    prev_map = {r.source_adapter: {"cost": float(r.cost or 0), "results": int(r.results or 0)} for r in previous}

    suggestions = []
    source_analysis = []

    for row in current:
        source = row.source_adapter or "manual"
        cost = float(row.cost or 0)
        results = int(row.results or 0)
        calls = int(row.calls or 0)
        cpl = cost / results if results > 0 else float("inf")

        prev = prev_map.get(source, {"cost": 0, "results": 0})
        cost_change = cost - prev["cost"]

        entry = {
            "source": source,
            "cost": round(cost, 2),
            "results": results,
            "api_calls": calls,
            "cost_per_lead": round(cpl, 4) if cpl != float("inf") else None,
            "prev_month_cost": round(prev["cost"], 2),
            "cost_change": round(cost_change, 2),
        }
        source_analysis.append(entry)

        # Heuristics
        if results == 0 and cost > 0:
            suggestions.append(f"{source}: Spent ${cost:.2f} with 0 results — consider disabling or checking API key")
        elif cpl > 1.0 and results > 0:
            suggestions.append(f"{source}: High cost-per-lead ${cpl:.2f} — evaluate ROI vs alternatives")
        if cost_change > prev["cost"] * 0.5 and prev["cost"] > 0:
            suggestions.append(f"{source}: Cost increased {cost_change/prev['cost']*100:.0f}% month-over-month")

    analysis = {
        "month": today.strftime("%Y-%m"),
        "sources": source_analysis,
        "suggestions": suggestions,
        "generated_at": datetime.utcnow().isoformat(),
    }

    # Store as automation event
    try:
        from app.services.automation_logger import log_automation_event
        log_automation_event(
            db, "cost_analysis",
            f"Monthly cost analysis: {len(source_analysis)} sources, {len(suggestions)} suggestions",
            details=analysis,
        )
    except Exception as e:
        logger.warning("Failed to log cost analysis event", error=str(e))

    return analysis


def aggregate_daily_costs(db: Session) -> dict:
    """Aggregate today's automated cost entries into summary.

    Called daily by scheduler to consolidate granular per-run entries.
    """
    from app.db.models.cost_tracking import CostEntry

    today = date.today()

    rows = db.query(
        CostEntry.source_adapter,
        func.sum(CostEntry.amount).label("total"),
        func.sum(CostEntry.api_calls_count).label("calls"),
        func.sum(CostEntry.results_count).label("results"),
        func.count(CostEntry.cost_id).label("entries"),
    ).filter(
        CostEntry.entry_date == today,
        CostEntry.is_automated == True,
        CostEntry.is_archived == False,
    ).group_by(CostEntry.source_adapter).all()

    summary = {}
    total = 0.0
    for row in rows:
        source = row.source_adapter or "unknown"
        cost = float(row.total or 0)
        total += cost
        summary[source] = {
            "cost": round(cost, 2),
            "api_calls": int(row.calls or 0),
            "results": int(row.results or 0),
            "entries": row.entries,
        }

    result = {
        "date": str(today),
        "total_cost": round(total, 2),
        "sources": summary,
    }

    # Log as automation event
    try:
        from app.services.automation_logger import log_automation_event
        log_automation_event(
            db, "cost_aggregation",
            f"Daily cost aggregation: ${total:.2f} across {len(summary)} sources",
            details=result,
        )
    except Exception as e:
        logger.warning("Failed to log cost aggregation event", error=str(e))

    return result
