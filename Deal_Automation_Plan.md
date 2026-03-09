# Deal Pipeline Automation Plan

## Overview
Transform the deals module from 100% manual Kanban board into a signal-driven CRM pipeline
with meaningful automation while preserving full manual control.

## Current State
- 7 seeded stages: New Lead → Contacted → Qualified → Proposal → Negotiation → Won → Lost
- Kanban board with drag-and-drop
- Manual deal creation (no contact/company picker)
- Activity log: only "Deal created" + stage changes
- Zero integration with campaigns, inbox, contacts, lead scoring, webhooks
- CRM sync is a placeholder stub

## Implementation Phases

### Phase 1: Backend — Deal Automation Service + Triggers
**File**: `backend/app/services/deal_automation.py` (NEW)

- [ ] 1a. `auto_create_deal_from_interested_reply(contact_id, campaign_id, db)`:
  - Check if deal already exists for this contact (avoid duplicates)
  - Create deal: name = "{contact_name} — {company}", stage = "New Lead"
  - Auto-populate: contact_id, client_id (from contact), campaign_id
  - Value = 0 (user fills later), probability = from lead score or 20% default
  - Log activity: "Auto-created from interested reply"
  - Return the new deal or existing deal

- [ ] 1b. `auto_log_email_activity(contact_id, event_type, details, db)`:
  - Find all open deals linked to this contact_id
  - For each deal, insert DealActivity: type = "email_sent"/"email_received"/"email_opened"/"email_bounced"
  - Description = summary (subject, from, timestamp)

- [ ] 1c. `auto_advance_stage(deal_id, signal, db)`:
  - Signal types: "email_sent" → move New Lead → Contacted
  - Signal types: "reply_received" → move Contacted → Qualified
  - Only advance forward (never go back automatically)
  - Check settings for auto_advance_enabled (default True)
  - Log stage change activity

- [ ] 1d. `update_deal_probability_from_score(contact_id, db)`:
  - Get contact's lead_score
  - Map: 0-20 → 10%, 21-40 → 20%, 41-60 → 40%, 61-80 → 60%, 81-100 → 80%
  - Update deal.probability (only if user hasn't manually set it — track with `probability_manual` flag)

- [ ] 1e. `detect_stale_deals(days_threshold, db)` → list of stale deals:
  - Deals with no DealActivity in last X days (default 7)
  - Exclude Won/Lost stages
  - Return list with deal info + days since last activity

### Phase 2: Wire Triggers into Existing Services

- [ ] 2a. **Inbox Syncer** (`inbox_syncer.py`):
  - After AI sentiment classifies a message as "interested" → call `auto_create_deal_from_interested_reply()`
  - After any received message → call `auto_log_email_activity(contact_id, "email_received", ...)`

- [ ] 2b. **Campaign Engine** (`campaign_engine.py`):
  - After sending an email → call `auto_log_email_activity(contact_id, "email_sent", ...)`
  - After first email sent to a contact with a deal → call `auto_advance_stage(deal, "email_sent")`

- [ ] 2c. **Outreach Pipeline** (`pipelines/outreach.py`):
  - After sending outreach → call `auto_log_email_activity()` for each contact

- [ ] 2d. **Lead Scorer** (`lead_scorer.py`):
  - After recalculating scores → call `update_deal_probability_from_score()` for contacts with deals

- [ ] 2e. **Webhook Dispatcher** (`webhook_dispatcher.py`):
  - Add deal events: `deal.created`, `deal.stage_changed`, `deal.won`, `deal.lost`
  - Fire from deals.py endpoints + deal_automation.py

### Phase 3: Backend API Enhancements

- [ ] 3a. **Contact/Client search endpoints** for deal creation picker:
  - `GET /contacts/search?q=term` → returns id, name, email, company (limit 20)
  - `GET /clients/search?q=term` → returns id, name (limit 20)
  - (May already exist — check existing endpoints)

- [ ] 3b. **Deal settings** in settings table:
  - `deal_auto_create_on_interested`: bool (default true)
  - `deal_auto_advance_stages`: bool (default true)
  - `deal_auto_log_activities`: bool (default true)
  - `deal_stale_threshold_days`: int (default 7)
  - `deal_score_to_probability`: bool (default true)

- [ ] 3c. **Stale deals endpoint**:
  - `GET /deals/stale?days=7` → list of stale deals with days_idle

- [ ] 3d. **Deal forecast endpoint**:
  - `GET /deals/forecast` → weighted pipeline (sum of value * probability/100)

### Phase 4: Frontend — Enhanced Deals Page

- [ ] 4a. **Contact/Company picker** in Create Modal:
  - Searchable dropdown for contact (shows name + email)
  - Auto-fills company when contact selected
  - Searchable dropdown for company (independent selection)

- [ ] 4b. **Activity timeline** in Detail Drawer:
  - Show all activities (auto-logged emails + manual notes + stage changes)
  - Icon per type (email, note, stage change, phone)
  - Timestamp + description + metadata

- [ ] 4c. **Stats enhancement**:
  - Add Weighted Forecast card (sum of value * probability/100)
  - Add "Stale Deals" badge/count

- [ ] 4d. **Auto-created deal badge**:
  - Visual indicator on cards that were auto-created (vs manual)
  - "Auto" badge with different border color

- [ ] 4e. **Deal settings** in Settings page:
  - Toggles for each automation (auto-create, auto-advance, auto-log, score→probability)
  - Stale threshold slider (1-30 days)

- [ ] 4f. **Stale deal indicator**:
  - Orange/red border on deal cards that haven't had activity in threshold days
  - Tooltip: "No activity for X days"

## Settings Keys
```
deal_auto_create_on_interested = true
deal_auto_advance_stages = true
deal_auto_log_activities = true
deal_stale_threshold_days = 7
deal_score_to_probability = true
```

## Database Changes
- Add `is_auto_created` Boolean column to `deals` table (default False)
- Add `probability_manual` Boolean column to `deals` table (default False)
  - True when user manually sets probability (prevents auto-override)

## Testing
- Unit tests for deal_automation.py (all 5 functions)
- Integration tests for trigger wiring (mock campaigns/inbox/outreach)
- Frontend: verify picker works, activities render, stats show forecast
