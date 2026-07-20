#!/usr/bin/env python3
"""Fantastic.jobs / Active Jobs DB — yield validation prototype.

Purpose: BEFORE committing to a plan, measure how many jobs matching the
Exzelon ICP (US, 1-200 employees, non-IT/non-staffing/non-healthcare, direct
employer, fresh) Fantastic.jobs can actually deliver per day — with company
details attached — so we can check it against the 2,000 valid jobs/day target.

It fetches the LinkedIn job-board feed, then applies every ICP filter CLIENT-SIDE
on the rich per-job company fields (org_linkedin_headcount, org_linkedin_industry,
org_linkedin_recruitment_agency_derived), and prints a funnel + projected/day.
Client-side filtering makes it robust to RapidAPI-vs-direct parameter naming and,
more importantly, directly measures whether the DATA supports the ICP.

USAGE (with your 7-day trial key):
  # RapidAPI "Active Jobs DB" (default):
  export FANTASTIC_JOBS_API_KEY="<your-rapidapi-key>"
  python scripts/validate_fantastic_jobs.py --pages 5 --window 7d

  # options:
  #   --pages N       pages of 100 to pull (sample size)   [default 5]
  #   --window 7d|24h time window (feed path)              [default 7d]
  #   --host HOST     RapidAPI host [active-jobs-db.p.rapidapi.com]
  #   --max-emp 200   employee-count ceiling               [default 200]
  #   --location "United States"

Requires: httpx  (already in backend/requirements.txt)
"""
import argparse
import os
import sys
from collections import Counter

try:
    import httpx
except ImportError:
    print("Missing dependency: pip install httpx", file=sys.stderr)
    sys.exit(1)

# ── ICP definition (mirror of the production business rules) ──────────────────
# Representative target titles (production uses settings.TARGET_JOB_TITLES).
TARGET_TITLES = [
    "HR Manager", "HR Director", "Human Resources", "Operations Manager",
    "Office Manager", "Plant Manager", "Warehouse Manager", "Project Manager",
    "Construction Manager", "Manufacturing Manager", "Production Manager",
    "Controller", "Accounting Manager", "Office Administrator", "Branch Manager",
    "General Manager", "Estimator", "Superintendent", "Logistics Manager",
]
# LinkedIn industries to EXCLUDE (IT / staffing / healthcare / insurance).
EXCLUDE_INDUSTRIES = {i.lower() for i in [
    "Software Development", "Information Technology and Services",
    "IT Services and IT Consulting", "Technology, Information and Internet",
    "Computer Software", "Computer & Network Security", "Internet",
    "Computer and Network Security", "Information Services",
    "Hospital & Health Care", "Hospitals and Health Care",
    "Health, Wellness and Fitness", "Medical Practices", "Medical Practice",
    "Pharmaceuticals", "Biotechnology", "Biotechnology Research",
    "Mental Health Care", "Insurance", "Staffing and Recruiting",
]}


def build_url(host: str, window: str) -> str:
    # RapidAPI "Active Jobs DB" feed paths embed the window: active-jb-7d / -24h.
    win = "24h" if window in ("24h", "1d", "day") else "7d"
    return f"https://{host}/active-jb-{win}"


def fetch_page(client, url, host, key, location, title_filter, offset, max_emp):
    params = {
        "limit": 100,
        "offset": offset,
        "location_filter": location,
        "title_filter": title_filter,           # Boolean OR of target titles
        "description_type": "text",
        # ask for AI + org enrichment (param names differ across variants; extra
        # params are ignored where unsupported — the org fields are what we need)
        "include_ai": "true",
        "include_basic_organization_details": "true",
        # server-side size filter (direct v1 API; ignored by variants that lack it)
        "organization_headcount_gte": 1,
        "organization_headcount_lt": max_emp + 1,
    }
    headers = {"x-rapidapi-key": key, "x-rapidapi-host": host}
    r = client.get(url, params=params, headers=headers, timeout=60)
    if r.status_code != 200:
        print(f"\nHTTP {r.status_code} from {r.request.url}\n{r.text[:400]}", file=sys.stderr)
        if r.status_code in (401, 403):
            print("→ Check the API key / that you're subscribed to Active Jobs DB.", file=sys.stderr)
        if r.status_code == 404:
            print("→ Endpoint path may differ on your plan; try --window 24h or check your RapidAPI dashboard.", file=sys.stderr)
        return None
    data = r.json()
    return data if isinstance(data, list) else data.get("data") or data.get("jobs") or []


