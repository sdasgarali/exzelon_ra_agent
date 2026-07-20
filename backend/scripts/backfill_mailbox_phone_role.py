"""One-time backfill for existing mailboxes missing a phone or a role.

Rules (per stakeholder):
  - Blank/NULL phone  -> the mailbox's own tenant.phone, falling back to
    Tenant 1's phone (the default) when the tenant has none.
  - NULL outreach_role_id -> that tenant's role named "RA" (case-insensitive);
    if the tenant has no "RA" role, fall back to Tenant 1's "RA" role only for
    tenant-1 mailboxes, otherwise skip (logged).

Idempotent. Dry-run by default; pass --commit to persist.

Usage:
  python scripts/backfill_mailbox_phone_role.py            # dry-run
  python scripts/backfill_mailbox_phone_role.py --commit   # apply
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.db.base import SessionLocal
from app.db.models.sender_mailbox import SenderMailbox
from app.db.models.tenant import Tenant
from app.db.models.outreach_role import OutreachRole
from app.schemas.sender_mailbox import normalize_us_phone

DEFAULT_TENANT_ID = 1
RA_ROLE_NAME = "RA"


def _blank(v) -> bool:
    return v is None or str(v).strip() == ""


def main(commit: bool) -> None:
    db = SessionLocal()
    try:
        # Tenant phone map + default (Tenant 1) phone
        tenant_phone = {t.tenant_id: t.phone for t in db.query(Tenant).all()}
        default_phone = tenant_phone.get(DEFAULT_TENANT_ID)
        if _blank(default_phone):
            print(f"WARNING: Tenant {DEFAULT_TENANT_ID} has no phone; blank phones with no tenant phone will be left as-is.")

        # RA role per tenant (case-insensitive match on role_name)
        ra_role_by_tenant = {}
        for r in db.query(OutreachRole).all():
            if (r.role_name or "").strip().lower() == RA_ROLE_NAME.lower():
                ra_role_by_tenant[r.tenant_id] = r.role_id
        default_ra_role = ra_role_by_tenant.get(DEFAULT_TENANT_ID)
        if default_ra_role is None:
            print(f"WARNING: Tenant {DEFAULT_TENANT_ID} has no '{RA_ROLE_NAME}' role; tenant-1 role backfill will be skipped.")

        mailboxes = db.query(SenderMailbox).all()
        phone_filled = role_filled = phone_skipped = role_skipped = 0

        for mb in mailboxes:
            # Phone
            if _blank(mb.phone):
                candidate = tenant_phone.get(mb.tenant_id)
                if _blank(candidate):
                    candidate = default_phone
                if not _blank(candidate):
                    try:
                        mb.phone = normalize_us_phone(candidate)
                        phone_filled += 1
                    except ValueError:
                        mb.phone = candidate  # keep raw if it doesn't parse as US
                        phone_filled += 1
                else:
                    phone_skipped += 1

            # Role
            if mb.outreach_role_id is None:
                role_id = ra_role_by_tenant.get(mb.tenant_id)
                if role_id is None and mb.tenant_id == DEFAULT_TENANT_ID:
                    role_id = default_ra_role
                if role_id is not None:
                    mb.outreach_role_id = role_id
                    role_filled += 1
                else:
                    role_skipped += 1

        print(f"Mailboxes scanned : {len(mailboxes)}")
        print(f"Phone  -> filled  : {phone_filled}  (skipped, no source phone: {phone_skipped})")
        print(f"Role   -> filled  : {role_filled}  (skipped, no RA role: {role_skipped})")

        if commit:
            db.commit()
            print("COMMITTED.")
        else:
            db.rollback()
            print("DRY-RUN (no changes saved). Re-run with --commit to apply.")
    finally:
        db.close()


if __name__ == "__main__":
    main(commit="--commit" in sys.argv)
