"""Backfill company firmographics (industry + size) onto existing companies/leads.

Fills ``ClientInfo`` (and propagates to ``lead_details``) for companies that are
missing industry / employee_count — the gap seen on metadata-poor sources like
SearchAPI (google_jobs), which return neither firmographics NOR a domain.

Chain per company (best-effort, bounded, cost-tracked):
  1. Domain — use the company's known domain/website; if none and LLM domain
     resolution is enabled, ask the free Groq resolver for the company's website
     and derive a domain (Apollo needs a domain — name-only lookups return
     nothing, verified live).
  2. Firmographics — Apollo /organizations/enrich by domain (authoritative size).
  3. Fallback — if Apollo has no data, keep the free Groq industry/size guess.
  4. Persist to ClientInfo and set lead_details.industry / company_size where NULL.

Usage (run from backend/):
    python scripts/backfill_company_size.py --dry-run                  # preview + counts
    python scripts/backfill_company_size.py --tenant 1 --limit 50      # execute, capped
    python scripts/backfill_company_size.py --since 2026-07-07         # only recent companies
    python scripts/backfill_company_size.py --no-llm-domain            # skip Groq domain guess

Apollo is billed per credit: one credit per company that reaches step 2. Always
--dry-run first to see how many companies would be looked up.
"""
import argparse
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import httpx  # noqa: E402
import structlog  # noqa: E402

from app.db.base import SessionLocal  # noqa: E402
from app.db.models.client import ClientInfo  # noqa: E402
from app.db.models.lead import LeadDetails  # noqa: E402
from app.services.company_firmographics import (  # noqa: E402
    apollo_enrich_by_domain,
    employee_count_to_size,
    _get_apollo_key,
)
from app.services.company_enrichment import _get_ai_adapter, _extract_domain  # noqa: E402

logger = structlog.get_logger()


def _llm_resolve(adapter, name: str) -> dict:
    """Free Groq guess of a company's website/industry/size. Best-effort → {}."""
    if not adapter or not name:
        return {}
    try:
        data = adapter.research_company(company_name=name, domain=None, location=None)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _propagate_to_leads(db, tenant_id, client_name, industry, company_size):
    """Fill industry/company_size on this company's leads where currently NULL."""
    updates = {}
    if industry:
        updates["industry"] = industry
    if company_size:
        updates["company_size"] = company_size
    if not updates:
        return 0
    q = db.query(LeadDetails).filter(LeadDetails.client_name == client_name)
    if tenant_id is not None:
        q = q.filter(LeadDetails.tenant_id == tenant_id)
    # Only touch rows that are actually missing the field(s).
    from sqlalchemy import or_
    conds = []
    if industry:
        conds.append(LeadDetails.industry.is_(None))
    if company_size:
        conds.append(LeadDetails.company_size.is_(None))
    q = q.filter(or_(*conds))
    return q.update(updates, synchronize_session=False)


