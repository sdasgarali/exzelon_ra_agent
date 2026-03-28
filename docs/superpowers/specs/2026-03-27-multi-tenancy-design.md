# Full Multi-Tenancy Retrofit — Design Spec

**Date**: 2026-03-27
**Status**: Approved (Approach A — Full Multi-Tenancy)
**Estimated Effort**: ~150 hours across 6 phases

---

## 1. Problem Statement

NeuraLeads is currently single-tenant: all users share all data. Anyone who signs up via "Get Started Free" immediately sees real client data (leads, contacts, mailboxes, campaigns). There is no email verification, no company scoping, and no data isolation.

**Requirements from stakeholder:**
1. Email-verified signup with mandatory Company Name field
2. Company-scoped data isolation (each company sees only its own data)
3. Starter plan with read-only access and demo/seed data
4. Upgrade prompts when users attempt locked actions
5. Protect existing data from unauthorized access

---

## 2. Architecture Overview

### Tenant Model

Every organization (company) is a **Tenant**. The existing `Tenant` model (currently unused) will be activated and enhanced.

```
Tenant (organization)
├── Users (1:many — each user belongs to exactly one tenant)
├── Leads (1:many)
├── Contacts (1:many)
├── Clients (1:many)
├── Campaigns (1:many)
├── Mailboxes (1:many)
├── Deals (1:many)
├── Templates (1:many)
├── ... (all data tables)
```

**Super Admin** is the only cross-tenant role — can see/manage all tenants.

### Data Flow

```
Signup → Create Tenant (starter plan) + User (viewer, unverified)
  → Send verification email (JWT link, 24h expiry)
  → User clicks link → is_verified = True
  → Login → JWT contains tenant_id
  → All queries filter by tenant_id from JWT
  → Starter users see seed demo data, read-only
  → Upgrade prompts on create/edit/delete actions
```

---

## 3. Database Schema Changes

### 3.1 Tenant Model (enhance existing)

```python
class TenantPlan(str, PyEnum):
    STARTER = "starter"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"

class Tenant(Base):
    __tablename__ = "tenants"

    tenant_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)              # Company name
    slug = Column(String(255), unique=True, nullable=False)  # URL-safe
    domain = Column(String(255), nullable=True)              # Optional company domain
    logo_url = Column(String(512), nullable=True)
    plan = Column(Enum(TenantPlan), default=TenantPlan.STARTER, nullable=False)
    max_users = Column(Integer, default=3)        # starter=3, pro=25, enterprise=unlimited
    max_mailboxes = Column(Integer, default=0)    # starter=0, pro=20, enterprise=unlimited
    max_contacts = Column(Integer, default=0)     # starter=0 (demo only), pro=10000, enterprise=unlimited
    max_campaigns = Column(Integer, default=0)    # starter=0, pro=50, enterprise=unlimited
    max_leads = Column(Integer, default=0)        # starter=0 (demo only), pro=50000, enterprise=unlimited
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

### 3.2 User Model Changes

```python
class User(Base):
    # Existing fields...
    tenant_id = Column(Integer, ForeignKey("tenants.tenant_id"), nullable=True)
    # nullable=True so super_admin can be global (tenant_id=NULL)
    is_verified = Column(Boolean, default=False, nullable=False)
    verification_token = Column(String(512), nullable=True)
    verification_sent_at = Column(DateTime, nullable=True)

    # Relationship
    tenant = relationship("Tenant", backref="users")

    # Constraints
    # UNIQUE(tenant_id, email) — same email can exist in different tenants
    __table_args__ = (
        UniqueConstraint('tenant_id', 'email', name='uq_tenant_email'),
    )
