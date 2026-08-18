# Plan — Tenant-configurable Notification Sender

## SESSION_CONTEXT_RETRIEVAL
> Per-tenant configurable "system/notification email sender" (SMTP host/port/user/password/from/security),
> stored in tenant settings (password Fernet-encrypted). New `send_system_email(db, tenant_id, ...)` prefers
> the tenant's config, falls back to global `settings.SMTP_*`. Settings UI tab "Notifications" + Save + Send-test.
> Seed Exzelon tenant with Hr@exzelon.com / smtp.office365.com:587 (basic SMTP confirmed working: 235 auth + 250 send).
> Branch: feature/tenant-notification-sender.

## Decisions (confirmed with user)
- Sender for Exzelon = `Hr@exzelon.com` (basic SMTP works; support@exzelon.com is 535-blocked → skip).
- Config is per-tenant, in Settings. Reuse SMTP basic-auth (no OAuth needed for Hr@).

## Setting keys (per-tenant via settings_resolver)
- `notification_sender_email`      (From address)
- `notification_sender_name`       (From display name, optional)
- `notification_smtp_host`
- `notification_smtp_port`         (int)
- `notification_smtp_user`
- `notification_smtp_password_enc` (Fernet-encrypted; never returned)
- `notification_smtp_security`     ("starttls" | "ssl")

## Backend
- [ ] 1. `services/system_mailer.py`:
      - `_smtp_send(host,port,user,password,security,from_email,from_name,to,subject,html) -> bool`
      - `get_notification_sender(db, tenant_id) -> dict` (email,name,host,port,user,security,password_set, +_password internal)
      - `send_system_email(db, tenant_id, to, subject, html) -> bool` — tenant config → else global settings.SMTP_* → else skip. Best-effort.
- [ ] 2. Wire callers to pass tenant_id (lazy import to avoid cycles):
      - `deal_notifications._email_assignee` / `_email_reps` (have db+tid)
      - `email_verification.send_verification_email` (user.tenant_id)
      - `password_reset.*` (user.tenant_id)
- [ ] 3. `api/endpoints/settings.py` — 3 endpoints (admin, tenant-scoped):
      - `GET  /settings/notification-sender` (get_current_tenant_id) → config incl `password_set`, `effective` fallback flag
      - `PUT  /settings/notification-sender` (require_tenant_id) → save; encrypt password if provided (blank = keep)
      - `POST /settings/notification-sender/test` (require_tenant_id) → send a test email; returns {ok, detail}
      - Inline Pydantic models.
- [ ] 4. Optional: refactor global `_send_email` to reuse `_smtp_send` (DRY) — keep behavior identical.

## Frontend
- [ ] 5. `lib/api.ts`: `settingsApi.getNotificationSender / updateNotificationSender / testNotificationSender`.
- [ ] 6. `dashboard/settings/page.tsx`: new tab `notifications` (defaults to full access — unmapped in TAB_PERM_MAP), card with fields + Save + "Send test email" (recipient input, default current user email) + status (configured vs global fallback). Responsive.

## Tests
- [ ] 7. Backend: `test_notification_sender.py` — send_system_email uses tenant config (monkeypatched SMTP), falls back to global, encrypts password; endpoints GET/PUT/test (admin, tenant-scoped, password never leaked).

## Deploy + seed + verify
- [ ] 8. Merge (as sdasgarali) → deploy. Seed Exzelon tenant settings (Hr@exzelon.com / smtp.office365.com:587, encrypted pw) via PUT (impersonate) or prod one-off.
- [ ] 9. Live: POST test → confirm Hr@ delivers; trigger a deal-assignment → email arrives from Hr@exzelon.com.

## Docs/memory
- [ ] 10. services.md, api-endpoints.md, deployment.md (env), memory topic + MEMORY.md.

## Completed
- [x] Verified Hr@exzelon.com basic SMTP: auth 235 + self-send 250; support@ = 535 blocked. exzelon.com SPF+DMARC ok, DKIM selectors absent (DMARC passes via SPF alignment). (2026-08-18)