def icp_pass(job, max_emp):
    """Return (ok, reason). Applies the ICP filters on the returned fields."""
    if not (job.get("organization") or job.get("organization_url")):
        return False, "no_company"
    if job.get("org_linkedin_recruitment_agency_derived") is True:
        return False, "staffing_agency"
    ind = (job.get("org_linkedin_industry") or "").strip().lower()
    if ind and ind in EXCLUDE_INDUSTRIES:
        return False, "excluded_industry"
    hc = job.get("org_linkedin_headcount")
    if hc is None:
        return False, "size_unknown"
    try:
        if int(hc) > max_emp or int(hc) < 1:
            return False, "size_out_of_range"
    except (TypeError, ValueError):
        return False, "size_unparseable"
    return True, "valid"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=5)
    ap.add_argument("--window", default="7d")
    ap.add_argument("--host", default="active-jobs-db.p.rapidapi.com")
    ap.add_argument("--location", default="United States")
    ap.add_argument("--max-emp", type=int, default=200)
    ap.add_argument("--key", default=os.environ.get("FANTASTIC_JOBS_API_KEY"))
    args = ap.parse_args()

    if not args.key:
        print("Set FANTASTIC_JOBS_API_KEY (RapidAPI key) or pass --key.", file=sys.stderr)
        sys.exit(2)

    url = build_url(args.host, args.window)
    title_filter = " OR ".join(f'"{t}"' for t in TARGET_TITLES)
    window_days = 1 if args.window in ("24h", "1d", "day") else 7

    print(f"Endpoint : {url}")
    print(f"Window   : {args.window}  |  Location: {args.location}  |  Size ≤ {args.max_emp}")
    print(f"Titles   : {len(TARGET_TITLES)} target titles (Boolean OR)\n")

    total = 0
    reasons = Counter()
    valid = []
    with httpx.Client() as client:
        for p in range(args.pages):
            batch = fetch_page(client, url, args.host, args.key, args.location,
                               title_filter, p * 100, args.max_emp)
            if batch is None:
                break
            if not batch:
                print(f"page {p+1}: 0 rows (end of feed)")
                break
            total += len(batch)
            for job in batch:
                ok, reason = icp_pass(job, args.max_emp)
                reasons[reason] += 1
                if ok:
                    valid.append(job)
            print(f"page {p+1}: fetched {len(batch)}, cumulative valid {len(valid)}")

    # ── Report ────────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("YIELD FUNNEL")
    print("=" * 60)
    print(f"Fetched (raw)                : {total}")
    for reason in ["no_company", "staffing_agency", "excluded_industry",
                   "size_unknown", "size_out_of_range", "size_unparseable", "valid"]:
        if reasons.get(reason):
            print(f"  {reason:<22}: {reasons[reason]}")
    v = len(valid)
    rate = (v / total * 100) if total else 0
    print(f"\nVALID (ICP-passing)          : {v}  ({rate:.1f}% of fetched)")
    if total:
        per_day = round(v / window_days)
        print(f"Implied valid jobs / day     : ~{per_day}  (over a {window_days}-day window)")
        print(f"Target                       : 2,000 / day  → "
              + ("MEETS TARGET" if per_day >= 2000 else "below target on this sample — widen titles/window or add Indeed+Glassdoor"))

    if valid:
        print("\nSample valid jobs (company details present):")
        for j in valid[:3]:
            print(f"  • {j.get('title')}  @ {j.get('organization')}")
            print(f"    size={j.get('org_linkedin_headcount')}  industry={j.get('org_linkedin_industry')}  "
                  f"posted={j.get('date_posted')}  agency={j.get('org_linkedin_recruitment_agency_derived')}")
            print(f"    {j.get('url')}")

    print("\nNote: this samples a few pages. To estimate true daily yield, run "
          "--window 24h with enough --pages to reach the end of that day's feed.")


if __name__ == "__main__":
    main()
