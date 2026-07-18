"""Pure parser for job-posting applicant/competition counts.

LinkedIn/Indeed job pages surface a competition signal in prose — "Over 100
applicants", "47 people clicked apply", "Be among the first 25 applicants". No
job-board API returns this, so it is scraped from the page (see
``applicant_enrichment``) and parsed here.

Kept dependency-free and side-effect-free so it can be unit-tested without any
network access.
"""
from __future__ import annotations

import re
from typing import Optional

# Ordered patterns. Each captures a number (optionally with thousands commas).
# "over N" / "N+" mean *strictly more than N*, so those are bumped by 1 so a
# ceiling of exactly N still drops them. Everything else is taken literally.
_NUM = r"(\d[\d,]*)"
_EXCEEDING_PATTERNS = [
    re.compile(rf"over\s+{_NUM}\s+(?:applicant|people\s+clicked|clicked\s+apply|applied|applies)", re.I),
    re.compile(rf"{_NUM}\+\s*(?:applicant|people\s+clicked|clicked\s+apply|applies)", re.I),
]
_EXACT_PATTERNS = [
    re.compile(rf"be\s+among\s+the\s+first\s+{_NUM}\s+applicant", re.I),
    re.compile(rf"{_NUM}\s+applicants?\b", re.I),
    re.compile(rf"{_NUM}\s+people\s+clicked\s+apply", re.I),
    re.compile(rf"{_NUM}\s+clicked\s+apply", re.I),
    re.compile(rf"{_NUM}\s+applies\b", re.I),
]


def _to_int(raw: str) -> Optional[int]:
    try:
        return int(raw.replace(",", ""))
    except (ValueError, AttributeError):
        return None


def parse_applicant_count(text: Optional[str]) -> Optional[int]:
    """Extract the strongest applicant/competition count from page text.

    Returns the MAX count found across all recognized phrasings (the strongest
    competition signal), or ``None`` when no count is present. "over N" / "N+"
    are returned as ``N + 1`` so a ceiling of exactly N still treats them as
    exceeding.

    Examples:
        "Over 100 applicants"                 -> 101
        "100+ applicants"                     -> 101
        "47 people clicked apply"             -> 47
        "Be among the first 25 applicants"    -> 25
        "1,024 applicants"                    -> 1024
        "2K alumni" / "" / None               -> None   (not an applicant count)
    """
    if not text:
        return None

    counts = []
    for pat in _EXCEEDING_PATTERNS:
        for m in pat.finditer(text):
            n = _to_int(m.group(1))
            if n is not None:
                counts.append(n + 1)
    for pat in _EXACT_PATTERNS:
        for m in pat.finditer(text):
            n = _to_int(m.group(1))
            if n is not None:
                counts.append(n)

    return max(counts) if counts else None


def applicant_count_exceeds(count, threshold: int) -> bool:
    """True when a KNOWN applicant count is strictly above ``threshold``.

    Recall-preserving: an unknown count (``None``) returns False, and a
    non-positive threshold disables the check entirely.
    """
    if not threshold or threshold <= 0:
        return False
    if count is None:
        return False
    try:
        return int(count) > threshold
    except (ValueError, TypeError):
        return False
