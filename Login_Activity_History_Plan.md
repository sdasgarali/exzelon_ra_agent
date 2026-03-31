# Login & Activity History — Enterprise Implementation Plan

## Overview

Add industry-standard login history tracking, failed-attempt lockout, auth event auditing, and a super-admin Activity Log dashboard. This brings the system from ~2/10 to ~8/10 on the enterprise login/audit maturity scale.

---

## Phase 1: LoginHistory Model & Backend Recording

### 1.1 New Model: `LoginHistory` (`backend/app/db/models/login_history.py`)

```python
class LoginHistory(Base):
    __tablename__ = "login_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenants.tenant_id"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=True)  # null if user not found
    email = Column(String(255), nullable=False, index=True)
    ip_address = Column(String(45), nullable=True)       # IPv4/IPv6
    user_agent = Column(String(500), nullable=True)
    success = Column(Boolean, nullable=False, default=False)
    failure_reason = Column(String(100), nullable=True)   # wrong_password, user_not_found, inactive, unverified, locked_out
    # created_at from Base
```

**Indexes**: `(email, created_at)`, `(tenant_id, created_at)`, `(ip_address, created_at)`, `(success, created_at)`

### 1.2 Update `auth.py` Login Endpoint

Record a `LoginHistory` entry for **every** login attempt (success AND failure):

- Extract `request.client.host` for IP (check `X-Forwarded-For` header first for nginx proxy)
- Extract `User-Agent` header
- On success: `success=True`, `failure_reason=None`
- On failure: `success=False`, `failure_reason` = one of:
  - `"user_not_found"` — email doesn't exist
  - `"wrong_password"` — password mismatch
  - `"inactive"` — `is_active=False`
  - `"unverified"` — `is_verified=False`
  - `"locked_out"` — account locked (see Phase 2)

### 1.3 Register Model

- Add import in `db/models/__init__.py`
- Import in `db/base.py`
- Add auto-migration block in `main.py` lifespan

**Files modified**: `db/models/login_history.py` (NEW), `db/models/__init__.py`, `db/base.py`, `api/endpoints/auth.py`, `main.py`

---

## Phase 2: Account Lockout

### 2.1 Lockout Service (`backend/app/services/account_lockout.py`)

Simple, stateless lockout logic using the `login_history` table — no extra tables needed:

```python
LOCKOUT_THRESHOLD = 5          # failed attempts before lockout
LOCKOUT_WINDOW_MINUTES = 15    # time window to count failures
LOCKOUT_DURATION_MINUTES = 15  # how long lockout lasts

def is_account_locked(db, email) -> tuple[bool, int]:
    """Returns (is_locked, minutes_remaining)"""
    # Count consecutive failed logins in last LOCKOUT_WINDOW_MINUTES
    # If >= LOCKOUT_THRESHOLD, check if last failure was within LOCKOUT_DURATION_MINUTES

def get_failed_attempt_count(db, email) -> int:
    """Count recent failed attempts for warning display"""
```

### 2.2 Integrate into Login Flow

In `auth.py`, before password verification:
1. Check `is_account_locked(db, email)` → if locked, record login attempt with `failure_reason="locked_out"`, return 423 (Locked)
2. After failed password check, record attempt → check if this triggers lockout threshold

### 2.3 Admin Unlock Endpoint

`POST /admin/tenants/{tenant_id}/users/{user_id}/unlock` (super_admin only):
- Inserts a "synthetic success" record or deletes recent failed records to reset the lockout counter
- Better approach: Add `locked_until` column on User model (nullable DateTime), admin sets to NULL to unlock

**Revised approach**: Add `locked_until` column to `User` model:
- Lockout sets `locked_until = now + 15 minutes`
- Login checks `locked_until > now`
- Admin unlock sets `locked_until = NULL`
- Self-healing: lockout expires naturally

**Files modified**: `services/account_lockout.py` (NEW), `api/endpoints/auth.py`, `db/models/user.py`, `main.py` (migration)

---

## Phase 3: Auth Event Audit Trail

### 3.1 Extend Existing AuditLog Usage

