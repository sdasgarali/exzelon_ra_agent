"""Spintax processing engine for email content variation.

Supports nested spintax: {Hello|Hi {there|friend}} → "Hello" or "Hi there" or "Hi friend"
Uses contact_id as seed for deterministic per-contact variation.
"""
import re
import random


# Pattern matches innermost {option1|option2} first (no nested braces)
_SPINTAX_PATTERN = re.compile(r"\{([^{}]+)\}")


def process_spintax(text: str, seed: int | None = None) -> str:
    """Process spintax patterns in text, resolving from innermost out.

    Args:
        text: Text containing {option1|option2|option3} patterns.
        seed: Optional seed for deterministic randomness (use contact_id).

    Returns:
        Text with all spintax patterns resolved to one random option.
    """
    if not text or "{" not in text:
        return text

    rng = random.Random(seed)

    # Resolve innermost patterns first, repeat until no patterns remain
    max_iterations = 50  # safety limit for deeply nested spintax
    for _ in range(max_iterations):
        match = _SPINTAX_PATTERN.search(text)
        if not match:
            break
        options = match.group(1).split("|")
        chosen = rng.choice(options)
        text = text[:match.start()] + chosen + text[match.end():]

    return text


def count_variants(text: str) -> int:
    """Count total possible variant combinations in spintax text.

    Useful for showing users how many unique versions exist.
    """
    if not text or "{" not in text:
        return 1

    total = 1
    for match in _SPINTAX_PATTERN.finditer(text):
        options = match.group(1).split("|")
        total *= len(options)
    return total


def validate_spintax(text: str) -> list[str]:
    """Validate spintax syntax and return list of errors (empty = valid).

    Checks for:
    - Unbalanced braces
    - Empty options
    - Single-option groups (pointless)
    """
    errors = []
    if not text:
        return errors

    # Check brace balance
    depth = 0
    for i, ch in enumerate(text):
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
    for match in _SPINTAX_PATTERN.finditer(text):
        options = match.group(1).split("|")
        if len(options) < 2:
            errors.append(f"Single-option group at position {match.start()}: {{{match.group(1)}}}")
        for idx, opt in enumerate(options):
            if not opt.strip():
                errors.append(f"Empty option #{idx + 1} in group at position {match.start()}")

    return errors
