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
# Manufacturing, Insurance, Financial Services, Construction, etc.). Notably we
# do NOT include a bare "technology" (would catch "Biotechnology") or bare
# "internet".
DEFAULT_EXCLUDED_INDUSTRY_KEYWORDS = [
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