```

**Decision**: Email uniqueness is per-tenant. The same person could have accounts in different tenants. Global super_admin has tenant_id=NULL and retains the existing global unique email constraint via application logic.

### 3.3 Tables Getting tenant_id (ROOT — 23 tables)

All ROOT entities get a new column:
```python
tenant_id = Column(Integer, ForeignKey("tenants.tenant_id"), nullable=False, index=True)
```

| # | Table | Notes |
|---|-------|-------|
| 1 | `users` | nullable (super_admin = NULL) |
| 2 | `lead_details` | Core data |
| 3 | `contact_details` | Core data |
| 4 | `client_info` | Core data |
| 5 | `sender_mailboxes` | Per-tenant mailboxes |
| 6 | `campaigns` | Per-tenant campaigns |
| 7 | `email_templates` | Per-tenant templates |
| 8 | `deals` | Per-tenant CRM |
| 9 | `deal_stages` | Per-tenant pipeline stages |
| 10 | `webhooks` | Per-tenant webhooks |
| 11 | `api_keys` | Per-tenant API keys |
| 12 | `icp_profiles` | Per-tenant ICPs |
| 13 | `saved_searches` | Per-tenant smart lists |
| 14 | `cost_entries` | Per-tenant cost tracking |
| 15 | `crm_sync_logs` | Per-tenant CRM sync |
| 16 | `job_runs` | Per-tenant pipeline runs |
| 17 | `tracking_domains` | Per-tenant tracking domains |
| 18 | `suppression_lists` | Per-tenant suppression |
| 19 | `automation_events` | Per-tenant automation log |
| 20 | `audit_logs` | Per-tenant audit trail |
| 21 | `email_validation_results` | Per-tenant validation cache |
| 22 | `warmup_profiles` | System profiles (tenant_id=NULL) + per-tenant custom |
| 23 | `seed_test_accounts` | System-level (tenant_id=NULL) |

### 3.4 Tables Inheriting Tenancy (CHILD — 17 tables)

These inherit tenant context through foreign keys to ROOT tables. **No tenant_id column needed** (queries join through parent).

However, for **performance and safety**, we add a denormalized `tenant_id` to the 5 highest-volume child tables:

| Table | Inherits via | Add tenant_id? |
|-------|-------------|----------------|
| `lead_contact_associations` | lead_id + contact_id | YES (denormalized) |
| `outreach_events` | campaign_id + contact_id + mailbox_id | YES (denormalized, high volume) |
| `inbox_messages` | mailbox_id + contact_id | YES (denormalized, high volume) |
| `campaign_contacts` | campaign_id + contact_id | YES (denormalized) |
| `sequence_steps` | campaign_id | NO (always fetched via campaign) |
| `deal_activities` | deal_id | NO |
| `deal_tasks` | deal_id | NO |
| `warmup_emails` | sender_mailbox_id | NO |
| `warmup_daily_logs` | mailbox_id | NO |
| `warmup_alerts` | mailbox_id | NO |
| `dns_check_results` | mailbox_id | NO |
| `blacklist_check_results` | mailbox_id | NO |
| `webhook_deliveries` | webhook_id | NO |
| `visitor_events` | contact_id | NO |
| `seed_test_results` | mailbox_id | NO |
| `job_run_logs` | run_id | NO |

### 3.5 Settings Table Strategy

The `settings` table currently stores global key-value pairs. For multi-tenancy:

- **System settings** (global): `tenant_id = NULL` (e.g., system-wide feature flags)
- **Tenant settings**: `tenant_id = <id>` (e.g., role_permissions per tenant)

```python
class Settings(Base):
    __tablename__ = "settings"
    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(255), nullable=False)
    value_json = Column(Text, nullable=True)
    tenant_id = Column(Integer, ForeignKey("tenants.tenant_id"), nullable=True)
    # UNIQUE(key, tenant_id) — same key can exist per tenant + globally
    __table_args__ = (
        UniqueConstraint('key', 'tenant_id', name='uq_setting_key_tenant'),
    )
```

Resolution order: tenant-specific setting > global setting > default.

---

## 4. Authentication & Authorization Changes

### 4.1 JWT Token Payload

```python
# Current
{"sub": "user@email.com", "role": "admin", "exp": ...}

# New
{"sub": "user@email.com", "role": "admin", "tenant_id": 1, "plan": "professional", "exp": ...}
```

### 4.2 Auth Dependencies

```python
def get_current_tenant_id(current_user: User = Depends(get_current_user)) -> int:
    """Extract tenant_id from current user. Super admin can specify via header."""
    if current_user.role == UserRole.SUPER_ADMIN:
        # Super admin can optionally target a specific tenant
        # via X-Tenant-ID header (for admin panel operations)
        return None  # or header value
    if not current_user.tenant_id:
        raise HTTPException(403, "No tenant assigned")
    return current_user.tenant_id

def require_tenant(tenant_id: int = Depends(get_current_tenant_id)) -> int:
    """Require a valid tenant context (non-super_admin)."""
    if tenant_id is None:
        raise HTTPException(400, "Tenant context required")
    return tenant_id
