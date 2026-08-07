"""AUDIT (read-only) — quantify Fantastic.jobs leads stored with an understated
company size, to size the Apollo-credit waste before deciding on a fix.

Background (see Fantastic_Jobs_Company_Size_RCA.md)
--------------------------------------------------
Fantastic.jobs returns two LinkedIn size signals per company:
  * ``org_linkedin_headcount`` — a count of *tagged member profiles*
    (systematically UNDERSTATED), and
  * ``org_linkedin_size``      — the company's SELF-REPORTED size band
    (e.g. "1001-5000"), i.e. the number shown on the LinkedIn profile.

The old adapter stored the understated headcount as ``company_size`` (a bare
integer string like "156"), so oversized companies passed the ICP size gate and
we spent Apollo contact-discovery credits on them. The fix stores the band going
forward; this script measures the EXISTING damage.

A fantastic_jobs lead whose stored ``company_size`` is a bare integer is
therefore SUSPECT — the true size may be far larger. Leads whose stored size is
already a band ("201-500") are trustworthy.

This script is strictly READ-ONLY. It writes nothing and spends no API credits.

Usage (run from backend/):
    python scripts/audit_fantastic_jobs_company_size.py
    python scripts/audit_fantastic_jobs_company_size.py --tenant 1
    python scripts/audit_fantastic_jobs_company_size.py --ceiling 200 --sample 25
"""
import argparse
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.db.base import SessionLocal  # noqa: E402
from app.db.models.lead import LeadDetails, LeadStatus  # noqa: E402
from app.services.company_filters import parse_employee_count  # noqa: E402

# Fantastic.jobs leads land under these source labels.
FJ_SOURCES = ("fantastic_jobs", "linkedin")

# Statuses that indicate contact discovery has ALREADY run (Apollo credits spent)
# vs. still pending (future waste risk if not re-verified).
ENRICHED_STATUSES = {
    LeadStatus.ENRICHED, LeadStatus.VALIDATED, LeadStatus.SENT,
    LeadStatus.HUNTING, LeadStatus.CLOSED_HIRED, LeadStatus.CLOSED_NOT_HIRED,
}
PENDING_STATUSES = {LeadStatus.NEW, LeadStatus.OPEN}

# A bare integer (optionally with thousands commas) — the understated,
# headcount-derived value. A band contains a '-', '+', or 'k'/'K'.
_NUMERIC_ONLY = re.compile(r"^\s*\d{1,3}(?:,\d{3})*\s*$|^\s*\d+\s*$")


def _classify_size(value):
    """Return one of: 'blank', 'numeric', 'band'."""
    text = (value or "").strip()
    if not text:
        return "blank"
    if _NUMERIC_ONLY.match(text):
        return "numeric"
    return "band"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tenant", type=int, default=None, help="Restrict to one tenant_id")
    ap.add_argument("--ceiling", type=int, default=200,
                    help="ICP employee ceiling used to flag 'would-pass' leads (default 200)")
    ap.add_argument("--sample", type=int, default=15,
                    help="How many suspect leads to print as examples (default 15)")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        q = db.query(LeadDetails).filter(LeadDetails.source.in_(FJ_SOURCES))
        if args.tenant is not None:
            q = q.filter(LeadDetails.tenant_id == args.tenant)
        leads = q.all()

        total = len(leads)
        by_class = Counter()
        by_status = Counter()
        # Suspect = numeric stored size that PASSES the ceiling (so it was kept /
        # enriched) — the population most likely to have wasted credits.
        suspect_enriched = []   # numeric, passes ceiling, already enriched
        suspect_pending = []    # numeric, passes ceiling, still pending
        already_excluded = 0

        for ld in leads:
            cls = _classify_size(ld.company_size)
            by_class[cls] += 1
            by_status[_status_val(ld.lead_status)] += 1
            if ld.lead_status == LeadStatus.EXCLUDED:
                already_excluded += 1
                continue
            if cls != "numeric":
                continue
            parsed = parse_employee_count(ld.company_size)
            if parsed is None or parsed > args.ceiling:
                continue  # would already be dropped by the gate — not the bug
            # Numeric size <= ceiling: kept on an understated signal → suspect.
            if ld.lead_status in ENRICHED_STATUSES:
                suspect_enriched.append(ld)
            else:
                suspect_pending.append(ld)

        # ---- Report ---------------------------------------------------------
        scope = f"tenant {args.tenant}" if args.tenant is not None else "ALL tenants"
        print("=" * 72)
        print(f"Fantastic.jobs company-size audit  ·  {scope}  ·  ceiling >{args.ceiling}")
        print("=" * 72)
        print(f"Total fantastic_jobs/linkedin leads : {total}")
        print(f"  stored size = bare integer (SUSPECT): {by_class['numeric']}")
        print(f"  stored size = band (trustworthy)     : {by_class['band']}")
        print(f"  stored size = blank/unknown          : {by_class['blank']}")
        print(f"  already EXCLUDED                     : {already_excluded}")
        print()
        print("Status distribution:")
        for st, n in sorted(by_status.items(), key=lambda kv: -kv[1]):
            print(f"  {st:<20} {n}")
        print()
        print("SUSPECT leads (bare-integer size <= ceiling, so kept on an")
        print("understated headcount — true size may be far larger):")
        print(f"  already enriched (Apollo credits LIKELY already spent): {len(suspect_enriched)}")
        print(f"  still pending    (FUTURE waste risk if not re-verified): {len(suspect_pending)}")
        print()
        sample = (suspect_enriched + suspect_pending)[: args.sample]
        if sample:
            print(f"Examples (first {len(sample)}):")
            print(f"  {'lead_id':<10} {'status':<16} {'size':<10} company")
            for ld in sample:
                lid = getattr(ld, "lead_ref", None) or ld.id
                print(f"  {str(lid):<10} {_status_val(ld.lead_status):<16} "
                      f"{str(ld.company_size):<10} {(ld.client_name or '')[:40]}")
        print()
        print("NOTE: stored bare-integer sizes cannot be trusted for "
              "fantastic_jobs leads.")
        print("      To recover true sizes, re-verify via Apollo firmographic-by-"
              "domain (paid).")
        print("      Re-run after the adapter fix ships to confirm new leads store "
              "bands, not integers.")
    finally:
        db.close()


def _status_val(status):
    return status.value if hasattr(status, "value") else str(status)


if __name__ == "__main__":
    main()
