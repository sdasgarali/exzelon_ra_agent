# Campaign Enrollment: Lead-Based Contact Selection

## Goal
Replace the flat contact list in the "Enroll Contacts" modal with a lead-centric expandable UI:
- Show leads (job postings) as expandable rows
- Expanding a lead shows its linked contacts with status badges
- Contacts have checkboxes — disabled for inactive/archived/unsubscribed
- Search filters both leads and contacts

## Current Flow
1. User clicks "Enroll Contacts" in campaign detail → Contacts tab
2. Modal loads all contacts with `validation_status='valid'` (flat list, up to 200)
3. User selects contacts via checkboxes
4. Submits → `POST /campaigns/{id}/contacts` with `{ contact_ids: [...] }`

## New Flow
1. User clicks "Enroll Contacts"
2. Modal loads leads (paginated, searchable by company/title/state)
3. Each lead row shows: company name, job title, state, contact count
4. Click chevron to expand → fetches linked contacts for that lead
5. Contacts show: name, email, status badge (Active/Validated/Unsubscribed/Archived)
6. Checkbox enabled only for enrollable contacts (active + valid email)
7. Disabled contacts show tooltip/reason why they can't be selected
8. "Select All" per lead to select all eligible contacts
9. Summary bar shows total selected count across all leads
10. Submit → same `POST /campaigns/{id}/contacts` endpoint (no backend changes needed)

## Implementation

### Step 1: Backend — New endpoint for leads with contact counts (~20 LOC)

**File**: `backend/app/api/endpoints/leads.py`

Add: `GET /leads/with-contacts` — returns leads with contact count for each, optimized for the enrollment modal.

```python
@router.get("/with-contacts")
def list_leads_with_contact_counts(
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db, user
):
    # Join leads → LeadContactAssociation → count
    # Return: lead_id, client_name, job_title, state, contact_count
```

### Step 2: Frontend — Add `leadsApi.listWithContactCounts()` method (~5 LOC)

**File**: `frontend/src/lib/api.ts`

Add method to `leadsApi`:
```typescript
listWithContacts: async (params) => api.get('/leads/with-contacts', { params })
```

### Step 3: Frontend — Rewrite Enroll Modal (~200 LOC)

**File**: `frontend/src/app/dashboard/campaigns/page.tsx`

Replace the current flat contact list with:

**State additions**:
- `enrollLeads: LeadWithCount[]` — paginated lead list
- `expandedLeadIds: Set<number>` — which leads are expanded
- `leadContacts: Record<number, Contact[]>` — cached contacts per lead
- `loadingLeadContacts: Set<number>` — loading state per lead
- `selectedContactIds: number[]` — (already exists, reuse)

**UI structure**:
```
┌─────────────────────────────────────────┐
│ Enroll Contacts from Leads              │
│ [Search leads...                      ] │
│─────────────────────────────────────────│
│ ▶ Acme Inc — Software Engineer (TX)  3  │
│ ▼ Beta Corp — HR Manager (CA)        2  │
│   ☑ Jane Doe  jane@beta.com  ● Active  │
│   ☐ John Doe  john@beta.com  ● Unsub   │  ← disabled
│ ▶ Gamma LLC — Sales Dir (NY)         1  │
│─────────────────────────────────────────│
│ 3 contacts selected                     │
│ [Cancel]           [Enroll 3 Contacts]  │
└─────────────────────────────────────────┘
```

**Contact status logic**:
- Enrollable (checkbox enabled): `is_archived=false` AND `outreach_status != 'unsubscribed'` AND `validation_status = 'valid'`
- Show but disabled: unsubscribed, archived, invalid email
- Badge colors: Active/green, Validated/blue, Unsubscribed/red, Archived/gray, Invalid/yellow

**Expand behavior**:
- Click lead row → toggle expand
- On first expand → `GET /contacts?lead_id={id}&page_size=100` (existing endpoint)
- Cache results in `leadContacts[leadId]`
- "Select All Eligible" checkbox per lead header

### Step 4: Verify build + tests

## Files Changed

| # | File | Action | LOC |
|---|------|--------|-----|
| 1 | `backend/app/api/endpoints/leads.py` | MODIFY | +30 |
| 2 | `frontend/src/lib/api.ts` | MODIFY | +5 |
| 3 | `frontend/src/app/dashboard/campaigns/page.tsx` | MODIFY | ~150 (replace enroll modal section) |