Use the existing `AuditLog` model (no new table needed) with new `entity_type="auth"` entries:

| Action | Details |
|--------|---------|
| `login_success` | IP, user-agent, email |
| `login_failed` | IP, user-agent, email, reason |
| `account_locked` | email, attempt count, lockout duration |
| `account_unlocked` | email, unlocked_by (admin email) |
| `password_changed` | email, changed_by |
| `impersonation_start` | admin email, target tenant, target user |
| `signup` | email, tenant name |
| `email_verified` | email |

### 3.2 Helper Function

```python
# In a new util or inline in auth.py
def log_auth_event(db, action: str, email: str, tenant_id: int | None,
                   details: dict, changed_by: str = "system"):
    audit = AuditLog(
        entity_type="auth",
        entity_id=email,
        action=action,
        changed_fields=details,
        changed_by=changed_by,
        tenant_id=tenant_id
    )
    db.add(audit)
```

### 3.3 Integration Points

- `auth.py` → login (success/fail), signup, verify, impersonate
- `users.py` → password change (if exists)
- `account_lockout.py` → lockout trigger, admin unlock

**Files modified**: `api/endpoints/auth.py`, `api/endpoints/admin_tenants.py` (impersonation audit), `services/account_lockout.py`

---

## Phase 4: Login History & Activity API Endpoints

### 4.1 New Endpoint File: `api/endpoints/activity_log.py`

**Super Admin routes** (prefix: `/activity`):

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/activity/login-history` | All login attempts with filters |
| `GET` | `/activity/login-history/stats` | Login stats (total logins, failures, locked accounts, active users) |
| `GET` | `/activity/auth-events` | Auth audit trail (filtered from AuditLog where entity_type="auth") |
| `GET` | `/activity/active-users` | Users who logged in within last 24h/7d/30d |

**Query params for login-history**:
- `email` — filter by user email
- `tenant_id` — filter by tenant
- `success` — filter by success/failure (boolean)
- `ip_address` — filter by IP
- `date_from`, `date_to` — date range
- `page`, `page_size` — pagination (default 50)

**Query params for auth-events**:
- `action` — filter by action type
- `email` — filter by email
- `date_from`, `date_to` — date range
- `page`, `page_size` — pagination

**Self-service route** (any authenticated user):

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/activity/my-login-history` | Current user's own login history |

### 4.2 Register Routes

Add to `api/router.py` with prefix `/activity`, tags `["Activity Log"]`.

**Files modified**: `api/endpoints/activity_log.py` (NEW), `api/router.py`

---

## Phase 5: Frontend — Activity Log Dashboard Page

### 5.1 New Page: `frontend/src/app/dashboard/activity-log/page.tsx`

**Super admin only** page with 3 tabs:

#### Tab 1: Login History
- Table with columns: Date/Time, Email, Tenant, IP Address, User Agent (truncated), Status (success/fail badge), Failure Reason
- Filters: email search, tenant dropdown, success/fail toggle, date range picker
- Pagination (50 per page)
- Color-coded: green for success, red for failure, orange for lockout
- Stats cards at top: Total Logins (24h), Failed Attempts (24h), Locked Accounts, Unique Users (24h)

#### Tab 2: Auth Events
- Table: Date/Time, Event Type (badge), Email, Details (JSON expanded), Changed By
- Filters: event type dropdown, email search, date range
- Event type badges: login_success (green), login_failed (red), account_locked (orange), impersonation_start (purple), signup (blue)

#### Tab 3: Active Users
- Table: Email, Role, Tenant, Last Login, Login Count (30d), Status (online indicator if <15min)
- Sort by last login, login count

### 5.2 API Client

Add `activityApi` group in `frontend/src/lib/api.ts`:

```typescript
export const activityApi = {
  getLoginHistory: async (params) => { ... },
  getLoginHistoryStats: async () => { ... },
  getAuthEvents: async (params) => { ... },
  getActiveUsers: async (params) => { ... },
  getMyLoginHistory: async (params) => { ... },
  unlockUser: async (tenantId, userId) => { ... },
}
```

### 5.3 Navigation