```

### 4.3 Query Pattern

Every endpoint that queries data will use this pattern:

```python
@router.get("/leads")
async def list_leads(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    tenant_id: int = Depends(get_current_tenant_id),
):
    query = db.query(LeadDetails)
    if tenant_id is not None:  # Non-super-admin: scope to tenant
        query = query.filter(LeadDetails.tenant_id == tenant_id)
    # Super admin sees all (tenant_id is None)
    ...
```

### 4.4 Super Admin Behavior

- Super admin (`tenant_id = NULL`) sees ALL data across ALL tenants
- Can switch tenant context via `X-Tenant-ID` header for management
- Can access tenant admin panel to manage tenants, plans, users
- Existing super_admin users (ali.aitechs@gmail.com, admin@exzelon.com) remain global

---

## 5. Registration & Verification Flow

### 5.1 New Signup Endpoint

```
POST /api/v1/auth/signup
Body: {
    "email": "user@company.com",
    "password": "SecurePass123",
    "full_name": "John Doe",
    "company_name": "Acme Corp"
}
Response: {
    "message": "Verification email sent. Check your inbox.",
    "user_id": 42
}
```

Backend logic:
1. Validate email format, password strength (min 8 chars, 1 uppercase, 1 number)
2. Check if email+company already exists
3. Create Tenant (name=company_name, slug=slugified, plan=starter)
4. Create User (tenant_id=new_tenant, role=admin, is_active=True, is_verified=False)
5. Generate verification JWT (24h expiry, contains user_id)
6. Send verification email via configured SMTP/mailbox
7. Return success message

### 5.2 Email Verification Endpoint

```
GET /api/v1/auth/verify?token=<jwt_token>
Response: Redirect to /login?verified=true
```

Backend logic:
1. Decode JWT, extract user_id
2. Check token not expired (24h)
3. Set user.is_verified = True
4. Clear verification_token
5. Seed demo data for the tenant (if starter plan)
6. Redirect to login page with success message

### 5.3 Login Changes

```python
# Add verification check in login
if not user.is_verified:
    raise HTTPException(403, "Email not verified. Check your inbox.")
```

### 5.4 Resend Verification

```
POST /api/v1/auth/resend-verification
Body: {"email": "user@company.com"}
```

Rate limited: 3 per hour per email.

### 5.5 Cleanup Job

Scheduler job (daily at 3 AM UTC): Delete unverified users + their empty tenants older than 72 hours.

---

## 6. Starter Plan Experience

### 6.1 Demo Data Seeding

When a starter tenant is created and verified, `seed_demo_data(tenant_id)` creates:

| Entity | Count | Description |
|--------|-------|-------------|
| Leads | 50 | Realistic job postings across 5 industries |
| Contacts | 30 | Decision-makers with emails (demo@example.com) |
| Clients | 10 | Companies with enrichment data |
| Campaigns | 3 | Sample campaigns (draft status) |
| Templates | 5 | Email template examples |
| Deal Stages | 7 | Default pipeline (New Lead → Won/Lost) |
| Deals | 8 | Sample deals across stages |

All demo data is clearly marked with `is_demo = True` flag (new boolean column on seeded tables).

### 6.2 Frontend Starter Mode

**Detection**: Frontend checks `user.tenant.plan` from the `/auth/me` endpoint response.

**Read-only enforcement**:
- All create/edit/delete buttons show lock icon
- Clicking locked button shows upgrade modal
- Data tables are fully browsable (read-only)
- Navigation shows all pages (demonstrates product scope)

**Starter banner**: Yellow bar at top of every dashboard page:
```
"You're on the Starter plan — Upgrade to Professional to unlock all features"
[Upgrade Now]
```

**Sidebar branding**: Show tenant name (Company Name) below "NeuraLeads" logo.

### 6.3 Plan Limits Enforcement (Backend)

```python
def check_plan_limit(db: Session, tenant_id: int, resource: str) -> bool:
    """Check if tenant has exceeded plan limits."""
    tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
    if tenant.plan == TenantPlan.STARTER:
        return False  # Starter can't create anything

    limits = {
        "mailboxes": (tenant.max_mailboxes, SenderMailbox),
        "contacts": (tenant.max_contacts, ContactDetails),
        "campaigns": (tenant.max_campaigns, Campaign),
        "leads": (tenant.max_leads, LeadDetails),
        "users": (tenant.max_users, User),
    }
    max_count, model = limits.get(resource, (None, None))
    if max_count is None:
        return True
    current = db.query(model).filter(model.tenant_id == tenant_id, model.is_archived == False).count()
    return current < max_count
