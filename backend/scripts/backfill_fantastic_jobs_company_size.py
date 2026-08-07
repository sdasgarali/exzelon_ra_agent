"""BACKFILL — re-verify Fantastic.jobs leads stored with an understated company
size and EXCLUDE the oversized ones before they cost Apollo contact-discovery
credits.

Why (see Fantastic_Jobs_Company_Size_RCA.md)
--------------------------------------------
Pre-fix, the Fantastic.jobs adapter stored ``org_linkedin_headcount`` (a count of
tagged LinkedIn member profiles — systematically UNDERSTATED) as ``company_size``.
So a 1001-5000-employee company was stored as e.g. "156", passed the >200 ICP
size gate, and reached paid contact discovery. The prod audit found ~503 such
SUSPECT leads still pending (bare-integer size <= ceiling, not yet enriched).

This script re-resolves the TRUE size for those leads via Apollo
``/organizations/enrich`` **by domain** (the authoritative source; cheap
org-enrich credit, NOT a contact-discovery credit), then:
  * size > ceiling  -> mark lead_status = EXCLUDED (+ skip_reason) so contact
    discovery never touches it, and store the authoritative size band;
  * size <= ceiling -> just correct company_size to the authoritative band;
  * unknown / no domain / no Apollo data -> leave untouched (recall preserved).

Cost discipline
---------------
DRY-RUN by default — prints exactly what would change and how many Apollo
org-enrich credits it would spend (one per unique domain). Pass ``--apply`` to
write. Bounded by ``--limit`` (leads considered) and ``--max-lookups`` (Apollo
calls). Only targets bare-integer ("suspect") sizes; trustworthy bands and
already-EXCLUDED leads are skipped.

Usage (run from backend/):
    python scripts/backfill_fantastic_jobs_company_size.py --tenant 1                 # dry run
    python scripts/backfill_fantastic_jobs_company_size.py --tenant 1 --apply         # write
    python scripts/backfill_fantastic_jobs_company_size.py --tenant 1 --include-enriched --apply
"""
import argparse
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.db.base import SessionLocal  # noqa: E402
from app.db.models.lead import LeadDetails, LeadStatus  # noqa: E402
from app.services.company_filters import (  # noqa: E402
    exceeds_size_ceiling_any,
    parse_employee_count,
)
from app.services.company_enrichment import _extract_domain  # noqa: E402
from app.services.company_firmographics import (  # noqa: E402
    enrich_firmographics_batch,
    get_firmographic_provider,
    _get_apollo_key,
)

FJ_SOURCES = ("fantastic_jobs", "linkedin")
PENDING_STATUSES = (LeadStatus.NEW, LeadStatus.OPEN)
# A bare integer (optionally comma-grouped) = the understated headcount-derived
# value. Anything with '-', '+', or 'k' is a trustworthy band.
_NUMERIC_ONLY = re.compile(r"^\s*\d{1,3}(?:,\d{3})*\s*$|^\s*\d+\s*$")


def _is_suspect(value) -> bool:
    text = (value or "").strip()
    return bool(text) and bool(_NUMERIC_ONLY.match(text))


def _domain_for(lead) -> str:
    return _extract_domain(lead.employer_website or "") or ""


