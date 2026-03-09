"""Spam word checker — scores email content for spam trigger words.

Returns a 0-100 score (0 = clean, 100 = definite spam) with flagged words.
"""
import re
from typing import Dict, Any, List
from html import unescape

# Trigger words with severity: high=10, medium=5, low=2
SPAM_WORDS = {
    # High severity (10 points each)
    "free": 10, "guaranteed": 10, "no obligation": 10, "winner": 10,
    "congratulations": 10, "100% free": 10, "risk-free": 10, "no cost": 10,
    "act now": 10, "urgent": 10, "limited time": 10, "expires": 10,
    "click below": 10, "click here": 10, "order now": 10, "buy now": 10,
    "apply now": 10, "sign up free": 10, "double your": 10, "earn money": 10,
    "make money": 10, "cash bonus": 10, "fast cash": 10, "million dollars": 10,
    "be your own boss": 10, "work from home": 10, "no experience": 10,
    "no strings attached": 10, "no catch": 10, "promise you": 10,
    "weight loss": 10, "lose weight": 10, "miracle": 10, "cure": 10,
    "viagra": 10, "casino": 10, "lottery": 10, "prize": 10,
    # Medium severity (5 points each)
    "limited offer": 5, "special promotion": 5, "exclusive deal": 5,
    "best price": 5, "lowest price": 5, "bargain": 5, "discount": 5,
    "save big": 5, "cheap": 5, "bonus": 5, "gift": 5,
    "additional income": 5, "extra income": 5, "money back": 5,
    "satisfaction guaranteed": 5, "no questions asked": 5,
    "compare rates": 5, "incredible deal": 5, "great offer": 5,
    "for free": 5, "call now": 5, "don't miss": 5, "don't delete": 5,
    "once in a lifetime": 5, "time limited": 5, "while supplies last": 5,
    "offer expires": 5, "instant": 5, "immediately": 5,
    "dear friend": 5, "dear sir": 5, "dear madam": 5,
    "unsubscribe": 5, "opt out": 5, "remove me": 5,
    "increase sales": 5, "increase traffic": 5, "online degree": 5,
    "as seen on": 5, "all natural": 5, "no side effects": 5,
    "accept credit cards": 5, "rates are low": 5, "refinance": 5,
    "pre-approved": 5, "consolidate": 5, "eliminate debt": 5,
    # Low severity (2 points each)
    "opportunity": 2, "offer": 2, "deal": 2, "save": 2,
    "amazing": 2, "incredible": 2, "unbelievable": 2,
    "exclusive": 2, "limited": 2, "special": 2,
    "attention": 2, "important": 2, "reminder": 2,
    "confirm": 2, "verify": 2, "update your": 2,
    "subscribe": 2, "join now": 2, "register": 2,
    "affordable": 2, "competitive": 2, "premium": 2,
    "revolutionary": 2, "breakthrough": 2, "innovative": 2,
    "reply now": 2, "respond now": 2, "act fast": 2,
    "low cost": 2, "no fee": 2, "no charge": 2,
    "top rated": 2, "best selling": 2, "number one": 2,
    "results guaranteed": 2, "proven results": 2,
}

# Additional patterns (regex-based)
SPAM_PATTERNS = [
    (r'!\s*!+', 8, "multiple_exclamation"),      # Multiple exclamation marks
    (r'[A-Z]{5,}', 6, "excessive_caps"),         # Words in ALL CAPS (5+ chars)
    (r'\$\d+', 4, "dollar_amount"),              # Dollar amounts
    (r'%\s*off', 5, "percent_off"),              # % off
    (r'https?://\S+', 2, "url_in_body"),         # URLs in body
    (r'RE:\s|FW:\s', 5, "fake_reply_forward"),   # Fake RE:/FW: in subject
]


def strip_html(html: str) -> str:
    """Remove HTML tags and decode entities."""
    text = re.sub(r'<[^>]+>', ' ', html)
    text = unescape(text)
    return text


def check_spam_score(subject: str, body_html: str) -> Dict[str, Any]:
    """Check email content for spam trigger words and patterns.

    Args:
        subject: Email subject line
        body_html: Email body (HTML or plain text)

    Returns:
        {score: int 0-100, flagged_words: [{word, severity, count, location}], grade: str}
    """
    body_text = strip_html(body_html)
    combined = f"{subject} {body_text}".lower()
    flagged: List[Dict[str, Any]] = []
    total_points = 0

    # Check trigger words
    for word, severity in SPAM_WORDS.items():
        count = len(re.findall(r'\b' + re.escape(word) + r'\b', combined, re.IGNORECASE))
        if count > 0:
            location = "subject" if word.lower() in subject.lower() else "body"
            if word.lower() in subject.lower() and word.lower() in body_text.lower():
                location = "both"
            points = severity * count
            # Subject words count double
            if location in ("subject", "both"):
                points = int(points * 1.5)
            total_points += points
            severity_label = "high" if severity >= 10 else ("medium" if severity >= 5 else "low")
            flagged.append({
                "word": word,
                "severity": severity_label,
                "count": count,
                "location": location,
                "points": points,
            })

    # Check patterns
    for pattern, severity, name in SPAM_PATTERNS:
        subject_matches = len(re.findall(pattern, subject))
        body_matches = len(re.findall(pattern, body_text))
        total_matches = subject_matches + body_matches
        if total_matches > 0:
            points = severity * total_matches
            total_points += points
            flagged.append({
                "word": f"[pattern: {name}]",
                "severity": "medium" if severity >= 5 else "low",
                "count": total_matches,
                "location": "subject" if subject_matches and not body_matches else (
                    "body" if body_matches and not subject_matches else "both"),
                "points": points,
            })

    # Normalize to 0-100 scale (cap at 100)
    score = min(100, total_points)

    # Grade
    if score <= 10:
        grade = "clean"
    elif score <= 30:
        grade = "low_risk"
    elif score <= 60:
        grade = "medium_risk"
    elif score <= 80:
        grade = "high_risk"
    else:
        grade = "spam"

    # Sort by points descending
    flagged.sort(key=lambda x: x["points"], reverse=True)

    return {
        "score": score,
        "grade": grade,
        "flagged_words": flagged[:20],  # Top 20
        "total_triggers": len(flagged),
    }
