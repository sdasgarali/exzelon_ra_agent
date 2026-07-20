"""Email Humanizer — post-generation pass to defeat AI content detectors.

Applies natural imperfections, varied sentence structure, and conversational
markers to AI-generated email copy so it reads like a busy human typed it
between meetings rather than a polished LLM output.

Anti-AI-detection guidance embedded in this module:
- Vary sentence length (burstiness) — AI text is uniformly mid-length
- Inject natural imperfections — dashes, ellipses, parenthetical asides
- Break paragraph uniformity — humans write uneven paragraphs
- Add conversational starters — "Honestly,", "Quick thought —", etc.
- NEVER start with "I hope this email finds you well" or "I wanted to reach out"
"""
import html as html_lib
import math
import random
import re
from typing import Dict, List

import structlog

logger = structlog.get_logger()

# Conversational starters — sprinkled into 10-20% of sentences
_CONVERSATIONAL_STARTERS = [
    "Honestly, ",
    "Quick thought — ",
    "By the way, ",
    "Oh, ",
    "Actually, ",
    "Side note — ",
    "Between us, ",
    "Real talk — ",
    "Funny enough, ",
    "Worth mentioning — ",
]

# Sentence-merge connectors
_MERGE_CONNECTORS = [" — ", "... ", " — basically, "]

# AI red-flag openers to strip if present
_AI_OPENERS = [
    re.compile(r"^I hope this (?:email |message )?finds you well[.,]?\s*", re.IGNORECASE),
    re.compile(r"^I (?:just )?wanted to reach out[.,]?\s*", re.IGNORECASE),
    re.compile(r"^I came across your (?:company|profile|posting)[.,]?\s*", re.IGNORECASE),
    re.compile(r"^I hope you(?:'re| are) (?:doing |having a )?(?:well|great)[.,]?\s*", re.IGNORECASE),
]


def humanize_email(
    subject: str,
    body_html: str,
    body_text: str,
    intensity: str = "medium",
) -> Dict[str, object]:
    """Main entry point — apply humanization pass to AI-generated email.

    Args:
        subject: Email subject line.
        body_html: HTML email body (with <p> tags).
        body_text: Plain-text email body.
        intensity: "light" | "medium" | "heavy".

    Returns:
        {subject, body_html, body_text, modifications: list[str]}
    """
    if intensity not in ("light", "medium", "heavy"):
        intensity = "medium"

    modifications: List[str] = []

    # Preserve the rendered email signature — the humanizer must never rewrite
    # or drop it. Split it off, humanize only the message, re-attach at the end.
    message_html, signature_html = _split_signature(body_html)

    # Work on the message plain text first, then mirror changes back to HTML.
    working_text = _strip_html(message_html)

    # Step 0: Strip AI red-flag openers
    cleaned, stripped = _strip_ai_openers(working_text)
    if stripped:
        working_text = cleaned
        modifications.append(f"removed_ai_opener:{stripped}")

    # Step 1: Vary sentence length
    before = working_text
    working_text = _vary_sentence_length(working_text)
    if working_text != before:
        modifications.append("varied_sentence_length")

    # Step 2: Add conversational markers
    before = working_text
    working_text = _add_conversational_markers(working_text)
    if working_text != before:
        modifications.append("added_conversational_markers")

    # Step 3: Inject natural imperfections
    before = working_text
    working_text = _inject_natural_imperfections(working_text, intensity)
    if working_text != before:
        modifications.append(f"injected_imperfections:{intensity}")

    # Step 4: Vary paragraph structure in HTML (message only)
    result_html = message_html
    before_html = result_html
    result_html = _vary_paragraph_structure(result_html)
    if result_html != before_html:
        modifications.append("varied_paragraph_structure")

    # Rebuild HTML body from modified text if we changed the text
    if modifications:
        result_html = _rebuild_html_from_text(working_text, message_html)

    # Re-attach the untouched signature block.
    result_html = result_html + signature_html
    sig_text = _strip_html(signature_html)
    result_text = working_text + (("\n\n" + sig_text) if sig_text else "")

    # Apply opener stripping to subject too
    for pattern in _AI_OPENERS:
        subject = pattern.sub("", subject)

    logger.info(
        "email_humanized",
        intensity=intensity,
        modifications=modifications,
        burstiness=round(compute_burstiness_score(working_text), 3),
    )

    return {
        "subject": subject.strip(),
        "body_html": result_html,
        "body_text": result_text,
        "modifications": modifications,
    }


