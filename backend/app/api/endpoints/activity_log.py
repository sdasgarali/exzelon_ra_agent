"""Activity log endpoints — login history, auth events, active users."""
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.api.deps.database import get_db
from app.api.deps.auth import get_current_active_user, require_role, UserRole
from app.db.models.login_history import LoginHistory
from app.db.models.audit_log import AuditLog
from app.db.models.user import User
from app.services.audit_helper import write_audit_log

router = APIRouter(prefix="/activity", tags=["Activity Log"])

# Super admin dependency
super_admin_dep = require_role([UserRole.SUPER_ADMIN])


@router.get("/login-history")
async def get_login_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(super_admin_dep),
    email: Optional[str] = None,
    success: Optional[bool] = None,
    ip_address: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """List all login attempts. Super admin only."""
    query = db.query(LoginHistory)

    if email:
        query = query.filter(LoginHistory.email_attempted.ilike(f"%{email}%"))
    if success is not None:
        query = query.filter(LoginHistory.success == success)
    if ip_address:
        query = query.filter(LoginHistory.ip_address.ilike(f"%{ip_address}%"))
    if date_from:
        try:
            dt_from = datetime.fromisoformat(date_from)
            query = query.filter(LoginHistory.created_at >= dt_from)
        except ValueError:
            pass
    if date_to:
        try:
            dt_to = datetime.fromisoformat(date_to)
            query = query.filter(LoginHistory.created_at <= dt_to)
        except ValueError:
            pass

    total = query.count()
    offset = (page - 1) * page_size
    records = query.order_by(LoginHistory.created_at.desc()).offset(offset).limit(page_size).all()

    return {
        "items": [
            {
                "log_id": r.log_id,
                "tenant_id": r.tenant_id,
                "user_id": r.user_id,
                "email_attempted": r.email_attempted,
                "success": r.success,
                "failure_reason": r.failure_reason,
                "ip_address": r.ip_address,
                "user_agent": r.user_agent,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in records
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/login-history/stats")
async def get_login_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(super_admin_dep),
):
    """Get 24h login statistics. Super admin only."""
    now = datetime.utcnow()
    day_ago = now - timedelta(hours=24)
    week_ago = now - timedelta(days=7)

    base_24h = db.query(LoginHistory).filter(LoginHistory.created_at >= day_ago)

    logins_24h = base_24h.count()
    failed_24h = base_24h.filter(LoginHistory.success == False).count()
    unique_users_24h = base_24h.filter(LoginHistory.success == True).with_entities(
        func.count(func.distinct(LoginHistory.user_id))
    ).scalar() or 0

    unique_users_7d = db.query(LoginHistory).filter(
        LoginHistory.created_at >= week_ago,
        LoginHistory.success == True,
    ).with_entities(
        func.count(func.distinct(LoginHistory.user_id))
    ).scalar() or 0

    locked_accounts = db.query(User).filter(
        User.locked_until > now
    ).count()

    return {
        "logins_24h": logins_24h,
        "failed_24h": failed_24h,
        "locked_accounts": locked_accounts,
        "unique_users_24h": unique_users_24h,
        "unique_users_7d": unique_users_7d,
    }


@router.get("/auth-events")
async def get_auth_events(
    db: Session = Depends(get_db),
    current_user: User = Depends(super_admin_dep),
    entity_type: Optional[str] = None,
    action: Optional[str] = None,
    changed_by: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """List audit log entries. Super admin only."""
    query = db.query(AuditLog)

    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    if action:
        query = query.filter(AuditLog.action.ilike(f"%{action}%"))
    if changed_by:
        query = query.filter(AuditLog.changed_by.ilike(f"%{changed_by}%"))

    total = query.count()
    offset = (page - 1) * page_size
    records = query.order_by(AuditLog.created_at.desc()).offset(offset).limit(page_size).all()

    return {
        "items": [
            {
                "log_id": r.log_id,
                "tenant_id": r.tenant_id,
                "entity_type": r.entity_type,
                "entity_id": r.entity_id,
                "action": r.action,
                "changed_by": r.changed_by,
                "changed_fields": r.changed_fields,
                "notes": r.notes,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in records
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/active-users")
async def get_active_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(super_admin_dep),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """List users sorted by last login, with 30d login count. Super admin only."""
    now = datetime.utcnow()
    thirty_days_ago = now - timedelta(days=30)

    total = db.query(User).filter(User.is_active == True).count()
    offset = (page - 1) * page_size
    users = db.query(User).filter(User.is_active == True).order_by(
        User.last_login_at.desc().nullslast()
    ).offset(offset).limit(page_size).all()

    result = []
    for u in users:
        login_count_30d = db.query(LoginHistory).filter(
            LoginHistory.user_id == u.user_id,
            LoginHistory.success == True,
            LoginHistory.created_at >= thirty_days_ago,
        ).count()

        is_online = False
        if u.last_login_at:
            is_online = (now - u.last_login_at) < timedelta(minutes=15)

        result.append({
            "user_id": u.user_id,
            "email": u.email,
            "full_name": u.full_name,
            "role": u.role.value if hasattr(u.role, "value") else str(u.role),
            "tenant_id": u.tenant_id,
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
            "logins_30d": login_count_30d,
            "is_online": is_online,
            "is_locked": bool(u.locked_until and u.locked_until > now),
        })

    return {
        "items": result,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/my-login-history")
async def get_my_login_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """Get current user's own login history."""
    query = db.query(LoginHistory).filter(LoginHistory.user_id == current_user.user_id)
    total = query.count()
    offset = (page - 1) * page_size
    records = query.order_by(LoginHistory.created_at.desc()).offset(offset).limit(page_size).all()

    return {
        "items": [
            {
                "log_id": r.log_id,
                "email_attempted": r.email_attempted,
                "success": r.success,
                "failure_reason": r.failure_reason,
                "ip_address": r.ip_address,
                "user_agent": r.user_agent,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in records
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/unlock-user/{user_id}")
async def unlock_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(super_admin_dep),
):
    """Unlock a locked user account. Super admin only."""
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.failed_login_count = 0
    user.locked_until = None

    write_audit_log(db, tenant_id=0, entity_type="auth",
                    entity_id=user.user_id, action="account_unlocked",
                    changed_by=current_user.email,
                    notes=f"Unlocked user {user.email}")
    db.commit()

    return {"message": f"User {user.email} unlocked successfully", "user_id": user_id}