def run_backfill(tenant_id=None, since=None, limit=None, dry_run=False, use_llm_domain=True):
    db = SessionLocal()
    try:
        api_key = _get_apollo_key(db, tenant_id=tenant_id)
        if not api_key:
            print("ERROR: No Apollo API key (settings apollo_api_key / APOLLO_API_KEY).")
            return

        q = db.query(ClientInfo).filter(
            (ClientInfo.employee_count.is_(None)) | (ClientInfo.industry.is_(None))
        )
        if tenant_id is not None:
            q = q.filter(ClientInfo.tenant_id == tenant_id)
        if since:
            q = q.filter(ClientInfo.created_at >= since)
        q = q.order_by(ClientInfo.client_id)
        if limit:
            q = q.limit(limit)
        clients = q.all()
        total = len(clients)
        print(f"Companies missing industry/size (tenant={tenant_id}, since={since}): {total}")
        if total == 0:
            print("Nothing to do.")
            return

        with_domain = sum(1 for c in clients if c.domain or _extract_domain(c.website or ""))
        print(f"  with a known domain (Apollo-ready now): {with_domain}")
        print(f"  domain-less (need {'LLM domain guess' if use_llm_domain else 'skipped — no domain'}): {total - with_domain}")
        if dry_run:
            print(f"\n[DRY RUN] Would look up up to {total} companies via Apollo (1 credit each).")
            for c in clients[:15]:
                d = c.domain or _extract_domain(c.website or "") or "(no domain)"
                print(f"  - {c.client_name}  [{d}]")
            if total > 15:
                print(f"  ... and {total - 15} more")
            return

        adapter = _get_ai_adapter(db, tenant_id=tenant_id, force_provider="groq") if use_llm_domain else None
        if use_llm_domain and not adapter:
            print("WARN: LLM domain resolution requested but no Groq adapter — domain-less companies will be skipped.")

        updated = leads_touched = apollo_hits = skipped = 0
        with httpx.Client() as http:
            for idx, c in enumerate(clients):
                domain = c.domain or _extract_domain(c.website or "")
                llm = {}
                if not domain and adapter:
                    llm = _llm_resolve(adapter, c.client_name)
                    domain = _extract_domain(llm.get("website") or "")

                org = apollo_enrich_by_domain(http, api_key, domain) if domain else None
                if org:
                    apollo_hits += 1

                # Merge: Apollo authoritative, Groq guess as fallback.
                industry = (org or {}).get("industry") or llm.get("industry")
                emp = (org or {}).get("employee_count")
                company_size = (org or {}).get("company_size")
                if emp is None and llm.get("employee_count"):
                    try:
                        emp = int(llm["employee_count"])
                    except (ValueError, TypeError):
                        emp = None
                if not company_size:
                    company_size = employee_count_to_size(emp) if emp else llm.get("company_size")
                website = (org or {}).get("website_url") if org else llm.get("website")

                changed = False
                if industry and not c.industry:
                    c.industry = str(industry)[:100]
                    changed = True
                if emp and not c.employee_count:
                    c.employee_count = emp
                    changed = True
                if company_size and not c.company_size:
                    c.company_size = str(company_size)[:50]
                    changed = True
                if website and not c.website:
                    c.website = website
                    changed = True
                    if not c.domain:
                        c.domain = _extract_domain(website)
                if (org or {}).get("linkedin_url") and not c.linkedin_url:
                    c.linkedin_url = org["linkedin_url"]
                    changed = True

                if changed:
                    c.enrichment_source = c.enrichment_source or ("apollo_backfill" if org else "llm_backfill")
                    c.enriched_at = c.enriched_at or datetime.utcnow()
                    leads_touched += _propagate_to_leads(
                        db, c.tenant_id, c.client_name, c.industry, c.company_size
                    )
                    updated += 1
                else:
                    skipped += 1

                if (idx + 1) % 25 == 0:
                    db.commit()
                    print(f"  {idx+1}/{total} — updated={updated}, apollo_hits={apollo_hits}, leads={leads_touched}")
                time.sleep(1.0)  # rate limit (Apollo + Groq)

        db.commit()
        print("\nBackfill complete:")
        print(f"  companies processed: {total}")
        print(f"  companies updated:   {updated}  (apollo hits: {apollo_hits})")
        print(f"  lead rows filled:    {leads_touched}")
        print(f"  no data found:       {skipped}")
    except Exception as e:
        db.rollback()
        print(f"ERROR: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Backfill company firmographics (industry+size) via Apollo + Groq")
    p.add_argument("--tenant", type=int, default=None, help="Tenant id to scope (e.g. 1)")
    p.add_argument("--since", type=str, default=None, help="Only companies created on/after YYYY-MM-DD")
    p.add_argument("--limit", type=int, default=None, help="Cap number of companies")
    p.add_argument("--dry-run", action="store_true", help="Preview counts, no changes / no Apollo calls")
    p.add_argument("--no-llm-domain", action="store_true", help="Do NOT use Groq to guess domains for domain-less companies")
    args = p.parse_args()
    run_backfill(
        tenant_id=args.tenant, since=args.since, limit=args.limit,
        dry_run=args.dry_run, use_llm_domain=not args.no_llm_domain,
    )
