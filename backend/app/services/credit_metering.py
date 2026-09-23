"""Credit usage tracking and metering.

Two records, deliberately:

* :class:`TenantCreditBalance` — one row per tenant, the authoritative running total.
  Spending locks it (``SELECT ... FOR UPDATE``) so the check and the decrement happen
  in one transaction. This is the ELR-009b fix for the sum-then-check race.
* :class:`CreditUsage` — the append-only ledger of *what* each credit went on, which
  is what the usage screens and invoices read.

Gate vs meter, which are not the same thing:

* :func:`check_credit_budget` is the **gate**. It runs before expensive work, raises
  402, and is wired at endpoint entry.
* :func:`meter` / :func:`spend` are the **meter**. They run after the work, and never
  raise — failing a pipeline *after* burning a paid API call would cost money and
  lose the record of it. A shortfall drives the balance negative and logs, so overage
  is visible in the data rather than silently clamped away.
"""
import random
import time
import structlog
from datetime import date, datetime, timedelta
from typing import Optional
from fastapi import HTTPException, status
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.credit_costs import category_for, cost_for, label_for
from app.db.models.credit_balance import TenantCreditBalance
from app.db.models.credit_usage import CreditUsage
from app.db.query_helpers import tenant_filter

logger = structlog.get_logger()

#: Retries for a contended :func:`spend`. The row lock that makes spending correct is
#: also what makes contention normal — `pipeline_max_workers` defaults to 6 — so a
#: lock wait or deadlock has to be retried rather than treated as failure. Five
#: attempts with jittered backoff tops out around 150ms, which is far below any
#: pipeline's tolerance and far above a typical lock wait.
SPEND_MAX_ATTEMPTS = 5
SPEND_RETRY_BASE_SECONDS = 0.01


def _period_start(when: Optional[datetime] = None) -> date:
    """First day of the calendar month an allowance covers."""
    d = (when or datetime.utcnow()).date()
    return d.replace(day=1)


def plan_credit_limit(plan: Optional[str], tenant=None) -> int:
    """Monthly credit allowance for a plan.

    Reads `core.plans.PLAN_MATRIX` — the allowances are product pricing, not per-
    deployment config. A `CREDIT_LIMIT_*_OVERRIDE` setting can raise (never lower) a
    ceiling for one deployment; 0 means "use the matrix".

    Custom tenants carry their own allowance on the tenant row, floored at Max.
    Pass `tenant` to resolve that; without it, custom falls back to Max's number.
    """
    from app.core.config import settings
    from app.core.plans import PLAN_MATRIX, credits_for_plan, is_custom, normalize_plan

    key = normalize_plan(plan)

    if key == "custom":
        floor = PLAN_MATRIX["max"].credits_per_month
        row_value = getattr(tenant, "credits_per_month", None) if tenant is not None else None
        return max(int(row_value or 0), floor)

    override = {
        "free": settings.CREDIT_LIMIT_FREE_OVERRIDE,
        "pro": settings.CREDIT_LIMIT_PRO_OVERRIDE,
        "max": settings.CREDIT_LIMIT_MAX_OVERRIDE,
    }.get(key, 0)
    if override and int(override) > 0:
        return int(override)
    return credits_for_plan(key)


def month_usage(db: Session, tenant_id: int) -> float:
    """Total credits used by a tenant in the current calendar month."""
    month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    q = db.query(func.sum(CreditUsage.credits_used)).filter(
        CreditUsage.is_archived == False,
        CreditUsage.recorded_at >= month_start,
    )
    q = tenant_filter(q, CreditUsage, tenant_id)
    return float(q.scalar() or 0)


def enforcement_enabled(db: Session, tenant_id: Optional[int]) -> bool:
    """Whether credit enforcement is active — global config OR per-tenant opt-in.

    Defaults OFF so turning it on is always an explicit decision and never breaks
    a live pipeline silently. (ELR-009)
    """
    from app.core.config import settings
    from app.core.settings_resolver import get_tenant_setting_bool
    if settings.CREDIT_ENFORCEMENT_ENABLED:
        return True
    return get_tenant_setting_bool(db, "credit_enforcement_enabled", tenant_id=tenant_id, default=False)


# ---------------------------------------------------------------------------
# Balance: get, refill, spend. (ELR-009b)
# ---------------------------------------------------------------------------

