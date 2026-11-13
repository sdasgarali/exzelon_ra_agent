# Plan — Warmup Health Score v2

> Status: **PLANNED, awaiting approval** (2026-11-13). Nothing below is implemented.
> Context: prod review on 2026-11-13 (434 mailboxes). The score was calculated correctly
> but did not track deliverability: brand-new mailboxes showed 85 after one warmup reply, and
> hr@exzelon.com showed 100 while exzelon.com has no DKIM.

## 1. Problems with v1 (`services/pipelines/warmup_engine.py: calculate_health_score`)

| # | Problem | Prod example |
|---|---|---|
| P1 | No data scores as perfect: bounce/complaint = 100 at 0 sends; `min_emails_for_scoring` only gates auto-pause/promotion, not the score | Day-1 mailbox with 2 sends shows 85 |
| P2 | Reply score is full at 10% reply rate, and replies come from our own peer auto-replier (target 50%) | One peer reply moves 60 → 85 |
| P3 | DNS (SPF/DKIM/DMARC) and blacklist results are stored but never used | hr@exzelon.com = 100 with no DKIM |
| P4 | "Age" = time since the mailbox was added to NeuraLeads, not domain/account age | Old domain connected today scores 0 for age |
| P5 | Inbox vs spam placement is never measured (IMAP reader only reads INBOX) | No signal for the thing that matters most |
| P6 | Lifetime counters: old clean history hides a new bounce spike | — |

## 2. Design

### 2.1 Data sufficiency (fixes P1)
- If `total_emails_sent < warmup_min_emails_for_scoring` (default 10): `health_score = null`,
  `data_status = "insufficient_data"`, plus `progress = sent/min`. UI shows "Collecting data (4/10)".
- Averages and charts skip nulls. Promotion/auto-pause logic unchanged (already gated).

### 2.2 Engagement score (weights renormalised over components that have data)

| Component | Weight | Rule |
|---|---|---|
| Bounce | 30 | as v1 (≤2% → 100, ≥5% → 0, linear between) |
| Complaint | 20 | as v1 |
| Reply | 15 | **linear** to `warmup_reply_rate_good`, default raised 10% → **20%** (fixes P2) |
| Inbox placement | 25 | `inbox / (inbox + spam)` over last 14 days; ≥98% → 100, ≤80% → 0. Omitted until ≥10 placements observed (fixes P5) |
| Age | 10 | weight cut from 15; see decision D2 (fixes P4) |

### 2.3 Hard caps (fixes P3) — score = min(engagement score, caps); each cap adds a reason
| Condition (latest `dns_check_results` row / `sender_mailboxes.is_blacklisted`) | Cap |
|---|---|
| Blacklisted | 40 |
| SPF or DKIM invalid | 60 |
| DMARC missing | 80 |
| No DNS check yet | no cap, reason "dns_unchecked" |

Response gains `caps_applied: [{reason, cap}]` so the UI can say *why* (e.g. "Capped at 60: DKIM missing").

### 2.4 Inbox placement measurement (P5)
- New column `warmup_emails.placement` (`inbox|spam|unknown`, default `unknown`) — **Alembic** migration.
- `imap_reader`: also open the Junk folder (IMAP `LIST` special-use `\Junk`; fallbacks
  `Junk Email`, `[Gmail]/Spam`, `Junk`, `Spam`). For warmup mail from peers: match Message-ID →
  set `placement`; spam copies are **moved to INBOX and marked read** (spam rescue, also a
  reputation signal). INBOX hits → `placement = inbox`.
- Include `COLD_READY` and `RECOVERING` in the IMAP read cycle (needed since maintenance warmup, #152).
- Fix cycle length: today 5–15 s sleep per mailbox × 434 mailboxes ≈ 72 min on a 30-min
  interval, so cycles are skipped. Use a bounded thread pool / shorter jitter.

### 2.5 Rolling window (P6)
- Bounce/complaint/reply rates from the last 14 days (`warmup_emails` + `outreach_events`),
  falling back to lifetime counters when the window has < min emails.

### 2.6 Rollout
- Setting `warmup_health_score_version` (1|2). Ship with **1**, run a shadow comparison script
  on prod data (v1 vs v2 distribution per status/domain), review with user, then flip to **2**.
- `warmup_daily_logs.health_score` keeps storing a number (0 for insufficient data is NOT used —
  store NULL; check column nullability first).

## 3. Touch points
- `services/pipelines/warmup_engine.py` (score, assess, promotion threshold usage)
- `api/endpoints/warmup.py` (overview, health-scores, averages), `api/endpoints/deliverability.py` (2 call sites use `float(...)`)
- `services/warmup/scheduler.py` (daily log snapshot), `services/warmup/imap_reader.py`
- `schemas/warmup.py` (nullable score, components, caps, data_status)
- `db/models/warmup_email.py` + Alembic revision; `CLAUDE_REFERENCE/data-models.md`, `services.md`
- MCP: `mcp_server` health tools pass the new fields through
- Frontend `dashboard/warmup/page.tsx` (null score, cap reasons, placement %), deliverability page

## 4. Tasks
- [ ] 1. Decisions D1–D4 confirmed by user
- [ ] 2. Score v2 function + data-sufficiency + caps, behind `warmup_health_score_version` (unit tests per rule)
- [ ] 3. API/schema/MCP: nullable score, components, `caps_applied`, `data_status`; averages skip nulls
- [ ] 4. Frontend: "Collecting data", cap reasons, placement column
- [ ] 5. Alembic `warmup_emails.placement`; IMAP Junk scan + rescue; include COLD_READY/RECOVERING; bounded cycle time
- [ ] 6. Rolling 14-day rates
- [ ] 7. Shadow script v1 vs v2 on prod → review with user
- [ ] 8. Full suites, PR, deploy with version 1, then flip to 2 after review

## 5. Acceptance criteria
- Mailbox with < 10 sends shows "Collecting data", never a number.
- hr@exzelon.com (no DKIM) shows ≤ 60 with reason "DKIM missing" until DKIM is published.
- A blacklisted mailbox never shows > 40.
- One peer reply no longer moves a mailbox by 25 points.
- Placement % visible per mailbox once ≥ 10 warmup emails were seen by peers.
- Flipping `warmup_health_score_version` back to 1 restores v1 numbers exactly.

## 6. Decisions needed
- **D1** Reply target: 20% (recommended) or keep 10%?
- **D2** Age: (a) keep platform age at weight 10 (recommended, no external calls) or (b) real domain age via RDAP lookup, cached per domain.
- **D3** Cap values 40 / 60 / 80 OK?
- **D4** Should a score below a threshold (e.g. 50) stop the mailbox from being picked for campaigns? Today `mailbox_selector` ignores health. Out of scope unless requested.

## 7. Expected prod impact (once on v2)
- The 300 new neuraforz mailboxes: "Collecting data" for their first ~4–5 warmup days, then a number.
- ali@ / hr@ / Zanemartin@exzelon.com: capped at 60 until exzelon.com DKIM is enabled.
- Cold-ready Exzelon mailboxes: settle by bounce/placement once maintenance warmup (#152) runs.