```

Endpoints return `HTTP 403` with `{"detail": "Plan limit reached", "upgrade_required": true, "resource": "campaigns", "current": 50, "max": 50}`.

---

## 7. Upgrade Flow

### 7.1 Upgrade Page

New dashboard page: `/dashboard/upgrade`

Displays plan comparison table:

| Feature | Starter | Professional | Enterprise |
|---------|---------|-------------|------------|
| Price | Free | $X/mo | Custom |
| Users | 3 | 25 | Unlimited |
| Mailboxes | 0 | 20 | Unlimited |
| Contacts | Demo only | 10,000 | Unlimited |
| Leads | Demo only | 50,000 | Unlimited |
| Campaigns | 0 | 50 | Unlimited |
| Email sending | No | Yes | Yes |
| Warmup engine | No | Yes | Yes |
| CRM sync | No | Yes | Yes |
| Analytics | Basic | Full | Full |
| Priority support | No | Yes | Yes |

### 7.2 Upgrade CTA

For now: "Contact us to upgrade" with email link to sales@neuraleads.com. Self-serve billing (Stripe) is a future enhancement.

### 7.3 Admin Upgrade API

Super admin can upgrade tenants:
```
PUT /api/v1/admin/tenants/{tenant_id}
Body: {"plan": "professional", "max_mailboxes": 20, ...}
```

On upgrade from starter: Optionally clear demo data (`DELETE WHERE is_demo = True AND tenant_id = X`).

---

## 8. Security Fixes (Bundled)

### 8.1 Fix Role Injection

Current register endpoint accepts `role` from request body. Fix:
```python
# REMOVE role from signup — always assign admin (first user) or viewer
user = User(
    email=data.email,
    password_hash=get_password_hash(data.password),
    full_name=data.full_name,
    role=UserRole.ADMIN,  # First user of tenant = admin
    tenant_id=new_tenant.tenant_id,
    is_verified=False,
)
```

The existing `/auth/register` endpoint will be kept for internal admin use (creating users within a tenant) but will require authentication + admin role.

### 8.2 Rate Limiting

- Signup: 5 per IP per hour
- Verification resend: 3 per email per hour
- Login: 5 per minute per IP (already exists)

### 8.3 Input Sanitization

- Company name: Strip HTML, max 255 chars, alphanumeric + spaces + common punctuation
- Slug: Auto-generated from company name, checked for uniqueness

---

## 9. Tenant Admin Panel (Super Admin Only)

New page: `/dashboard/admin/tenants`

**Table columns**: Tenant Name, Plan, Users, Leads, Contacts, Campaigns, Created, Status, Actions

**Actions**: View details, Change plan, Activate/Deactivate, Impersonate (switch context), Delete

**API Endpoints**:
```
GET    /api/v1/admin/tenants              — List all tenants
GET    /api/v1/admin/tenants/{id}         — Tenant details + stats
PUT    /api/v1/admin/tenants/{id}         — Update plan/limits
DELETE /api/v1/admin/tenants/{id}         — Soft-delete tenant
POST   /api/v1/admin/tenants/{id}/impersonate — Get token with tenant context
```

---

## 10. Data Migration

### 10.1 Existing Data

All existing data gets assigned to **Tenant #1** (the primary/original tenant):

```sql
-- 1. Create primary tenant
INSERT INTO tenants (tenant_id, name, slug, plan, is_active)
VALUES (1, 'Exzelon', 'exzelon', 'enterprise', TRUE);

-- 2. Assign all existing users to tenant #1
UPDATE users SET tenant_id = 1 WHERE tenant_id IS NULL AND role != 'super_admin';