def _split_signature(html: str) -> tuple:
    """Split an email body into (message_html, signature_html).

    The signature is the block produced by render_signature_html, identifiable
    by its distinctive top-border style. Returns ("", "") boundaries so callers
    can humanize the message without touching the signature.
    """
    if not html:
        return html, ""
    pos = html.find("border-top:1px solid #cccccc")
    if pos == -1:
        return html, ""
    div_start = html.rfind("<div", 0, pos)
    if div_start == -1:
        return html, ""
    return html[:div_start], html[div_start:]


# ---------------------------------------------------------------------------
# Sentence-length variation
# ---------------------------------------------------------------------------

def _vary_sentence_length(text: str) -> str:
    """Split into sentences, occasionally merge short ones or split long ones.

    Goal: break AI's uniform sentence-length pattern and increase burstiness.
    """
    sentences = _split_sentences(text)
    if len(sentences) < 3:
        return text

    result = []
    i = 0
    while i < len(sentences):
        sent = sentences[i].strip()
        if not sent:
            i += 1
            continue

        word_count = len(sent.split())

        # Merge two consecutive short sentences (~30% chance)
        if (
            word_count <= 8
            and i + 1 < len(sentences)
            and len(sentences[i + 1].split()) <= 10
            and random.random() < 0.3
        ):
            connector = random.choice(_MERGE_CONNECTORS)
            next_sent = sentences[i + 1].strip()
            # Lower-case next sentence start if merging
            if next_sent and next_sent[0].isupper() and not next_sent.startswith("I "):
                next_sent = next_sent[0].lower() + next_sent[1:]
            merged = sent.rstrip(".!?") + connector + next_sent
            result.append(merged)
            i += 2
            continue

        # Split long sentences at a comma (~25% chance)
        if word_count > 20 and "," in sent and random.random() < 0.25:
            comma_pos = sent.find(",", len(sent) // 3)
            if comma_pos > 0:
                first_half = sent[:comma_pos].strip() + "."
                second_half = sent[comma_pos + 1:].strip()
                if second_half:
                    second_half = second_half[0].upper() + second_half[1:]
                result.append(first_half)
                result.append(second_half)
                i += 1
                continue

        result.append(sent)
        i += 1

    return " ".join(result)


# ---------------------------------------------------------------------------
# Natural imperfections
# ---------------------------------------------------------------------------

def _inject_natural_imperfections(text: str, intensity: str) -> str:
    """Add natural human typing artifacts based on intensity level.

    - light: occasional dash usage, ellipsis
    - medium: above + inconsistent contractions, parenthetical asides
    - heavy: above + rare double-space, missing comma before "but"
    """
    if intensity == "light":
        return _light_imperfections(text)
    elif intensity == "medium":
        text = _light_imperfections(text)
        return _medium_imperfections(text)
    else:  # heavy
        text = _light_imperfections(text)
        text = _medium_imperfections(text)
        return _heavy_imperfections(text)


def _light_imperfections(text: str) -> str:
    """Light: occasional dash and ellipsis usage."""
    sentences = _split_sentences(text)
    if len(sentences) < 3:
        return text

    # Add ellipsis to one sentence ending (~20% of sentences, max 1)
    added_ellipsis = False
    result = []
    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
        if (
            not added_ellipsis
            and sent.endswith(".")
            and len(sent.split()) >= 5
            and random.random() < 0.2
        ):
            sent = sent[:-1] + "..."
            added_ellipsis = True
        result.append(sent)

    # Replace one comma-separated clause with em-dash style (~25% chance)
    text = " ".join(result)
    if random.random() < 0.25:
        # Find pattern: "word, like/such as/which/who X," and wrap with dashes
        text = re.sub(
            r", ((?:like|such as|which|who) [^,]{5,30}),",
            r" — \1 —",
            text,
            count=1,
        )

    return text


def _medium_imperfections(text: str) -> str:
    """Medium: inconsistent contractions and parenthetical asides."""
    # Randomly expand one contraction (inconsistency)
    contractions_map = {
        "I'm": "I am",
        "we're": "we are",
        "We're": "We are",
        "it's": "it is",
        "It's": "It is",
        "don't": "do not",
        "Don't": "Do not",
        "doesn't": "does not",
        "can't": "cannot",
        "won't": "will not",
    }
    expanded = False
    for contraction, expansion in contractions_map.items():
        if contraction in text and not expanded and random.random() < 0.35:
            # Only expand one occurrence to create inconsistency
            text = text.replace(contraction, expansion, 1)
            expanded = True
            break

    # Add one parenthetical aside (~30% chance)
    if random.random() < 0.3:
        asides = [
            "(just a thought)",
            "(from what I can tell)",
            "(no pressure)",
            "(if that helps)",
            "(we see this a lot)",
        ]
        sentences = _split_sentences(text)
        if len(sentences) >= 3:
            # Insert aside after a middle sentence
            mid = len(sentences) // 2
            sent = sentences[mid].strip()
            if sent.endswith("."):
                sentences[mid] = sent[:-1] + " " + random.choice(asides) + "."
            text = " ".join(s.strip() for s in sentences if s.strip())

    return text


def _heavy_imperfections(text: str) -> str:
    """Heavy: rare double-space or missing comma before 'but'."""
    # Occasionally add a double space (~20% chance, max 1)
    if random.random() < 0.2:
        words = text.split(" ")
        if len(words) > 10:
            pos = random.randint(5, len(words) - 3)
            words[pos] = words[pos] + " "  # double space
            text = " ".join(words)

    # Drop comma before "but" in one place (~25% chance)
    if ", but " in text and random.random() < 0.25:
        text = text.replace(", but ", " but ", 1)

    return text


# ---------------------------------------------------------------------------
# Paragraph structure variation
# ---------------------------------------------------------------------------

def _vary_paragraph_structure(html: str) -> str:
    """Ensure paragraphs are not all the same length.

    If all <p> blocks are within 20% of each other's word count, merge or split
    to create variety.
    """
    # Extract paragraph contents
    paragraphs = re.findall(r"<p>(.*?)</p>", html, re.DOTALL)
    if len(paragraphs) < 3:
        return html

    word_counts = [len(p.split()) for p in paragraphs]
    avg = sum(word_counts) / len(word_counts) if word_counts else 0
    if avg == 0:
        return html

    # Check if all are within 20% of average
    all_similar = all(
        abs(wc - avg) / avg <= 0.2 for wc in word_counts if avg > 0
    )

    if not all_similar:
        return html  # Already varied enough

    # Merge two shortest consecutive paragraphs
    min_pair_idx = 0
    min_pair_sum = float("inf")
    for i in range(len(paragraphs) - 1):
        pair_sum = word_counts[i] + word_counts[i + 1]
        if pair_sum < min_pair_sum:
            min_pair_sum = pair_sum
            min_pair_idx = i

    new_paragraphs = list(paragraphs)
    merged = new_paragraphs[min_pair_idx] + " " + new_paragraphs[min_pair_idx + 1]
    new_paragraphs[min_pair_idx] = merged
    del new_paragraphs[min_pair_idx + 1]

    # Rebuild HTML
    result = html
    for i, old_p in enumerate(paragraphs):
        if i < len(new_paragraphs):
            result = result.replace(f"<p>{old_p}</p>", f"<p>{new_paragraphs[i]}</p>", 1)
        else:
            result = result.replace(f"<p>{old_p}</p>", "", 1)

    return result


# ---------------------------------------------------------------------------
# Conversational markers
# ---------------------------------------------------------------------------

def _add_conversational_markers(text: str) -> str:
    """Occasionally prepend sentences with conversational starters.

    Only add to 10-20% of sentences, max 2 per email.
    """
    sentences = _split_sentences(text)
    if len(sentences) < 4:
        return text

    markers_added = 0
    max_markers = 2
    target_rate = random.uniform(0.10, 0.20)

    result = []
    for i, sent in enumerate(sentences):
        sent = sent.strip()
        if not sent:
            continue

        # Skip first sentence, and only add to non-short sentences
        should_add = (
            i > 0
            and markers_added < max_markers
            and len(sent.split()) >= 5
            and random.random() < target_rate
            and not any(sent.startswith(s) for s in _CONVERSATIONAL_STARTERS)
        )

        if should_add:
            starter = random.choice(_CONVERSATIONAL_STARTERS)
            # Lower-case the sentence start (unless "I")
            if sent[0].isupper() and not sent.startswith("I ") and not sent.startswith("I'"):
                sent = sent[0].lower() + sent[1:]
            sent = starter + sent
            markers_added += 1

        result.append(sent)

    return " ".join(result)


# ---------------------------------------------------------------------------
# Burstiness scoring
# ---------------------------------------------------------------------------

def compute_burstiness_score(text: str) -> float:
    """Measure sentence-length variance (std_dev / mean).

    Higher = more human-like. AI text typically scores 0.2-0.4, humans 0.5-0.8.

    Returns:
        Float in range 0.0-1.0. Clamped at 1.0.
    """
    sentences = _split_sentences(text)
    lengths = [len(s.split()) for s in sentences if s.strip()]

    if len(lengths) < 2:
        return 0.0

    mean = sum(lengths) / len(lengths)
    if mean == 0:
        return 0.0

    variance = sum((l - mean) ** 2 for l in lengths) / len(lengths)
    std_dev = math.sqrt(variance)

    score = std_dev / mean
    return min(1.0, score)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _split_sentences(text: str) -> List[str]:
    """Split text into sentences, preserving common abbreviations."""
    # Handle ellipsis first to avoid splitting on them
    text = text.replace("...", "\x00ELLIPSIS\x00")
    # Split on sentence-ending punctuation followed by space + capital or end
    parts = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)
    # Restore ellipsis
    return [p.replace("\x00ELLIPSIS\x00", "...") for p in parts if p.strip()]


def _strip_html(html_text: str) -> str:
    """Strip HTML tags and decode entities to get plain text."""
    text = re.sub(r"<br\s*/?>", "\n", html_text)
    text = re.sub(r"</p>", "\n\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html_lib.unescape(text)
    return text.strip()


def _strip_ai_openers(text: str) -> tuple:
    """Remove known AI red-flag opening phrases. Returns (cleaned, stripped_phrase)."""
    for pattern in _AI_OPENERS:
        match = pattern.search(text)
        if match:
            return pattern.sub("", text).strip(), match.group(0).strip()
    return text, ""


def _rebuild_html_from_text(modified_text: str, original_html: str) -> str:
    """Rebuild HTML by wrapping modified text paragraphs in <p> tags.

    Preserves the overall HTML structure pattern from the original.
    """
    # If original has <p> tags, rebuild with them
    if "<p>" in original_html:
        paragraphs = [p.strip() for p in modified_text.split("\n\n") if p.strip()]
        if not paragraphs:
            paragraphs = [modified_text.strip()]
        return "".join(f"<p>{p}</p>" for p in paragraphs)

    return modified_text