def _load_tenant(db: Session, tenant_id: int):
    from app.db.models.tenant import Tenant
    return db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()


def get_balance(
    db: Session,
    tenant_id: int,
    *,
    lock: bool = False,
    tenant=None,
) -> TenantCreditBalance:
    """The tenant's balance row, created and refilled as needed.

    `lock=True` takes a row lock for the duration of the caller's transaction, which
    is how :func:`spend` serialises concurrent writers. It is a no-op on SQLite (which
    serialises writes at the file level anyway), so the tests exercise the logic but
    not the lock itself.
    """
    q = db.query(TenantCreditBalance).filter(TenantCreditBalance.tenant_id == tenant_id)
    if lock:
        q = q.with_for_update()
    balance = q.first()

    if balance is None:
        balance = _create_balance(db, tenant_id, tenant=tenant)
    else:
        refill_if_new_period(db, balance, tenant=tenant)
    return balance


def _create_balance(db: Session, tenant_id: int, tenant=None) -> TenantCreditBalance:
    """First balance row for a tenant.

    Seeded with the plan allowance **minus what the ledger says was already spent this
    month**, so switching a live deployment onto balance-based accounting doesn't hand
    every existing tenant a free refill mid-month.
    """
    tenant = tenant if tenant is not None else _load_tenant(db, tenant_id)
    allowance = plan_credit_limit(getattr(tenant, "plan", None), tenant=tenant)
    already_spent = month_usage(db, tenant_id)

    balance = TenantCreditBalance(
        tenant_id=tenant_id,
        period_start=_period_start(),
        allowance_credits=float(allowance) - already_spent,
        topup_credits=0.0,
        period_spent=already_spent,
        lifetime_spent=already_spent,
        last_refill_at=datetime.utcnow(),
    )
    db.add(balance)
    db.flush()
    logger.info("credit_balance_created", tenant_id=tenant_id,
                allowance=allowance, carried_over_spend=already_spent)
    return balance


def refill_if_new_period(db: Session, balance: TenantCreditBalance, tenant=None) -> bool:
    """Reset the monthly allowance when the calendar month has turned.

    Runs lazily on every access so a tenant is always correct even if the scheduler
    sweep (:func:`refill_all_balances`) missed a night. Unused allowance does **not**
    roll over — that was a deliberate v1 decision, rollover being the single largest
    source of credit-accounting bugs. Purchased top-ups are untouched; they never
    expire.
    """
    current = _period_start()
    if balance.period_start and balance.period_start >= current:
        return False

    tenant = tenant if tenant is not None else _load_tenant(db, balance.tenant_id)
    balance.allowance_credits = float(plan_credit_limit(getattr(tenant, "plan", None), tenant=tenant))
    balance.period_start = current
    balance.period_spent = 0.0
    balance.last_refill_at = datetime.utcnow()
    logger.info("credit_allowance_refilled", tenant_id=balance.tenant_id,
                allowance=balance.allowance_credits, period=str(current))
    return True


def adjust_allowance_for_plan_change(db: Session, tenant, old_allowance: int) -> float:
    """Move this month's remaining allowance onto the tenant's (already changed) plan.

    Without this, a plan change only reached the balance at the next monthly refill: a
    customer who paid for Pro on the 10th kept Free's 300 credits for three weeks.

    `allowance_credits` is "plan allowance minus what was spent from it", so shifting it
    by ``new - old`` keeps the spend and swaps the allowance underneath it:

    * **Upgrade** — the whole difference is available immediately.
    * **Downgrade** — lowered, but never below 0 and never deeper into overage than it
      already was. A downgrade must not turn credits someone already used into a debt.

    Top-ups are untouched either way; they were paid for separately. Returns the change
    applied (0 when there is nothing to do).
    """
    new_allowance = plan_credit_limit(getattr(tenant, "plan", None), tenant=tenant)
    delta = float(new_allowance) - float(old_allowance)
    if delta == 0:
        return 0.0

    balance = (
        db.query(TenantCreditBalance)
        .filter(TenantCreditBalance.tenant_id == tenant.tenant_id)
        .with_for_update()
        .first()
    )
    # No row yet: it is created lazily from the plan the tenant is on NOW, which is
    # already the new one. A stale month: the refill below uses the new plan too.
    if balance is None or refill_if_new_period(db, balance, tenant=tenant):
        return 0.0

    current = float(balance.allowance_credits or 0)
    if delta > 0:
        updated = current + delta
    else:
        updated = min(current, max(0.0, current + delta))
    balance.allowance_credits = updated
    applied = updated - current

    logger.info("credit_allowance_plan_change", tenant_id=tenant.tenant_id,
                old_allowance=old_allowance, new_allowance=new_allowance,
                remaining_before=current, remaining_after=updated)
    return applied