-- 3. Backfill tenant_id on all data tables
UPDATE lead_details SET tenant_id = 1 WHERE tenant_id IS NULL;
UPDATE contact_details SET tenant_id = 1 WHERE tenant_id IS NULL;
UPDATE client_info SET tenant_id = 1 WHERE tenant_id IS NULL;
-- ... repeat for all 27 tables
```

### 10.2 Migration Strategy

1. Add `tenant_id` column as **NULLABLE** to all tables
2. Run backfill migration (set all existing data to tenant_id=1)
3. Add NOT NULL constraint after backfill
4. Add indexes on tenant_id for all tables
5. Add foreign key constraints

This is done in the `main.py` lifespan hooks (following existing pattern).

---

## 11. Implementation Phases

### Phase 1: Foundation (Security + Tenant Model + Email Verification)
- Fix role injection vulnerability
- Activate and enhance Tenant model
- Add tenant_id to User model
- Create signup endpoint with email verification
- Create verification endpoint
- Migrate existing data to Tenant #1
- Add tenant_id to JWT tokens

### Phase 2: Core Data Isolation (Lead/Contact/Client/Mailbox)
- Add tenant_id to LeadDetails, ContactDetails, ClientInfo, SenderMailbox
- Update all endpoints in leads.py, contacts.py, clients.py, mailboxes.py
- Update pipeline services (lead_sourcing, contact_enrichment, email_validation, outreach)
- Create tenant-aware auth dependency

### Phase 3: Campaign & Communication Isolation
- Add tenant_id to Campaign, OutreachEvent, InboxMessage, EmailTemplate
- Update campaigns.py, outreach.py, inbox.py, templates.py
- Update campaign_engine.py, inbox_syncer.py, auto_enrollment.py
- Update warmup services

### Phase 4: CRM & Analytics Isolation
- Add tenant_id to Deal, DealStage, Webhook, ICPProfile, SavedSearch, CostEntry
- Update deals.py, analytics.py, dashboard.py, webhooks.py, icp_wizard.py, saved_searches.py
- Update crm_sync_engine.py
- Update remaining endpoints (audit, automation, tracking_domains, etc.)

### Phase 5: Starter Plan & Demo Mode
- Implement demo data seeding
- Add is_demo flag to relevant tables
- Frontend starter mode (read-only enforcement, upgrade prompts)
- Upgrade page
- Plan limit enforcement backend

### Phase 6: Admin Panel & Polish
- Tenant admin panel (super admin only)
- Impersonation
- Cleanup scheduler (unverified users)
- Settings tenant-scoping
- Frontend signup page redesign
- Testing & deployment

---

## 12. Files Affected (Summary)

| Category | Count | Files |
|----------|-------|-------|
| DB Models | 27+ | All files in `db/models/` |
| API Endpoints | 31 | All files in `api/endpoints/` |
| Auth Dependencies | 2 | `api/deps/auth.py`, `core/security.py` |
| Services | 15+ | `services/*.py`, `services/pipelines/*.py`, `services/warmup/*.py` |
| Schemas | 10+ | `schemas/*.py` (add tenant context to responses) |
| Frontend Pages | 5+ | login, layout, upgrade (new), admin/tenants (new) |
| Frontend Components | 3+ | UpgradeModal, StarterBanner, PlanBadge |
| Config | 2 | `config.py`, `.env` |
| Main | 1 | `main.py` (migration hooks) |

**Total**: ~90 files modified, ~10 new files created

---

## 13. Non-Goals (Explicitly Out of Scope)

- Self-serve billing / Stripe integration
- Multiple tenants per user (workspace switching)
- Custom domain per tenant
- Tenant-specific branding/theming
- Data export between tenants
- Tenant API rate limiting
- Horizontal database sharding

These can be added later as the product matures.

---

## 14. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Missing a query → data leak | Critical | Systematic file-by-file audit, integration tests per endpoint |
| Migration corrupts existing data | Critical | Full backup before migration, test on local DB first |
| Super admin breaks when tenant context is NULL | High | Explicit super_admin bypass in all tenant checks |
| Performance regression from added JOINs/filters | Medium | Indexes on tenant_id, denormalized tenant_id on high-volume tables |
| Email verification fails (SMTP not configured) | Medium | Fallback: auto-verify in dev mode, require SMTP for prod |
| Existing API keys stop working | High | Backfill API keys to tenant #1, add tenant_id to key validation |

---

## 15. Acceptance Criteria

1. New user signs up with company name → receives verification email → verifies → sees demo data
2. Verified starter user can browse all pages (read-only) but cannot create/edit/delete
3. Clicking locked action shows upgrade modal
4. Existing users (Exzelon team) see all their existing data unchanged (Tenant #1)
5. New tenant's data is completely invisible to other tenants
6. Super admin can see all tenants, switch context, manage plans
7. All 248 API endpoints filter by tenant_id (verified by integration tests)
8. JWT tokens contain tenant_id and plan
