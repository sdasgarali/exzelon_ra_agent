#!/usr/bin/env python3
"""Hard-delete the gate-flagged unwanted leads while PRESERVING companies and
contacts.

- Reads the approved lead_ids from /tmp/unwanted_leads.csv (produced by
  profile_unwanted_leads.py).
- Backs up the exact rows to be removed to /tmp/unwanted_leads_backup.json.
- Aborts if any outreach_events / outreach_drafts / campaign_contacts row
  references these leads (those FKs are ON DELETE NO ACTION).
- Dry-run by default. Pass --execute to commit the DELETE.

contact_details.lead_id is ON DELETE SET NULL (contacts survive) and
lead_contact_associations.lead_id is ON DELETE CASCADE (join rows auto-clean).
client_info is never referenced by a lead FK and is not touched.
"""
import argparse
import csv
import json

from sqlalchemy import text
from app.db.base import SessionLocal

IDS_CSV = "/tmp/unwanted_leads.csv"
BACKUP = "/tmp/unwanted_leads_backup.json"
NO_ACTION_TABLES = ["outreach_events", "outreach_drafts", "campaign_contacts"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true", help="commit the DELETE (default: dry-run)")
    args = ap.parse_args()

    db = SessionLocal()
    ids = [int(r["lead_id"]) for r in csv.DictReader(open(IDS_CSV))]
    if not ids:
        print("No ids in", IDS_CSV, "- nothing to do.")
        return
    ph = ",".join(str(i) for i in ids)
    print(f"Target unwanted leads: {len(ids)}")

    before_leads = db.execute(text("SELECT COUNT(*) FROM lead_details")).scalar()
    before_contacts = db.execute(text("SELECT COUNT(*) FROM contact_details")).scalar()
    before_clients = db.execute(text("SELECT COUNT(*) FROM client_info")).scalar()

    # Guard: NO ACTION FK tables must have zero references, else DELETE fails.
    for tbl in NO_ACTION_TABLES:
        n = db.execute(text(f"SELECT COUNT(*) FROM {tbl} WHERE lead_id IN ({ph})")).scalar()
        if n:
            print(f"ABORT: {tbl} has {n} row(s) referencing these leads "
                  f"(ON DELETE NO ACTION). Handle those first.")
            return
    print("Safety: 0 outreach/draft/campaign child rows — clean to delete.")

    # Backup exactly what will be removed / altered.
    lead_rows = [dict(r._mapping) for r in
                 db.execute(text(f"SELECT * FROM lead_details WHERE lead_id IN ({ph})"))]
    assoc_rows = [dict(r._mapping) for r in
                  db.execute(text(f"SELECT * FROM lead_contact_associations WHERE lead_id IN ({ph})"))]
    contact_links = [dict(r._mapping) for r in
                     db.execute(text(f"SELECT contact_id, lead_id FROM contact_details WHERE lead_id IN ({ph})"))]
    with open(BACKUP, "w", encoding="utf-8") as f:
        json.dump({"leads": lead_rows, "associations": assoc_rows,
                   "contact_links": contact_links}, f, default=str, indent=2)
    print(f"Backup: {BACKUP}  (leads={len(lead_rows)}, associations={len(assoc_rows)}, "
          f"contact_links={len(contact_links)})")

    if not args.execute:
        print(f"\nDRY RUN — would DELETE {len(ids)} leads.")
        print(f"  leads {before_leads} -> {before_leads - len(ids)} | contacts {before_contacts} (Δ0) | "
              f"clients {before_clients} (Δ0)")
        print("Re-run with --execute to commit.")
        return

    # Commit the delete (SET NULL / CASCADE handled by the DB).
    deleted = db.execute(text(f"DELETE FROM lead_details WHERE lead_id IN ({ph})")).rowcount
    db.commit()

    after_leads = db.execute(text("SELECT COUNT(*) FROM lead_details")).scalar()
    after_contacts = db.execute(text("SELECT COUNT(*) FROM contact_details")).scalar()
    after_clients = db.execute(text("SELECT COUNT(*) FROM client_info")).scalar()
    remaining = db.execute(text(f"SELECT COUNT(*) FROM lead_details WHERE lead_id IN ({ph})")).scalar()
    if contact_links:
        cids = ",".join(str(c["contact_id"]) for c in contact_links)
        nulled = db.execute(text(
            f"SELECT COUNT(*) FROM contact_details WHERE contact_id IN ({cids}) AND lead_id IS NULL")).scalar()
        survived = db.execute(text(
            f"SELECT COUNT(*) FROM contact_details WHERE contact_id IN ({cids})")).scalar()
    else:
        nulled = survived = 0

    print("\nRESULT (committed):")
    print(f"  deleted rows: {deleted}")
    print(f"  leads    {before_leads} -> {after_leads}  (−{before_leads - after_leads})")
    print(f"  contacts {before_contacts} -> {after_contacts}  (Δ{after_contacts - before_contacts}; expect 0)")
    print(f"  clients  {before_clients} -> {after_clients}  (Δ{after_clients - before_clients}; expect 0)")
    print(f"  unwanted remaining: {remaining}  (expect 0)")
    print(f"  formerly-linked contacts: {survived} survived, {nulled} now lead_id NULL "
          f"(of {len(contact_links)})")


if __name__ == "__main__":
    main()
