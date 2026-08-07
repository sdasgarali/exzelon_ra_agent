"""Pure company-level exclusion filters for lead sourcing.

These helpers decide whether a sourced job/company should be dropped based on
company *attributes* (size, industry, placeholder name) — as opposed to the
keyword/title filters in ``adapters/base.py`` which only match text in the job
title and company name.

Kept dependency-free and side-effect-free so they can be unit-tested in
isolation and reused by the pipeline + backfill scripts.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

# --- Company size ------------------------------------------------------------

# Matches number tokens with an optional K/M multiplier, e.g. "500", "1k", "5K",
# "1.5M". Used to parse both plain counts ("250") and Apollo/LinkedIn-style
# bands ("501-1K employees", "10K+ employees", "201-500").
_NUM_TOKEN_RE = re.compile(r"(\d+(?:\.\d+)?)\s*([km]?)", re.IGNORECASE)
_MULTIPLIER = {"": 1, "k": 1_000, "m": 1_000_000}


def parse_employee_count(value) -> Optional[int]:
    """Parse an employee count from an int or a size string/band.

    Returns the LOWER bound of a range (lenient — keeps a company that *could*
    be within the ceiling) or the single value for a plain count / "N+" band.
    Returns ``None`` when no number can be parsed.

    Examples:
        250            -> 250
        "250"          -> 250
        "201-500"      -> 201
        "501-1K employees" -> 501
        "1K-5K employees"  -> 1000
        "10K+ employees"   -> 10000
        "5000+"        -> 5000
        "" / None / "unknown" -> None
    """
    if value is None:
        return None
    if isinstance(value, bool):  # guard: bool is a subclass of int
        return None
    if isinstance(value, (int, float)):
        return int(value) if value > 0 else None

    text = str(value).strip().lower()
    if not text:
        return None
    # Drop thousands-separator commas ("1,250" → "1250") before tokenizing so
    # they aren't split into separate numbers. Ranges use hyphens, not commas.
    text = text.replace(",", "")

    nums = []
    for num, mult in _NUM_TOKEN_RE.findall(text):
        try:
            nums.append(int(float(num) * _MULTIPLIER[mult.lower()]))
        except (ValueError, KeyError):
            continue
    nums = [n for n in nums if n > 0]
    if not nums:
        return None
    # Range → lower bound; single value / "N+" → that value.
    return min(nums)


def exceeds_size_ceiling(value, ceiling: int) -> bool:
    """True when a parsed employee count is strictly above ``ceiling``.

    Unknown/unparseable sizes return False (never drop on unknown size — recall
    is preserved; the enrichment step is responsible for resolving unknowns).
    """
    if not ceiling or ceiling <= 0:
        return False
    count = parse_employee_count(value)
    if count is None:
        return False
    return count > ceiling


def exceeds_size_ceiling_any(values: Iterable, ceiling: int) -> bool:
    """Conservative multi-signal ceiling check — drops when ANY known signal is
    above ``ceiling`` (compares the LARGEST parsed value).

    A job board can expose more than one size signal for the same company. E.g.
    Fantastic.jobs returns both ``org_linkedin_headcount`` (a count of tagged
    LinkedIn *member profiles* — systematically UNDERSTATED) and
    ``org_linkedin_size`` (the company's SELF-REPORTED size band). Keying a
    cost-control drop gate on the lowest signal lets a large company slip through
    on its understated headcount (the R1603 bug: headcount 156 but band
    "1001-5000"). For exclusion we therefore take the most conservative (largest)
    estimate and drop when it exceeds the ceiling.

    Unknown/unparseable signals are ignored; all-unknown returns False (recall
    preserved — never drop on unknown size). A non-positive ceiling disables it.
    """
    if not ceiling or ceiling <= 0:
        return False
    counts = [parse_employee_count(v) for v in values]
    counts = [c for c in counts if c is not None]
    if not counts:
        return False
    return max(counts) > ceiling


def below_size_floor_any(values: Iterable, floor: int) -> bool:
    """Conservative multi-signal floor check — symmetric to
    :func:`exceeds_size_ceiling_any`.

    Drops only when the LARGEST known size signal is still below ``floor`` so a
    company is never dropped as "too small" while another signal says it could be
    in-band. All-unknown returns False (recall preserved); non-positive floor
    disables it.
    """
    if not floor or floor <= 0:
        return False
    counts = [parse_employee_count(v) for v in values]
    counts = [c for c in counts if c is not None]
    if not counts:
        return False
    return max(counts) < floor


def size_buckets_within_ceiling(ceiling: int) -> list:
    """LinkedIn self-reported size buckets whose lower bound is ``<= ceiling``.

    Used to push a server-side size filter (Fantastic.jobs ``organization_size``,
    which matches the ``org_linkedin_size`` band) so oversized companies are never
    fetched. Recall-preserving in the same lower-bound sense as
    :func:`parse_employee_count`: a bucket is kept if a company in it *could* be
    within the ceiling. Returns ``[]`` for a non-positive ceiling (filter off).

    Example: ceiling 200 -> ['1', '2-10', '11-50', '51-200'] (drops 201-500 and up).
    """
    if not ceiling or ceiling <= 0:
        return []
    # (bucket label, lower bound) — the canonical LinkedIn / Fantastic.jobs bands.
    _BANDS = [
        ("1", 1), ("2-10", 2), ("11-50", 11), ("51-200", 51), ("201-500", 201),
        ("501-1000", 501), ("1001-5000", 1001), ("5001-10000", 5001), ("10001+", 10001),
    ]
    return [label for label, lower in _BANDS if lower <= ceiling]


def below_size_floor(value, floor: int) -> bool:
    """True when a parsed employee count is strictly below ``floor``.

    Symmetric to :func:`exceeds_size_ceiling`: a minimum-size gate that drops
    companies smaller than the ICP band. Recall-preserving in the same way —
    unknown/unparseable sizes return False (never drop on unknown size), and a
    non-positive floor disables the gate (``floor=1`` keeps every company with
    at least one employee, i.e. effectively a no-op that leaves the mechanism in
    place to tighten later).

    Note ``parse_employee_count`` returns the LOWER bound of a band, so a band
    like "51-200" parses to 51 and is compared against the floor — a company is
    only dropped when even the smallest end of its size band is under the floor.
    """
    if not floor or floor <= 0:
        return False
    count = parse_employee_count(value)
    if count is None:
        return False
    return count < floor


# --- Salary -----------------------------------------------------------------


def salary_below_threshold(salary_min, salary_max, threshold) -> bool:
    """True only when a KNOWN salary is confidently below ``threshold``.

    Recall-preserving: we drop a lead solely on salary when the *best-case*
    known figure (the max of whatever is present) is still under the floor.
    Unknown/blank salary, a zero threshold, or a plausibly-hourly figure never
    triggers a drop — those pass through to be resolved downstream.

    Examples (threshold 40000):
        (None, None)      -> False   (unknown — keep)
        (25000, 32000)    -> True    (best case 32k < 40k)
        (25000, 55000)    -> False   (range spans the floor — keep)
        (None, 38000)     -> True    (only known figure is below)
        (30, 45)          -> False   (looks hourly, not annual — keep)
    """
    try:
        thr = int(threshold or 0)
    except (TypeError, ValueError):
        thr = 0
    if thr <= 0:
        return False

    figures = []
    for v in (salary_min, salary_max):
        if v is None:
            continue
        try:
            n = float(v)
        except (TypeError, ValueError):
            continue
        if n > 0:
            figures.append(n)
    if not figures:
        return False

    best = max(figures)
    # Guard against hourly/monthly rates being compared to an annual floor:
    # anything below 1000 is almost certainly not an annual salary.
    if best < 1000:
        return False
    return best < thr


# --- Industry ----------------------------------------------------------------

# Substring keywords (lowercased) that mark an industry as out-of-scope.
# Deliberately precise to avoid dropping target industries (Healthcare,
# Manufacturing, Financial Services, Construction, etc.). Notably we do NOT
# include a bare "technology" (would catch "Biotechnology") or bare "internet".
DEFAULT_EXCLUDED_INDUSTRY_KEYWORDS = [
    # Insurance (excluded per ICP decision 2026-07-17 — was previously a target)
    "insurance",
    # IT / Software
    "information technology",
    "it services",
    "computer software",
    "software development",
    "software",
    "saas",
    "information services",
    "computer hardware",
    "computer networking",
    "semiconductor",
    "technology, information and internet",
    # Staffing & Recruiting
    "staffing",
    "recruiting",
    "recruitment",
    "human resources services",
    "employment services",
    "executive search",
    # Government / Public administration
    "government administration",
    "public administration",
    "government relations",
    "military",
    "legislative office",
    "international affairs",
]


def industry_is_excluded(industry: Optional[str], keywords: Optional[Iterable[str]] = None) -> bool:
    """True when ``industry`` contains any excluded keyword (case-insensitive).

    Empty/unknown industry returns False (resolved by enrichment, not dropped).
    """
    if not industry:
        return False
    text = industry.strip().lower()
    if not text:
        return False
    kw_list = keywords if keywords is not None else DEFAULT_EXCLUDED_INDUSTRY_KEYWORDS
    return any(kw and kw.lower() in text for kw in kw_list)


# --- Placeholder / confidential company names --------------------------------

DEFAULT_PLACEHOLDER_COMPANY_NAMES = {
    "confidential",
    "confidential company",
    "unknown company",
    "unknown",
    "n/a",
    "na",
    "none",
    "undisclosed",
    "undisclosed company",
    "private company",
    "company confidential",
    "stealth",
    "stealth startup",
}


def is_placeholder_company(name: Optional[str], placeholders: Optional[Iterable[str]] = None) -> bool:
    """True when a company name is blank or a known placeholder/confidential value."""
    text = (name or "").strip().lower()
    if not text:
        return True
    pool = set(p.lower() for p in placeholders) if placeholders is not None else DEFAULT_PLACEHOLDER_COMPANY_NAMES
    return text in pool
