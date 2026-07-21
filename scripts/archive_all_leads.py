#!/usr/bin/env python3
"""Soft-archive all existing leads (is_archived = 1).

Archived leads are hidden from the leads UI by default and excluded from
contact-enrichment, company-enrichment, and outreach selection — a clean
"start fresh" that keeps every row (fully reversible by flipping the flag back).

Backs up the ids it flips (only currently-unarchived rows) to
/tmp/leads_prearchive_backup.json so an exact revert is possible.
Dry-run by default; pass --execute to commit.
"""
import argparse
import json

from sqlalchemy import text
from app.db.base import SessionLocal

BACKUP = "/tmp/leads_prearchive_backup.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true", help="commit the archive (default: dry-run)")
    args = ap.parse_args()

    db = SessionLocal()
    total = db.execute(text("SELECT COUNT(*) FROM lead_details")).scalar()
    archived = db.execute(text("SELECT COUNT(*) FROM lead_details WHERE is_archived = 1")).scalar()
    to_flip = db.execute(text("SELECT COUNT(*) FROM lead_details WHERE is_archived = 0")).scalar()
    print(f"leads total={total}  already_archived={archived}  will_archive={to_flip}")
    print("by tenant (currently unarchived):")
    for tid, cnt in db.execute(text(
        "SELECT tenant_id, COUNT(*) FROM lead_details WHERE is_archived = 0 GROUP BY tenant_id ORDER BY tenant_id")):
        print(f"  tenant {tid}: {cnt}")

    # Backup the exact ids we will flip (so revert only touches these).
    ids = [r[0] for r in db.execute(text("SELECT lead_id FROM lead_details WHERE is_archived = 0"))]
    with open(BACKUP, "w", encoding="utf-8") as f:
        json.dump({"archived_lead_ids": ids}, f)
    print(f"Backup of {len(ids)} lead_ids -> {BACKUP} (revert source)")

    if not args.execute:
        print("\nDRY RUN — no changes. Re-run with --execute to archive.")
        return

    updated = db.execute(text("UPDATE lead_details SET is_archived = 1 WHERE is_archived = 0")).rowcount
    db.commit()
    after_arch = db.execute(text("SELECT COUNT(*) FROM lead_details WHERE is_archived = 1")).scalar()
    after_active = db.execute(text("SELECT COUNT(*) FROM lead_details WHERE is_archived = 0")).scalar()
    print(f"\nRESULT (committed): flipped {updated} rows")
    print(f"  archived: {archived} -> {after_arch}")
    print(f"  active (unarchived) remaining: {after_active}  (expect 0)")


if __name__ == "__main__":
    main()
