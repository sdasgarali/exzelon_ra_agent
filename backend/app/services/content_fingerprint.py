"""Content Fingerprint Guard — detect overly similar outbound emails.

ESPs flag accounts that send near-identical emails at volume. This module
computes content fingerprints and similarity scores so the campaign engine
can monitor (and eventually gate) content uniqueness before sending.
"""
import hashlib
import math
import re
import string
from collections import Counter
from typing import Optional

import structlog
from sqlalchemy.orm import Session

from app.db.models.outreach import OutreachEvent, OutreachStatus

logger = structlog.get_logger()

# HTML tag stripper (reuse for body normalization)
_HTML_TAG_RE = re.compile(r"<[^>]+>")

# Template placeholder patterns (Jinja2 / mustache / spintax leftovers)
_PLACEHOLDER_RE = re.compile(
    r"\{\{[^}]+\}\}"       # {{variable}}
    r"|\{%[^%]+%\}"        # {% block %}
    r"|\{[^{}|]+\|[^}]+\}" # {option1|option2} spintax
)


def compute_content_hash(text: str) -> str:
    """Compute a SHA-256 hash of normalized text.

    Normalization: lowercase, strip whitespace, remove punctuation.

    Args:
        text: Raw text content.

    Returns:
        Hex digest of the SHA-256 hash.
    """
    normalized = text.lower().strip()
    normalized = normalized.translate(str.maketrans("", "", string.punctuation))
    # Collapse all whitespace to single spaces
    normalized = " ".join(normalized.split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def compute_shingles(text: str, n: int = 3) -> set[str]:
    """Generate word-level n-gram shingles from text.

    Args:
        text: Input text.
        n: Shingle size (number of words per shingle). Default 3.

    Returns:
        Set of shingle strings joined by spaces.
    """
    # Strip HTML for a fair comparison
    clean = _HTML_TAG_RE.sub(" ", text)
    words = clean.lower().split()
    if len(words) < n:
        # If text is shorter than n words, return a single shingle of all words
        return {" ".join(words)} if words else set()
    return {" ".join(words[i : i + n]) for i in range(len(words) - n + 1)}


def jaccard_similarity(set_a: set, set_b: set) -> float:
    """Compute Jaccard similarity between two sets.

    J(A, B) = |A intersection B| / |A union B|

    Args:
        set_a: First set.
        set_b: Second set.

    Returns:
        Similarity score in [0.0, 1.0]. Returns 0.0 if both sets are empty.
    """
    if not set_a and not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


def check_content_uniqueness(
    db: Session,
    body_html: str,
    campaign_id: int,
    tenant_id: int,
    threshold: float = 0.85,
) -> dict:
    """Check whether an outgoing email body is too similar to recent sends.

    Compares the new body against the last 20 sent outreach events for the
    same campaign using Jaccard similarity on word-level 3-shingles.

    Args:
        db: Database session.
        body_html: HTML body of the email about to be sent.
        campaign_id: The campaign this email belongs to.
        tenant_id: Tenant scope.
        threshold: Similarity threshold above which content is flagged as
            not unique (default 0.85).

    Returns:
        Dict with keys:
            - unique (bool): True if content is sufficiently different.
            - max_similarity (float): Highest Jaccard score found.
            - similar_event_id (int | None): event_id of the most similar
              recent send, or None if all are below threshold.
            - warning (str): Human-readable message.
    """
    result = {
        "unique": True,
        "max_similarity": 0.0,
        "similar_event_id": None,
        "warning": "",
    }

    if not body_html:
        return result

    new_shingles = compute_shingles(body_html)
    if not new_shingles:
        return result

    # Fetch the last 20 sent events for this campaign
    recent_events = (
        db.query(OutreachEvent)
        .filter(
            OutreachEvent.campaign_id == campaign_id,
            OutreachEvent.tenant_id == tenant_id,
            OutreachEvent.status == OutreachStatus.SENT,
            OutreachEvent.body_html.isnot(None),
        )
        .order_by(OutreachEvent.sent_at.desc())
        .limit(20)
        .all()
    )

    if not recent_events:
        return result

    max_sim = 0.0
    most_similar_id: Optional[int] = None

    for event in recent_events:
        if not event.body_html:
            continue
        event_shingles = compute_shingles(event.body_html)
        sim = jaccard_similarity(new_shingles, event_shingles)
        if sim > max_sim:
            max_sim = sim
            most_similar_id = event.event_id

    result["max_similarity"] = round(max_sim, 4)

    if max_sim > threshold:
        result["unique"] = False
        result["similar_event_id"] = most_similar_id
        result["warning"] = (
            f"Content similarity {max_sim:.1%} exceeds threshold "
            f"{threshold:.1%}. ESPs may flag this as bulk/spam. "
            f"Most similar to event_id={most_similar_id}."
        )

    return result


def compute_entropy_score(subject: str, body: str) -> dict:
    """Compute a content variability score based on Shannon entropy.

    Higher entropy indicates more character diversity (good). The presence
    of template placeholders or personalized tokens boosts the score.

    Args:
        subject: Email subject line.
        body: Email body (HTML or plain text).

    Returns:
        Dict with keys:
            - subject_entropy (float): Shannon entropy of the subject.
            - body_entropy (float): Shannon entropy of the body.
            - has_personalization (bool): True if template variables detected.
            - score (int, 0-100): Overall variability score.
              <30 = high risk (too generic), 30-60 = moderate, >60 = good.
    """
    subject_entropy = _shannon_entropy(subject)
    body_clean = _HTML_TAG_RE.sub(" ", body) if body else ""
    body_entropy = _shannon_entropy(body_clean)

    # Check for personalization markers
    has_personalization = bool(
        _PLACEHOLDER_RE.search(subject or "")
        or _PLACEHOLDER_RE.search(body or "")
    )

    # Score calculation:
    # Base: average of normalized entropies (max realistic ~4.5 for English)
    max_expected_entropy = 4.5
    norm_subj = min(subject_entropy / max_expected_entropy, 1.0) if subject else 0.0
    norm_body = min(body_entropy / max_expected_entropy, 1.0) if body else 0.0

    # Weighted: body matters more than subject (70/30)
    base_score = (norm_subj * 0.3 + norm_body * 0.7) * 80  # max 80 from entropy

    # Personalization bonus: +20 if placeholders detected
    personalization_bonus = 20 if has_personalization else 0

    score = int(min(base_score + personalization_bonus, 100))

    return {
        "subject_entropy": round(subject_entropy, 4),
        "body_entropy": round(body_entropy, 4),
        "has_personalization": has_personalization,
        "score": score,
    }


def _shannon_entropy(text: str) -> float:
    """Compute Shannon entropy (bits) for a string.

    H = -SUM(p_i * log2(p_i)) for each unique character.

    Returns 0.0 for empty strings.
    """
    if not text:
        return 0.0
    counts = Counter(text)
    length = len(text)
    entropy = 0.0
    for count in counts.values():
        p = count / length
        if p > 0:
            entropy -= p * math.log2(p)
    return entropy