def available_credits(db: Session, tenant_id: Optional[int]) -> dict:
    """Remaining credits, split by source. Super admins are not metered."""
    if tenant_id is None:
        return {"allowance": None, "topup": None, "total": None, "metered": False}

    tenant = _load_tenant(db, tenant_id)
    balance = get_balance(db, tenant_id, tenant=tenant)
    return {
        "allowance": round(float(balance.allowance_credits or 0), 2),
        "topup": round(float(balance.topup_credits or 0), 2),
        "total": round(balance.total_available, 2),
        "period_start": balance.period_start.isoformat() if balance.period_start else None,
        "period_spent": round(float(balance.period_spent or 0), 2),
        "plan_allowance": plan_credit_limit(getattr(tenant, "plan", None), tenant=tenant),
        "metered": True,
    }


def _debit(balance: TenantCreditBalance, credits: float) -> float:
    """Draw `credits` off a balance. Returns the shortfall (0 when fully covered).

    Allowance first, top-ups second. Any shortfall is pushed onto `allowance_credits`
    as a negative, so an overage stays visible in the data until the next refill
    rather than being clamped to zero and forgotten.
    """
    allowance = float(balance.allowance_credits or 0)
    topup = float(balance.topup_credits or 0)

    from_allowance = max(min(allowance, credits), 0.0)
    remainder = credits - from_allowance
    from_topup = max(min(topup, remainder), 0.0)
    shortfall = remainder - from_topup

    balance.allowance_credits = allowance - from_allowance - shortfall
    balance.topup_credits = topup - from_topup
    balance.period_spent = float(balance.period_spent or 0) + credits
    balance.lifetime_spent = float(balance.lifetime_spent or 0) + credits
    balance.last_spend_at = datetime.utcnow()
    return shortfall


def spend(
    db: Session,
    tenant_id: Optional[int],
    action: str,
    quantity: float = 1,
    *,
    user_id: Optional[int] = None,
    reference_id: Optional[str] = None,
    description: Optional[str] = None,
    commit: bool = False,
) -> Optional[CreditUsage]:
    """Atomically consume credits for `action` and append a ledger entry.

    The monthly allowance is drawn down first and purchased top-ups only once it is
    exhausted, so a top-up is never wasted covering a month the allowance would have
    paid for anyway.

    Never raises. The work being metered has already happened — a paid API call has
    already been made — so throwing here would cost money *and* lose the record of it.
    A shortfall drives `allowance_credits` negative and logs, leaving the overage
    visible instead of silently clamped.
    """
    if tenant_id is None:
        return None  # super-admin / internal work is not metered

    credits = cost_for(action, quantity, db=db)
    if credits <= 0:
        return None  # free action (sends, warmup) — governed by the send quota

    last_error: Optional[Exception] = None
    for attempt in range(SPEND_MAX_ATTEMPTS):
        try:
            with db.begin_nested():  # SAVEPOINT: a failure can't poison the caller
                balance = get_balance(db, tenant_id, lock=True)
                shortfall = _debit(balance, credits)

                entry = CreditUsage(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    usage_type=action,
                    credits_used=credits,
                    description=description or label_for(action),
                    reference_id=reference_id,
                )
                db.add(entry)

                if shortfall > 0:
                    logger.warning(
                        "credit_overage", tenant_id=tenant_id, action=action,
                        credits=credits, shortfall=shortfall,
                        note="spent past the available balance; the pre-flight gate "
                             "should have blocked this run",
                    )

            if commit:
                db.commit()
            logger.debug("credit_spent", tenant_id=tenant_id, action=action,
                         credits=credits, attempt=attempt + 1)
            return entry

        except (OperationalError, DBAPIError) as e:
            # Contention, not a logic error: a row-lock wait, a deadlock victim, a
            # SQLite "database is locked". The row lock that makes spending correct is
            # exactly what produces these under a six-worker pipeline, so giving up on
            # the first one means the busier a tenant gets, the less we bill them.
            last_error = e
            if attempt + 1 < SPEND_MAX_ATTEMPTS:
                # Jittered backoff: without the jitter, workers that collided once
                # wake together and collide again.
                time.sleep(SPEND_RETRY_BASE_SECONDS * (2 ** attempt) * (0.5 + random.random()))
                continue

        except Exception as e:  # noqa: BLE001 — metering must never break a pipeline
            logger.warning("Failed to record credit spend", tenant_id=tenant_id,
                           action=action, error=str(e))
            return None

    # Out of retries. This is revenue we consumed and did not bill, so it is an ERROR
    # with the amount attached — not a debug line someone finds a quarter later.
    logger.error(
        "credit_spend_lost", tenant_id=tenant_id, action=action, credits=credits,
        attempts=SPEND_MAX_ATTEMPTS, error=str(last_error),
        note="work was performed but could not be billed after retries",
    )
    return None


