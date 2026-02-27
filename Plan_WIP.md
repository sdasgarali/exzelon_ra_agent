# Plan WIP
## SESSION_CONTEXT_RETRIEVAL
> Email thread view, reply tracking, and UNSUBSCRIBE implemented end-to-end. DB migrated (message_id + sender_mailbox_id columns added), lead detail endpoint enriched with contact+sender info, frontend rewritten with inbox-style thread view + Check Replies button + UNSUBSCRIBE badge. All verified: Python compiles, frontend builds clean.

## Immediate TODO
- [ ] End-to-end test: send email -> reply -> verify reply detected
- [ ] End-to-end test: reply with UNSUBSCRIBE -> verify suppression list
- [ ] Manual verification of thread modal UI at /dashboard/leads/2

## Completed
- [x] DB migration: ALTER TABLE outreach_events ADD message_id + sender_mailbox_id (2026-02-26)
- [x] Backend: Enrich lead detail endpoint with contact_name, contact_email, sender_name, sender_email (2026-02-26)
- [x] Frontend: Inbox-style email thread view with HTML iframe, reply blocks, UNSUBSCRIBE badges (2026-02-26)
- [x] Frontend: Check Replies button + status filter tabs (2026-02-26)
- [x] Verification: Python compiles, frontend builds clean (2026-02-26)

## Previous Work
- [x] Reply tracker service (reply_tracker.py) - IMAP reply checker + UNSUBSCRIBE detection (2026-02-26)
- [x] Scheduler job - every 15 min 8am-8pm UTC (2026-02-26)
- [x] API endpoints - /check-replies, /events/{id}/thread (2026-02-26)
- [x] Email Templates feature fully implemented (2026-02-26)

## Blockers / Notes
- Write/Edit tools have Windows path issues; used python3 -c workaround for backend, Write tool for frontend
- SQLAlchemy create_all creates new tables with all columns; existing tables need ALTER TABLE
- Pre-existing TypeScript Set iteration issues fixed in mailboxes + settings pages
- SenderMailbox import added inline in leads.py to avoid circular import issues