def run(tenant_id, ceiling, limit, max_lookups, include_enriched, apply):
    db = SessionLocal()
    try:
        if get_firmographic_provider(db, tenant_id=tenant_id) != "apollo":
            print("ERROR: company_firmographic_provider is not 'apollo' for this "
                  "tenant — cannot re-verify size. Aborting.")
            return
        if not _get_apollo_key(db, tenant_id=tenant_id):
            print("ERROR: no Apollo API key configured. Aborting.")
            return

        q = db.query(LeadDetails).filter(LeadDetails.source.in_(FJ_SOURCES))
        if tenant_id is not None:
            q = q.filter(LeadDetails.tenant_id == tenant_id)
        if not include_enriched:
            q = q.filter(LeadDetails.lead_status.in_(PENDING_STATUSES))
        q = q.order_by(LeadDetails.lead_id)
        leads = q.all()

        # Candidates: suspect bare-integer size, currently within the ceiling (so
        # they were KEPT on an understated signal), with a resolvable domain.
        candidates, no_domain = [], 0
        for ld in leads:
            if ld.lead_status == LeadStatus.EXCLUDED:
                continue
            if not _is_suspect(ld.company_size):
                continue
            parsed = parse_employee_count(ld.company_size)
            if parsed is None or parsed > ceiling:
                continue  # already over the ceiling / unparseable — the gate handles it
            if not _domain_for(ld):
                no_domain += 1
                continue
            candidates.append(ld)

        if limit:
            candidates = candidates[:limit]

        # Dedupe Apollo lookups by domain (many leads share a company).
        by_domain = {}
        for ld in candidates:
            by_domain.setdefault(_domain_for(ld), ld.client_name)
        unique_domains = len(by_domain)

        print("=" * 70)
        print(f"Fantastic.jobs size re-verify backfill  ·  tenant {tenant_id}  ·  "
              f"ceiling >{ceiling}  ·  {'APPLY' if apply else 'DRY RUN'}")
        print("=" * 70)
        print(f"Candidate suspect leads (bare-int size <= ceiling, has domain): "
              f"{len(candidates)}")
        print(f"  unique domains to look up (Apollo credits)  : {unique_domains}")
        print(f"  suspect leads skipped — no resolvable domain: {no_domain}")
        print(f"  scope: {'ALL non-excluded' if include_enriched else 'still-pending only'}")

        if not candidates:
            print("Nothing to do.")
            return

        # One Apollo org-enrich per unique domain (name, domain) items.
        items = [(name, dom) for dom, name in by_domain.items()]
        if not apply:
            print(f"\n[DRY RUN] Would spend up to "
                  f"{min(unique_domains, max_lookups)} Apollo org-enrich credits.")
            print("Re-run with --apply to write. Preview of candidates:")
            for ld in candidates[:15]:
                print(f"  lead {ld.lead_id}  R{ld.run_id or '-'}  "
                      f"size={ld.company_size:<6}  {ld.client_name[:40]}  "
                      f"[{_domain_for(ld)}]")
            if len(candidates) > 15:
                print(f"  ... and {len(candidates) - 15} more")
            return

        firmo = enrich_firmographics_batch(
            db, items, tenant_id=tenant_id, max_lookups=max_lookups,
        )

        excluded = corrected = unresolved = 0
        reasons = Counter()
        for ld in candidates:
            key = (ld.client_name or "").strip().lower()
            m = firmo.get(key)
            if not m:
                unresolved += 1
                continue
            true_emp = m.get("employee_count")
            true_band = m.get("company_size")
            # Conservative: judge the largest of the authoritative size and the
            # (understated) stored value.
            over = exceeds_size_ceiling_any(
                [true_emp, true_band, ld.company_size], ceiling
            )
            if over:
                ld.lead_status = LeadStatus.EXCLUDED
                ld.skip_reason = (
                    f"size_ceiling: Apollo re-verify = {true_emp or true_band} "
                    f"(>{ceiling}); stored '{ld.company_size}' was understated "
                    f"LinkedIn headcount"
                )
                if true_band:
                    ld.company_size = str(true_band)[:100]
                excluded += 1
                reasons[true_band or str(true_emp)] += 1
            else:
                # In-band — just correct the stored size to the authoritative band.
                if true_band and true_band != ld.company_size:
                    ld.company_size = str(true_band)[:100]
                    corrected += 1

        db.commit()
        print("\nBackfill complete:")
        print(f"  leads EXCLUDED (were oversized, credits saved): {excluded}")
        print(f"  leads size-corrected (still in-band)          : {corrected}")
        print(f"  unresolved (Apollo had no data — left as-is)  : {unresolved}")
        if reasons:
            print("  excluded by resolved size band:")
            for band, n in reasons.most_common():
                print(f"    {band:<12} {n}")
    except Exception as e:
        db.rollback()
        print(f"ERROR: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tenant", type=int, default=1, help="Tenant id (default 1)")
    ap.add_argument("--ceiling", type=int, default=200,
                    help="ICP employee ceiling (default 200)")
    ap.add_argument("--limit", type=int, default=None,
                    help="Cap candidate leads considered")
    ap.add_argument("--max-lookups", type=int, default=1000,
                    help="Hard cap on Apollo org-enrich calls (default 1000)")
    ap.add_argument("--include-enriched", action="store_true",
                    help="Also re-verify already-enriched leads (default: pending only)")
    ap.add_argument("--apply", action="store_true",
                    help="Write changes (default: dry run)")
    args = ap.parse_args()
    run(args.tenant, args.ceiling, args.limit, args.max_lookups,
        args.include_enriched, args.apply)
