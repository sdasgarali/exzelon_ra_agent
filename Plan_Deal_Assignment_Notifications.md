# Plan — Deal-Assignment Notifications + Per-User Notification Preferences

## SESSION_CONTEXT_RETRIEVAL
> Building: (1) notify a user (in-app bell + email) when a deal is ASSIGNED to them; (2) per-user
> master toggles for in-app and email notifications, editable in the admin Users form AND a new
> self-service profile page. Toggles are GLOBAL master switches gating ALL of that user's
> in-app / email notifications. Branch: feature/deal-assignment-notifications.

## Design decisions (confirmed with user)
- Toggle location: **both** admin Users edit modal + a new self-service `/dashboard/profile` page.
- Toggle scope: **global master toggles** — `notify_inapp_enabled` gates every in-app notification,
  `notify_email_enabled` gates every notification email (deal assignment, unclaimed-queue, future).
- Default: both ON (opt-out model, preserves current behavior).

## Backend
- [ ] 1. `db/models/user.py` — add `notify_inapp_enabled`, `notify_email_enabled` (Boolean, NOT NULL, default True).
- [ ] 2. `main.py` lifespan — idempotent `ALTER TABLE users ADD COLUMN … BOOLEAN NOT NULL DEFAULT 1` for both (mirror `onboarding_dismissed_at` pattern).
- [ ] 3. `schemas/user.py` — add both to `UserBase` (default True → flows to `UserCreate` + `UserResponse`); add both `Optional[bool]=None` to `UserUpdate`.
- [ ] 4. `services/deal_notifications.py`:
      - New `notify_deal_assigned(db, deal, assignee, actor, tenant_id)` — in-app if `assignee.notify_inapp_enabled`, email if `assignee.notify_email_enabled`; best-effort. `_email_assignee(...)` helper.
      - Update `forward_new_deal_to_reps` to respect each rep's master toggles (in-app + email) — consistency with "global master toggles".
- [ ] 5. `api/endpoints/deals.py` `assign_deal` — after commit, when assigned to another user, call `notify_deal_assigned(...)` (skip self-assignment). Init `target=None` before branch.
- [ ] 6. `api/endpoints/auth.py` — new self-service `PATCH /auth/me/notification-preferences` (any active user updates only their own two toggles).

## Frontend
- [ ] 7. `lib/store.ts` — add optional `notify_inapp_enabled`, `notify_email_enabled` to `User`.
- [ ] 8. `lib/api.ts` — `authApi.updateNotificationPreferences(body)` → PATCH; `usersApi.update` already passes arbitrary payload.
- [ ] 9. `dashboard/users/page.tsx` — add both to `User` iface + `UserFormData` + `DEFAULT_FORM` + `openEditModal` + `handleSave` payload; two toggles in modal ("Notifications" group).
- [ ] 10. New `dashboard/profile/page.tsx` — self-service "Notifications" section (two toggles) + save via `authApi.updateNotificationPreferences`, refresh store via `setUser`. Responsive.
- [ ] 11. `dashboard/layout.tsx` — add "Notification settings" link in the profile dropdown → `/dashboard/profile`.

## Tests
- [ ] 12. Backend unit — `notify_deal_assigned` honors both prefs (on/off × in-app/email).
- [ ] 13. Backend integration — `POST /deals/{id}/assign` creates a NotificationEntry for the assignee; none when in-app pref off; `PATCH /auth/me/notification-preferences` persists.

## Docs / memory
- [ ] 14. Update `CLAUDE_REFERENCE/data-models.md`, `services.md`, `api-endpoints.md`.
- [ ] 15. Memory topic file + MEMORY.md pointer.

## Completed
- [x] Recon of existing notification infra (model, service, endpoints, bell UI, users form) — 2026-08-16