def meter(
    db: Session,
    tenant_id: Optional[int],
    action: str,
    quantity: float = 1,
    **kwargs,
) -> None:
    """Fire-and-forget :func:`spend` for use inside pipelines.

    Same guarantees, no return value — the call site should read as an accounting
    aside, not something whose result changes what the pipeline does next.
    """
    spend(db, tenant_id, action, quantity, **kwargs)


def grant_topup(
    db: Session,
    tenant_id: int,
    credits: float,
    *,
    reference_id: Optional[str] = None,
    description: Optional[str] = None,
    commit: bool = True,
) -> TenantCreditBalance:
    """Add purchased credits. These never expire and survive the monthly refill."""
    balance = get_balance(db, tenant_id, lock=True)
    balance.topup_credits = float(balance.topup_credits or 0) + float(credits)
    balance.lifetime_purchased = float(balance.lifetime_purchased or 0) + float(credits)

    db.add(CreditUsage(
        tenant_id=tenant_id,
        usage_type="topup_purchase",
        credits_used=-float(credits),  # negative: a grant, not a consumption
        description=description or f"Purchased {int(credits):,} credits",
        reference_id=reference_id,
    ))
    if commit:
        db.commit()
    logger.info("credit_topup_granted", tenant_id=tenant_id, credits=credits,
                reference_id=reference_id)
    return balance


def refill_all_balances(db: Session) -> int:
    """Refill every stale balance. Driven by the monthly scheduler job.

    Lazy refill already keeps active tenants correct; this exists so dormant tenants
    and the usage screens agree with the calendar without someone having to hit an
    endpoint first.
    """
    current = _period_start()
    stale = db.query(TenantCreditBalance).filter(
        TenantCreditBalance.period_start < current
    ).all()
    refilled = 0
    for balance in stale:
        if refill_if_new_period(db, balance):
            refilled += 1
    if refilled:
        db.commit()
        logger.info("credit_balances_refilled", count=refilled, period=str(current))
    return refilled


def check_credit_budget(
    db: Session,
    tenant_id: Optional[int],
    plan: Optional[str] = None,
    credits_needed: float = 1.0,
) -> None:
    """Pre-flight budget guard for a paid action. Raises HTTP 402 when enabled and the
    tenant does not have `credits_needed` available.

    A no-op unless enforcement is enabled (see :func:`enforcement_enabled`), so it is
    safe to call at every paid choke-point without changing current behaviour.

    Reads the balance row rather than re-summing the ledger (ELR-009b). The old
    sum-then-check let six concurrent pipeline workers all read the same "under the
    ceiling" and all proceed; the balance is locked and decremented by :func:`spend`,
    so the accounting is authoritative even when this gate is racy — a gate that
    admits one extra request is harmless, a *counter* that loses writes is not.
    """
    if tenant_id is None:
        return  # super-admin / internal: not metered
    if not enforcement_enabled(db, tenant_id):
        return

    # Always load the tenant: custom plans carry their allowance on the row, and a
    # JWT `plan` claim can be stale (or a legacy starter/professional/enterprise
    # string) after an upgrade.
    tenant = _load_tenant(db, tenant_id)
    balance = get_balance(db, tenant_id, tenant=tenant)
    available = balance.total_available

    if available < credits_needed:
        ceiling = plan_credit_limit(getattr(tenant, "plan", None), tenant=tenant)
        spent = float(balance.period_spent or 0)
        logger.warning("credit_budget_exceeded", tenant_id=tenant_id,
                       available=available, needed=credits_needed, ceiling=ceiling)
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                f"Out of credits ({int(spent)}/{int(ceiling)} used this month). "
                "Upgrade your plan or buy a top-up to continue."
            ),
        )