Add to `layout.tsx` nav items:
```typescript
{ name: "Activity Log", href: "/dashboard/activity-log", icon: ScrollText, iconColor: "text-amber-500", roles: ["super_admin"] }
```

Place it near the bottom, grouped with other admin items (after Billing, before Roles).

**Files modified**: `frontend/src/app/dashboard/activity-log/page.tsx` (NEW), `frontend/src/lib/api.ts`, `frontend/src/app/dashboard/layout.tsx`

---

## Phase 6: Tests

### 6.1 Backend Unit Tests (`backend/tests/unit/test_account_lockout.py`)
- [ ] `test_account_not_locked_initially`
- [ ] `test_account_locks_after_threshold_failures`
- [ ] `test_lockout_expires_after_duration`
- [ ] `test_successful_login_resets_failure_count`
- [ ] `test_get_failed_attempt_count`

### 6.2 Backend Integration Tests (`backend/tests/integration/test_activity_log.py`)
- [ ] `test_login_creates_history_record`
- [ ] `test_failed_login_records_failure_reason`
- [ ] `test_lockout_returns_423`
- [ ] `test_admin_unlock_user`
- [ ] `test_get_login_history_super_admin_only`
- [ ] `test_get_login_history_with_filters`
- [ ] `test_get_auth_events`
- [ ] `test_get_active_users`
- [ ] `test_my_login_history_returns_own_only`
- [ ] `test_impersonation_creates_audit_event`

### 6.3 Update Existing Auth Tests
- Update `test_auth.py` to verify login history records are created

**Files modified**: `tests/unit/test_account_lockout.py` (NEW), `tests/integration/test_activity_log.py` (NEW), `tests/integration/test_auth.py` (updated)

---

## Phase 7: CLAUDE.md & Documentation Updates

- Add Activity Log to Key Data Models section
- Add `/activity` endpoints to API endpoints table
- Add `LoginHistory` to model list
- Add Activity Log page to frontend pages reference
- Update Plan_WIP.md

---

## File Summary

| Action | File | Phase |
|--------|------|-------|
| **NEW** | `backend/app/db/models/login_history.py` | 1 |
| **NEW** | `backend/app/services/account_lockout.py` | 2 |
| **NEW** | `backend/app/api/endpoints/activity_log.py` | 4 |
| **NEW** | `frontend/src/app/dashboard/activity-log/page.tsx` | 5 |
| **NEW** | `backend/tests/unit/test_account_lockout.py` | 6 |
| **NEW** | `backend/tests/integration/test_activity_log.py` | 6 |
| EDIT | `backend/app/db/models/__init__.py` | 1 |
| EDIT | `backend/app/db/base.py` | 1 |
| EDIT | `backend/app/api/endpoints/auth.py` | 1, 2, 3 |
| EDIT | `backend/app/db/models/user.py` | 2 |
| EDIT | `backend/app/main.py` | 1, 2 |
| EDIT | `backend/app/api/router.py` | 4 |
| EDIT | `backend/app/api/endpoints/admin_tenants.py` | 3 |
| EDIT | `frontend/src/lib/api.ts` | 5 |
| EDIT | `frontend/src/app/dashboard/layout.tsx` | 5 |
| EDIT | `backend/tests/integration/test_auth.py` | 6 |
| EDIT | `CLAUDE.md` | 7 |
| EDIT | `Plan_WIP.md` | 7 |

## Estimated Scope

- **6 new files**, **~10 modified files**
- Backend: ~400-500 lines new code
- Frontend: ~500-600 lines (page + API client)
- Tests: ~200-250 lines
- **Total**: ~1,100-1,350 lines

## What's Intentionally Excluded (future enhancements)

- **GeoIP lookup** — requires MaxMind DB or external API, add later
- **Full session table** — JWT-based auth means sessions aren't server-managed; would need token blacklist + refresh tokens
- **Device fingerprinting** — browser-side library needed
- **Login alert emails** — nice-to-have but not core
- **Password history** — separate feature, would need password_history table
- **CAPTCHA on lockout** — frontend integration with reCAPTCHA/hCaptcha
