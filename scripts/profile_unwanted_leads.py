#!/usr/bin/env python3
"""READ-ONLY profiler for the 'remove unwanted leads' task.

Classifies every existing lead with the PRODUCTION LeadEligibilityGate (same
rules used at sourcing) and reports:
  1. Every FK that references lead_details + its ON DELETE rule (deletion safety)
  2. Totals (leads / contacts / clients) and lead-status breakdown
  3. Unwanted leads by reason, with tenant split
  4. Impact: how many contacts + companies are PRESERVED
  5. A CSV export of the full unwanted list + an on-screen sample

DOES NOT MODIFY THE DATABASE. Safe to run repeatedly.
"""
import csv
from collections import Counter
from sqlalchemy import text, func

from app.db.base import SessionLocal
from app.db.models.lead import LeadDetails, LeadStatus
from app.db.models.contact import ContactDetails
from app.db.models.client import ClientInfo
from app.services.lead_eligibility import LeadEligibilityGate

db = SessionLocal()

print("=" * 72)
print("1) FOREIGN KEYS REFERENCING lead_details (deletion safety)")
print("=" * 72)
fk_rows = db.execute(text(
    """
    SELECT c.TABLE_NAME, c.COLUMN_NAME, c.CONSTRAINT_NAME, r.DELETE_RULE
    FROM information_schema.KEY_COLUMN_USAGE c
    JOIN information_schema.REFERENTIAL_CONSTRAINTS r
      ON c.CONSTRAINT_NAME = r.CONSTRAINT_NAME
     AND c.CONSTRAINT_SCHEMA = r.CONSTRAINT_SCHEMA
    WHERE c.REFERENCED_TABLE_NAME = 'lead_details'
      AND c.TABLE_SCHEMA = DATABASE()
    ORDER BY r.DELETE_RULE, c.TABLE_NAME
    """
)).fetchall()
blockers = []
for t, col, name, rule in fk_rows:
    flag = "" if rule in ("SET NULL", "CASCADE") else "  <-- BLOCKER (needs handling)"
    if flag:
        blockers.append((t, col, rule))
    print(f"  {t}.{col:16} ON DELETE {rule:9} ({name}){flag}")
if not fk_rows:
    print("  (none found)")

print("\n" + "=" * 72)
print("2) TOTALS + STATUS BREAKDOWN")
print("=" * 72)
total_leads = db.query(func.count(LeadDetails.lead_id)).scalar()
total_contacts = db.query(func.count(ContactDetails.contact_id)).scalar()
total_clients = db.query(func.count(ClientInfo.client_id)).scalar()
print(f"  leads={total_leads}  contacts={total_contacts}  clients={total_clients}")
print("  status:")
for st, cnt in (db.query(LeadDetails.lead_status, func.count())
                .group_by(LeadDetails.lead_status).all()):
    sv = st.value if hasattr(st, "value") else st
    print(f"    {sv:18} {cnt}")

print("\n" + "=" * 72)
print("3) CLASSIFY EVERY LEAD WITH THE PRODUCTION GATE")
print("=" * 72)
gates = {}


def gate_for(tid, lob):
    k = (tid, lob)
    if k not in gates:
        gates[k] = LeadEligibilityGate(db, tenant_id=tid, lob_id=lob)
    return gates[k]


reason_counts = Counter()
reason_by_tenant = Counter()
unwanted = []  # list of (lead, reason)
for lead in db.query(LeadDetails).yield_per(1000):
    eligible, reason = gate_for(lead.tenant_id, lead.lob_id).check(lead)
    if not eligible:
        reason_counts[reason] += 1
        reason_by_tenant[(lead.tenant_id, reason)] += 1
        unwanted.append((lead, reason))

print("  Unwanted by reason (current gate rules; unknown size/industry is NOT dropped):")
for reason, cnt in reason_counts.most_common():
    print(f"    {reason:26} {cnt}")
print(f"    {'TOTAL UNWANTED':26} {len(unwanted)}")

print("\n  By tenant:")
tenants = sorted({t for (t, _) in reason_by_tenant})
for t in tenants:
    tot = sum(c for (tt, _), c in reason_by_tenant.items() if tt == t)
    print(f"    tenant {t}: {tot}")

already_excluded = sum(
    1 for (l, _) in unwanted
    if (l.lead_status == LeadStatus.EXCLUDED or getattr(l.lead_status, "value", l.lead_status) == "excluded")
)
print(f"\n  Of those, already lead_status=EXCLUDED: {already_excluded}")
print(f"  NET NEW removals (not yet EXCLUDED):     {len(unwanted) - already_excluded}")

print("\n" + "=" * 72)
print("4) IMPACT — WHAT IS PRESERVED")
print("=" * 72)
unwanted_ids = [l.lead_id for (l, _) in unwanted]
linked_contacts = 0
for i in range(0, len(unwanted_ids), 1000):
    chunk = unwanted_ids[i:i + 1000]
    if chunk:
        linked_contacts += db.query(func.count(ContactDetails.contact_id)).filter(
            ContactDetails.lead_id.in_(chunk)).scalar()
companies = {(l.tenant_id, (l.client_name or "").strip().lower()) for (l, _) in unwanted}
print(f"  Contacts linked to unwanted leads : {linked_contacts}  -> PRESERVED (lead_id set NULL)")
print(f"  Distinct companies referenced     : {len(companies)}  -> client_info PRESERVED (never touched)")

print("\n" + "=" * 72)
print("5) EXPORT + SAMPLE")
print("=" * 72)
out = "/tmp/unwanted_leads.csv"
with open(out, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["lead_id", "tenant_id", "client_name", "job_title", "industry",
                "company_size", "source", "lead_status", "reason", "has_contacts"])
    for lead, reason in unwanted:
        sv = getattr(lead.lead_status, "value", lead.lead_status)
        w.writerow([lead.lead_id, lead.tenant_id, lead.client_name, lead.job_title,
                    lead.industry, lead.company_size, lead.source, sv, reason,
                    "yes" if lead.contacts else "no"])
print(f"  Full list -> {out} ({len(unwanted)} rows)")
print("\n  Sample (first 30):")
print(f"    {'lead_id':>7} | {'company':34} | {'title':24} | {'industry':16} | {'size':8} | reason")
for lead, reason in unwanted[:30]:
    print(f"    {lead.lead_id:>7} | {(lead.client_name or '')[:34]:34} | "
          f"{(lead.job_title or '')[:24]:24} | {(lead.industry or '-')[:16]:16} | "
          f"{(lead.company_size or '-')[:8]:8} | {reason}")

print("\nDONE (read-only — no changes made).")