def record_usage(
    db: Session,
    tenant_id: int,
    usage_type: str,
    credits: float = 1.0,
    description: str = None,
    user_id: int = None,
    reference_id: str = None,
) -> CreditUsage:
    """Record a credit usage entry with an explicit credit amount.

    Prefer :func:`meter`, which prices the action from `core.credit_costs` instead of
    making each call site invent a number. This stays for callers that genuinely know
    their own cost (and it debits the balance too, so the two records never diverge).

    Args:
        db: Database session.
        tenant_id: Tenant scope.
        usage_type: The action key, e.g. ``sms`` or ``ai_personalization``.
        credits: Number of credits consumed.
        description: Human-readable description.
        user_id: User who triggered the usage.
        reference_id: Related entity identifier (campaign_id, contact_id, etc).

    Returns:
        The created CreditUsage record.
    """
    entry = CreditUsage(
        tenant_id=tenant_id,
        user_id=user_id,
        usage_type=usage_type,
        credits_used=credits,
        description=description,
        reference_id=reference_id,
    )
    db.add(entry)

    # Keep the authoritative balance in step with the ledger. Best-effort: a balance
    # failure must not lose the ledger entry, which is the audit record.
    try:
        balance = get_balance(db, tenant_id, lock=True)
        _debit(balance, credits)
    except Exception as e:
        logger.warning("Failed to debit credit balance", tenant_id=tenant_id,
                       usage_type=usage_type, error=str(e))

    db.commit()
    db.refresh(entry)

    logger.info(
        "credit_usage_recorded",
        tenant_id=tenant_id,
        usage_type=usage_type,
        credits=credits,
    )
    return entry


def get_usage_summary(
    db: Session,
    tenant_id: int,
    days: int = 30,
) -> dict:
    """Get usage summary grouped by type.

    Args:
        db: Database session.
        tenant_id: Tenant scope.
        days: Number of days to look back.

    Returns:
        Dict with period, per-type breakdown, and total credits used.
    """
    cutoff = datetime.utcnow() - timedelta(days=days)
    q = db.query(
        CreditUsage.usage_type,
        func.sum(CreditUsage.credits_used).label("total"),
        func.count(CreditUsage.usage_id).label("count"),
    ).filter(
        CreditUsage.recorded_at >= cutoff,
        CreditUsage.is_archived == False,
    )
    q = tenant_filter(q, CreditUsage, tenant_id)
    rows = q.group_by(CreditUsage.usage_type).all()

    usage_list = [
        {
            "type": r.usage_type,
            "total_credits": float(r.total or 0),
            "count": r.count,
        }
        for r in rows
    ]

    return {
        "period_days": days,
        "usage": usage_list,
        "total_credits_used": sum(item["total_credits"] for item in usage_list),
    }


def get_usage_history(
    db: Session,
    tenant_id: int,
    usage_type: str = None,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """Get paginated credit usage history.

    Args:
        db: Database session.
        tenant_id: Tenant scope.
        usage_type: Optional filter by usage type.
        page: Page number (1-indexed).
        page_size: Items per page.

    Returns:
        Dict with items, total, page, page_size, and pages.
    """
    q = db.query(CreditUsage).filter(CreditUsage.is_archived == False)
    q = tenant_filter(q, CreditUsage, tenant_id)

    if usage_type:
        q = q.filter(CreditUsage.usage_type == usage_type)

    total = q.count()
    items = q.order_by(CreditUsage.recorded_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()

    return {
        "items": [
            {
                "usage_id": item.usage_id,
                "usage_type": item.usage_type,
                "credits_used": float(item.credits_used),
                "description": item.description,
                "reference_id": item.reference_id,
                "recorded_at": item.recorded_at.isoformat() if item.recorded_at else None,
            }
            for item in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
    }
