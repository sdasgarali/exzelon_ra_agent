"""Spintax processing engine for email content variation.

Supports nested spintax: {Hello|Hi {there|friend}} → "Hello" or "Hi there" or "Hi friend"
Uses contact_id as seed for deterministic per-contact variation.

Gap 12 enhancement: campaign_id can be mixed into the seed so the same
contact gets different spintax variants across different campaigns,
preventing identical emails from being sent to the same recipient.
"""
import re
import random


# Pattern matches innermost {option1|option2} first (no nested braces)
_SPINTAX_PATTERN = re.compile(r"\{([^{}]+)\}")


def process_spintax(
    text: str,
    seed: int | None = None,
    campaign_id: int | None = None,
) -> str:
    """Process spintax patterns in text, resolving from innermost out.

    Args:
        text: Text containing {option1|option2|option3} patterns.
        seed: Optional seed for deterministic randomness (use contact_id).
        campaign_id: Optional campaign ID to mix into seed so the same
            contact gets different variants across different campaigns.

    Returns:
        Text with all spintax patterns resolved to one random option.
    """
    if not text or "{" not in text:
        return text

    # Mix campaign_id into seed for cross-campaign variation
    effective_seed = seed
    if seed is not None and campaign_id is not None:
        # Combine contact_id and campaign_id into a single seed
        # Using a simple hash-like combination that produces different
        # but deterministic results per campaign
        effective_seed = seed * 31 + campaign_id

    rng = random.Random(effective_seed)

    # Temporarily replace template placeholders so they aren't processed as spintax.
    # {{contact_first_name}} → \x00PLACEHOLDER_0\x00, etc.
    placeholders: list[str] = []
    def _stash_placeholder(m: re.Match) -> str:
        idx = len(placeholders)
        placeholders.append(m.group(0))
        return f"\x00PH{idx}\x00"

    text = re.sub(r"\{\{\w+\}\}", _stash_placeholder, text)

    # Resolve innermost patterns first, repeat until no patterns remain
    max_iterations = 50  # safety limit for deeply nested spintax
    for _ in range(max_iterations):
        match = _SPINTAX_PATTERN.search(text)
        if not match:
            break
        options = match.group(1).split("|")
        chosen = rng.choice(options)
        text = text[:match.start()] + chosen + text[match.end():]

    # Restore template placeholders
    for idx, ph in enumerate(placeholders):
        text = text.replace(f"\x00PH{idx}\x00", ph)

    return text


def count_variants(text: str) -> int:
    """Count total possible variant combinations in spintax text.

    Template placeholders (``{{...}}``) are excluded from the count.
    """
    if not text or "{" not in text:
        return 1

    # Strip template placeholders so {{var}} doesn't count as a 1-option group
    cleaned = re.sub(r"\{\{\w+\}\}", "", text)

    total = 1
    for match in _SPINTAX_PATTERN.finditer(cleaned):
        options = match.group(1).split("|")
        total *= len(options)
    return total


def validate_spintax(text: str) -> list[str]:
    """Validate spintax syntax and return list of errors (empty = valid).

    Checks for:
    - Unbalanced braces
    - Empty options
    - Single-option groups (pointless)

    Template placeholders like ``{{contact_first_name}}`` are stripped before
    validation so they are not mistakenly flagged as single-option spintax groups.
    """
    errors = []
    if not text:
        return errors

    # Strip template placeholders ({{...}}) before validation — they are not spintax
    cleaned = re.sub(r"\{\{\w+\}\}", "", text)

    # Check brace balance
    depth = 0
    for i, ch in enumerate(cleaned):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                errors.append(f"Unexpected closing brace at position {i}")
                return errors
    if depth != 0:
        errors.append(f"Unclosed braces: {depth} opening brace(s) without matching close")
        return errors

    # Check for empty options and single-option groups
    for match in _SPINTAX_PATTERN.finditer(cleaned):
        options = match.group(1).split("|")
        if len(options) < 2:
            errors.append(f"Single-option group at position {match.start()}: {{{match.group(1)}}}")
        for idx, opt in enumerate(options):
            if not opt.strip():
                errors.append(f"Empty option #{idx + 1} in group at position {match.start()}")

    return errors
