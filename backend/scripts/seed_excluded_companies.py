"""Seed excluded companies from the USA staffing Excel file.

Usage:
    cd backend
    python scripts/seed_excluded_companies.py [--tenant-id 1] [--file path/to/xlsx]

This script reads the Excel file and inserts all companies as excluded
for the given tenant (defaults to tenant_id=1 = exzelon).
"""
import sys
import os
import argparse

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import openpyxl
from app.db.base import SessionLocal, Base, engine
# Import all models so metadata knows about all tables
from app.db.models import *  # noqa: F403
from app.db.models.company_exclusion import CompanyExclusion, normalize_company_for_exclusion


def seed_from_xlsx(file_path: str, tenant_id: int = 1, lob_id: int = None):
    """Read Excel and seed company exclusions."""
    # Ensure all tables exist (handles FK dependencies)
    Base.metadata.create_all(bind=engine)
    print("Table 'company_exclusions' ensured")

    wb = openpyxl.load_workbook(file_path, read_only=True)
    ws = wb.active

    db = SessionLocal()
    try:
        # Load existing normalized names for this tenant
        existing = set(
            r[0] for r in db.query(CompanyExclusion.company_name_normalized)
            .filter(CompanyExclusion.tenant_id == tenant_id)
            .all()
        )

        created = 0
        skipped = 0
        for row in ws.iter_rows(min_row=2, values_only=True):
            company_name = row[0]
            category = row[2] if len(row) > 2 else None

            if not company_name:
                continue

            company_name = str(company_name).strip()
            normalized = normalize_company_for_exclusion(company_name)

            if not normalized or normalized in existing:
                skipped += 1
                continue

            exclusion = CompanyExclusion(
                tenant_id=tenant_id,
                lob_id=lob_id,
                company_name=company_name,
                company_name_normalized=normalized,
                category=str(category).strip() if category else None,
                is_active=True,
            )
            db.add(exclusion)
            existing.add(normalized)
            created += 1

        db.commit()
        print(f"Done: {created} companies added, {skipped} duplicates skipped")
    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        raise
    finally:
        db.close()
        wb.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed excluded companies from Excel")
    parser.add_argument("--file", default=r"C:\Users\Anas\Downloads\usa_staffing_1000_plus.xlsx",
                        help="Path to Excel file")
    parser.add_argument("--tenant-id", type=int, default=1, help="Tenant ID (default: 1)")
    parser.add_argument("--lob-id", type=int, default=None, help="LOB ID to scope exclusions to")
    args = parser.parse_args()

    if not os.path.exists(args.file):
        print(f"Error: File not found: {args.file}")
        sys.exit(1)

    seed_from_xlsx(args.file, tenant_id=args.tenant_id, lob_id=args.lob_id)
