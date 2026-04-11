"""Template Scorecard — multi-dimension scoring, fix suggestions, and one-click apply.

Computes 10 quality dimensions for email template content, generates actionable
fix suggestions, and applies auto-fixable fixes with before/after score tracking.
No DB tables required — all computations are stateless and on-demand.
"""
import math
import re
from typing import Any, Dict, List, Optional

from app.services.spam_checker import check_spam_score, strip_html, SPAM_WORDS
from app.services.rendering_checker import check_rendering
from app.services.email_humanizer import compute_burstiness_score
from app.services.content_fingerprint import compute_entropy_score


# ─── Constants ────────────────────────────────────────────────────────────────

SPAM_REPLACEMENTS: Dict[str, str] = {
    "free": "complimentary",
    "guaranteed": "reliable",
    "act now": "when you're ready",
    "limited time": "currently available",
    "buy now": "get started",
    "discount": "offer",
    "click here": "learn more",
    "congratulations": "great news",
    "winner": "selected",
    "no obligation": "no commitment",
    "risk-free": "with confidence",
    "urgent": "timely",
    "expires": "available until",
    "order now": "get started today",
    "sign up free": "create an account",
    "double your": "grow your",
    "earn money": "generate revenue",
    "make money": "build income",
    "call now": "reach out",
    "don't miss": "consider",
    "once in a lifetime": "unique",
    "while supplies last": "while available",
    "offer expires": "available through",
    "immediately": "promptly",
    "exclusive deal": "special opportunity",
    "best price": "competitive pricing",
    "lowest price": "fair pricing",
    "save big": "save",
    "incredible deal": "strong opportunity",
    "great offer": "opportunity",
    "for free": "at no cost",
}

CTA_PHRASES = [
    "schedule a call", "book a time", "book a meeting", "reply",
    "click here", "learn more", "let me know", "interested?",
    "get started", "sign up", "try it", "start today",
    "reach out", "contact us", "set up a time", "grab a spot",
    "what does your calendar look like", "would a quick call work",
    "can i send", "want to see", "happy to chat", "want to chat",
    "let's connect", "15 minutes", "10-minute call", "brief call",
]

DIMENSION_WEIGHTS = {
    "spam_risk": 0.15,
    "rendering": 0.10,
    "humanization": 0.10,
    "personalization": 0.15,
    "subject_quality": 0.10,
    "clarity": 0.10,
    "cta_quality": 0.10,
    "compliance": 0.05,
    "content_entropy": 0.10,
    "word_count": 0.05,
}

DIMENSION_LABELS = {
    "spam_risk": "Spam Risk",
    "rendering": "Rendering",
    "humanization": "Humanization",
    "personalization": "Personalization",
    "subject_quality": "Subject Quality",
    "clarity": "Clarity",
    "cta_quality": "CTA Quality",
    "compliance": "Compliance",
    "content_entropy": "Content Entropy",
    "word_count": "Word Count",
}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _grade(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B+"
    if score >= 70:
        return "B"
    if score >= 60:
        return "C+"
    if score >= 50:
        return "C"
    if score >= 40:
        return "D"
    return "F"


def _count_syllables(word: str) -> int:
    """Rough syllable count for Flesch readability."""
    word = word.lower().strip(".,!?;:'\"")
    if not word:
        return 0
    count = 0
    vowels = "aeiouy"
    prev_vowel = False
    for ch in word:
        is_vowel = ch in vowels
        if is_vowel and not prev_vowel:
            count += 1
        prev_vowel = is_vowel
    # Silent e
    if word.endswith("e") and count > 1:
        count -= 1
    return max(1, count)


# ─── Individual Dimension Scorers ─────────────────────────────────────────────

def _score_spam_risk(subject: str, body_html: str) -> Dict[str, Any]:
    result = check_spam_score(subject, body_html)
    score = max(0, 100 - result["score"])
    issues: List[Dict[str, str]] = []
    for fw in result.get("flagged_words", [])[:10]:
        sev = fw.get("severity", "medium")
        issues.append({"severity": sev, "message": f"Spam trigger: \"{fw['word']}\" ({fw.get('location', 'body')}, {fw.get('points', 0)}pts)"})
    return {"score": score, "grade": _grade(score), "weight": DIMENSION_WEIGHTS["spam_risk"], "issues": issues}


def _score_rendering(body_html: str) -> Dict[str, Any]:
    if not body_html.strip():
        return {"score": 50, "grade": _grade(50), "weight": DIMENSION_WEIGHTS["rendering"], "issues": [{"severity": "medium", "message": "No HTML body provided"}]}
    result = check_rendering(body_html)
    score = result.get("score", 100)
    issues = [{"severity": w["severity"], "message": w["message"]} for w in result.get("warnings", [])[:8]]
    return {"score": score, "grade": _grade(score), "weight": DIMENSION_WEIGHTS["rendering"], "issues": issues}


def _score_humanization(body_html: str) -> Dict[str, Any]:
    text = strip_html(body_html).strip()
    if not text or len(text.split()) < 5:
        return {"score": 50, "grade": _grade(50), "weight": DIMENSION_WEIGHTS["humanization"], "issues": [{"severity": "low", "message": "Too short to assess humanization"}]}
    burstiness = compute_burstiness_score(text)
    # Map 0.0-1.0 burstiness to 0-100 score. Human range is 0.5-0.8.
    if burstiness >= 0.6:
        score = 90 + int((burstiness - 0.6) * 25)
    elif burstiness >= 0.4:
        score = 60 + int((burstiness - 0.4) * 150)
    elif burstiness >= 0.2:
        score = 30 + int((burstiness - 0.2) * 150)
    else:
        score = int(burstiness * 150)
    score = max(0, min(100, score))
    issues: List[Dict[str, str]] = []
    if burstiness < 0.4:
        issues.append({"severity": "medium", "message": f"Low burstiness ({burstiness:.2f}) — may seem AI-generated. Vary sentence lengths."})
    return {"score": score, "grade": _grade(score), "weight": DIMENSION_WEIGHTS["humanization"], "issues": issues}


def _score_personalization(subject: str, body_html: str) -> Dict[str, Any]:
    combined = f"{subject} {body_html}"
    vars_found = set(re.findall(r'\{\{(\w+)\}\}', combined))
    count = len(vars_found)
    issues: List[Dict[str, str]] = []

    if count == 0:
        score = 20
        issues.append({"severity": "high", "message": "No personalization variables. Add {{contact_first_name}} or {{company_name}}."})
    elif count == 1:
        score = 50
        issues.append({"severity": "medium", "message": "Only 1 variable used. Consider adding more personalization."})
    elif count == 2:
        score = 70
    else:
        score = 90

    # Bonus for key variables
    key_vars = {"contact_first_name", "company_name", "job_title"}
    found_key = vars_found & key_vars
    if found_key and count >= 2:
        score = min(100, score + 5 * len(found_key))
    elif not found_key and count > 0:
        issues.append({"severity": "low", "message": "Missing key variables: {{contact_first_name}}, {{company_name}}, or {{job_title}}."})

    return {"score": min(100, score), "grade": _grade(min(100, score)), "weight": DIMENSION_WEIGHTS["personalization"], "issues": issues}


def _score_subject_quality(subject: str) -> Dict[str, Any]:
    issues: List[Dict[str, str]] = []
    score = 100

    if not subject.strip():
        return {"score": 0, "grade": "F", "weight": DIMENSION_WEIGHTS["subject_quality"], "issues": [{"severity": "high", "message": "Subject line is empty."}]}

    length = len(subject)

    # Length check (30-60 chars optimal)
    if length < 10:
        score -= 40
        issues.append({"severity": "high", "message": f"Subject too short ({length} chars). Aim for 30-60 characters."})
    elif length < 30:
        score -= 15
        issues.append({"severity": "medium", "message": f"Subject is short ({length} chars). 30-60 characters is optimal."})
    elif length > 80:
        score -= 30
        issues.append({"severity": "high", "message": f"Subject too long ({length} chars). May be truncated in inbox."})
    elif length > 60:
        score -= 10
        issues.append({"severity": "low", "message": f"Subject is slightly long ({length} chars). 30-60 is ideal."})

    # ALL CAPS words
    words = subject.split()
    caps_words = [w for w in words if w.isupper() and len(w) > 2 and not w.startswith("{{")]
    if caps_words:
        score -= 15
        issues.append({"severity": "medium", "message": f"ALL CAPS words detected: {', '.join(caps_words[:3])}. Avoid shouting."})

    # Excessive punctuation
    if subject.count("!") > 1:
        score -= 10
        issues.append({"severity": "medium", "message": "Multiple exclamation marks in subject."})
    if subject.count("?") > 2:
        score -= 5
        issues.append({"severity": "low", "message": "Multiple question marks in subject."})

    # Spam words in subject
    subject_lower = subject.lower()
    for word, severity in SPAM_WORDS.items():
        if severity >= 10 and re.search(r'\b' + re.escape(word) + r'\b', subject_lower):
            score -= 15
            issues.append({"severity": "high", "message": f"Spam trigger word in subject: \"{word}\"."})
            break  # Only flag first

    # Personalization in subject = bonus
    if "{{" in subject:
        score = min(100, score + 5)

    return {"score": max(0, score), "grade": _grade(max(0, score)), "weight": DIMENSION_WEIGHTS["subject_quality"], "issues": issues}


def _score_clarity(body_html: str) -> Dict[str, Any]:
    text = strip_html(body_html).strip()
    if not text or len(text.split()) < 10:
        return {"score": 50, "grade": _grade(50), "weight": DIMENSION_WEIGHTS["clarity"], "issues": [{"severity": "low", "message": "Too short for readability assessment."}]}

    words = text.split()
    total_words = len(words)
    sentences = [s.strip() for s in re.split(r'[.!?]+', text) if s.strip()]
    total_sentences = max(1, len(sentences))
    total_syllables = sum(_count_syllables(w) for w in words)

    # Flesch Reading Ease
    fre = 206.835 - 1.015 * (total_words / total_sentences) - 84.6 * (total_syllables / total_words)
    fre = max(0, min(100, fre))

    # Map Flesch score to our 0-100 scale
    # Cold email sweet spot: grade 6-8 (Flesch 60-80)
    issues: List[Dict[str, str]] = []
    if fre >= 60:
        score = min(100, int(fre))
    elif fre >= 40:
        score = int(40 + (fre - 40) * 1.5)
        issues.append({"severity": "low", "message": f"Reading ease {fre:.0f} — slightly complex for cold email."})
    elif fre >= 20:
        score = int(20 + (fre - 20) * 1.0)
        issues.append({"severity": "medium", "message": f"Reading ease {fre:.0f} — too complex. Simplify sentences."})
    else:
        score = max(0, int(fre))
        issues.append({"severity": "high", "message": f"Reading ease {fre:.0f} — very hard to read. Use shorter sentences and simpler words."})

    # Check for very long sentences
    long_sentences = [s for s in sentences if len(s.split()) > 30]
    if long_sentences:
        score = max(0, score - 10)
        issues.append({"severity": "medium", "message": f"{len(long_sentences)} sentence(s) over 30 words. Break them up."})

    return {"score": max(0, min(100, score)), "grade": _grade(max(0, min(100, score))), "weight": DIMENSION_WEIGHTS["clarity"], "issues": issues}


def _score_cta_quality(body_html: str) -> Dict[str, Any]:
    text = strip_html(body_html).lower().strip()
    if not text:
        return {"score": 0, "grade": "F", "weight": DIMENSION_WEIGHTS["cta_quality"], "issues": [{"severity": "high", "message": "No content to assess CTA."}]}

    issues: List[Dict[str, str]] = []
    score = 0
    found_ctas: List[str] = []

    for phrase in CTA_PHRASES:
        if phrase in text:
            found_ctas.append(phrase)

    # Has CTA = 40 pts
    if found_ctas:
        score += 40
    else:
        issues.append({"severity": "high", "message": "No call-to-action detected. Add a clear CTA."})
        return {"score": 0, "grade": "F", "weight": DIMENSION_WEIGHTS["cta_quality"], "issues": issues}

    # CTA in last 2 sentences = 20 pts
    sentences = [s.strip() for s in re.split(r'[.!?]+', text) if s.strip()]
    last_two = " ".join(sentences[-2:]) if len(sentences) >= 2 else text
    cta_in_end = any(phrase in last_two for phrase in CTA_PHRASES)
    if cta_in_end:
        score += 20
    else:
        issues.append({"severity": "low", "message": "CTA not in final sentences. Move it closer to the end."})

    # Single clear CTA vs multiple = 20 pts
    if len(found_ctas) == 1:
        score += 20
    elif len(found_ctas) <= 3:
        score += 15
        issues.append({"severity": "low", "message": f"{len(found_ctas)} CTAs found. One clear CTA is usually more effective."})
    else:
        score += 5
        issues.append({"severity": "medium", "message": f"{len(found_ctas)} CTAs found. Too many — pick one primary CTA."})

    # CTA specificity = 20 pts
    specific_ctas = ["schedule a call", "book a time", "book a meeting", "set up a time",
                     "15 minutes", "10-minute call", "grab a spot", "what does your calendar"]
    if any(c in text for c in specific_ctas):
        score += 20
    elif any(c in text for c in ["reply", "let me know", "interested?"]):
        score += 15
    else:
        score += 10
        issues.append({"severity": "low", "message": "CTA could be more specific (e.g., 'book a 15-min call')."})

    return {"score": min(100, score), "grade": _grade(min(100, score)), "weight": DIMENSION_WEIGHTS["cta_quality"], "issues": issues}


def _score_compliance(subject: str, body_html: str) -> Dict[str, Any]:
    text_lower = strip_html(body_html).lower()
    html_lower = body_html.lower()
    issues: List[Dict[str, str]] = []
    score = 0

    # Unsubscribe link/text (40 pts)
    has_unsub = ("unsubscribe" in text_lower or "{{unsubscribe_link}}" in html_lower
                 or "opt out" in text_lower or "opt-out" in text_lower)
    if has_unsub:
        score += 40
    else:
        issues.append({"severity": "high", "message": "No unsubscribe link. Add {{unsubscribe_link}} for CAN-SPAM compliance."})

    # Company/sender identification (20 pts)
    has_company = ("{{company_name}}" in body_html or "{{sender_first_name}}" in body_html
                   or "{{signature}}" in body_html)
    if has_company:
        score += 20
    else:
        issues.append({"severity": "medium", "message": "No sender identification. Include {{signature}} or company info."})

    # Physical address or company name in footer (20 pts)
    # Check for common patterns
    has_address = bool(re.search(r'\d+\s+\w+\s+(st|street|ave|avenue|blvd|road|rd|dr|drive|ln|lane)', text_lower))
    has_footer_company = "{{signature}}" in html_lower
    if has_address or has_footer_company:
        score += 20
    else:
        issues.append({"severity": "low", "message": "Consider adding a physical address or {{signature}} for trust."})

    # Non-deceptive subject (20 pts)
    deceptive_patterns = [r'^re:\s', r'^fw:\s', r'^fwd:\s']
    subject_lower = subject.lower()
    is_deceptive = any(re.match(p, subject_lower) for p in deceptive_patterns)
    if not is_deceptive:
        score += 20
    else:
        issues.append({"severity": "high", "message": "Subject uses fake RE:/FW: prefix — deceptive per CAN-SPAM."})

    return {"score": min(100, score), "grade": _grade(min(100, score)), "weight": DIMENSION_WEIGHTS["compliance"], "issues": issues}


def _score_content_entropy(subject: str, body_html: str) -> Dict[str, Any]:
    body_text = strip_html(body_html)
    if not body_text.strip():
        return {"score": 30, "grade": _grade(30), "weight": DIMENSION_WEIGHTS["content_entropy"], "issues": [{"severity": "medium", "message": "No content for entropy analysis."}]}

    result = compute_entropy_score(subject, body_text)
    score = result.get("score", 50)
    issues: List[Dict[str, str]] = []

    if score < 40:
        issues.append({"severity": "medium", "message": f"Low content variability (entropy score {score}). Add more unique phrasing."})
    if not result.get("has_personalization"):
        issues.append({"severity": "low", "message": "No template variables detected for entropy boost."})

    return {"score": score, "grade": _grade(score), "weight": DIMENSION_WEIGHTS["content_entropy"], "issues": issues}


def _score_word_count(body_html: str) -> Dict[str, Any]:
    text = strip_html(body_html).strip()
    wc = len(text.split()) if text else 0
    issues: List[Dict[str, str]] = []

    if wc < 20:
        score = 20
        issues.append({"severity": "high", "message": f"Only {wc} words. Cold emails should be 50-200 words."})
    elif wc < 30:
        score = 30
        issues.append({"severity": "medium", "message": f"{wc} words — very short. Aim for 50-200 words."})
    elif wc < 50:
        score = 60
        issues.append({"severity": "low", "message": f"{wc} words — slightly short. 50-200 is ideal."})
    elif wc <= 200:
        score = 100
    elif wc <= 300:
        score = 70
        issues.append({"severity": "low", "message": f"{wc} words — slightly long. Keep under 200 for best engagement."})
    else:
        score = 40
        issues.append({"severity": "medium", "message": f"{wc} words — too long. Trim to under 200 for cold email."})

    return {"score": score, "grade": _grade(score), "weight": DIMENSION_WEIGHTS["word_count"], "issues": issues}


# ─── Main Scoring Function ───────────────────────────────────────────────────

def score_template(subject: str, body_html: str, body_text: str = "") -> Dict[str, Any]:
    """Compute 10-dimension scorecard for template content.

    Returns overall score, grade, recommendation, and per-dimension breakdowns.
    """
    dimensions = {
        "spam_risk": _score_spam_risk(subject, body_html),
        "rendering": _score_rendering(body_html),
        "humanization": _score_humanization(body_html),
        "personalization": _score_personalization(subject, body_html),
        "subject_quality": _score_subject_quality(subject),
        "clarity": _score_clarity(body_html),
        "cta_quality": _score_cta_quality(body_html),
        "compliance": _score_compliance(subject, body_html),
        "content_entropy": _score_content_entropy(subject, body_html),
        "word_count": _score_word_count(body_html),
    }

    # Weighted sum
    overall = sum(d["score"] * d["weight"] for d in dimensions.values())
    overall = max(0, min(100, round(overall)))

    # Count issues
    total_issues = sum(len(d["issues"]) for d in dimensions.values())
    critical_issues = sum(
        1 for d in dimensions.values()
        for issue in d["issues"]
        if issue["severity"] == "high"
    )

    # Recommendation
    if overall >= 70:
        recommendation = "SEND"
        recommendation_label = "Ready to send"
    elif overall >= 40:
        recommendation = "REVIEW"
        recommendation_label = "Review suggested improvements"
    else:
        recommendation = "DO_NOT_SEND"
        recommendation_label = "Significant issues found"

    return {
        "overall_score": overall,
        "overall_grade": _grade(overall),
        "recommendation": recommendation,
        "recommendation_label": recommendation_label,
        "dimensions": dimensions,
        "total_issues": total_issues,
        "critical_issues": critical_issues,
    }


# ─── Fix Suggestions ─────────────────────────────────────────────────────────

def get_fixes(subject: str, body_html: str, body_text: str = "") -> Dict[str, Any]:
    """Generate actionable fix suggestions from template content analysis."""
    fixes: List[Dict[str, Any]] = []
    fix_id = 0

    # 1) Spam word replacements
    spam_result = check_spam_score(subject, body_html)
    for fw in spam_result.get("flagged_words", []):
        word = fw.get("word", "")
        if word.startswith("["):  # Skip pattern-based findings
            continue
        word_lower = word.lower()
        replacement = SPAM_REPLACEMENTS.get(word_lower)
        if replacement:
            fix_id += 1
            location = fw.get("location", "body")
            if location == "both":
                location = "body"
            fixes.append({
                "id": f"fix_{fix_id}",
                "dimension": "spam_risk",
                "severity": fw.get("severity", "medium"),
                "category": "spam_words",
                "message": f"Replace \"{word}\" with \"{replacement}\"",
                "original": word,
                "replacement": replacement,
                "location": location,
                "auto_fixable": True,
            })

    # 2) Subject length
    subject_len = len(subject)
    if subject_len > 80:
        fix_id += 1
        fixes.append({
            "id": f"fix_{fix_id}",
            "dimension": "subject_quality",
            "severity": "medium",
            "category": "subject_length",
            "message": f"Subject is {subject_len} chars. Trim to under 60 for best inbox display.",
            "original": subject,
            "replacement": subject[:57] + "..." if len(subject) > 60 else subject,
            "location": "subject",
            "auto_fixable": True,
        })
    elif subject_len < 15 and subject_len > 0:
        fix_id += 1
        fixes.append({
            "id": f"fix_{fix_id}",
            "dimension": "subject_quality",
            "severity": "low",
            "category": "subject_length",
            "message": f"Subject is only {subject_len} chars. Add more detail for better open rates.",
            "original": "",
            "replacement": "",
            "location": "subject",
            "auto_fixable": False,
        })

    # 3) Missing personalization
    combined = f"{subject} {body_html}"
    vars_found = set(re.findall(r'\{\{(\w+)\}\}', combined))
    if "contact_first_name" not in vars_found:
        fix_id += 1
        fixes.append({
            "id": f"fix_{fix_id}",
            "dimension": "personalization",
            "severity": "medium",
            "category": "missing_personalization",
            "message": "Add {{contact_first_name}} for a personal greeting.",
            "original": "",
            "replacement": "{{contact_first_name}}",
            "location": "body",
            "auto_fixable": False,
        })
    if "company_name" not in vars_found:
        fix_id += 1
        fixes.append({
            "id": f"fix_{fix_id}",
            "dimension": "personalization",
            "severity": "low",
            "category": "missing_personalization",
            "message": "Add {{company_name}} to show you researched the recipient.",
            "original": "",
            "replacement": "{{company_name}}",
            "location": "body",
            "auto_fixable": False,
        })

    # 4) Missing CTA
    body_lower = strip_html(body_html).lower()
    has_cta = any(phrase in body_lower for phrase in CTA_PHRASES)
    if not has_cta and len(body_lower.split()) > 10:
        fix_id += 1
        fixes.append({
            "id": f"fix_{fix_id}",
            "dimension": "cta_quality",
            "severity": "high",
            "category": "missing_cta",
            "message": "No call-to-action found. Add a CTA like 'Would a quick call work this week?'",
            "original": "",
            "replacement": "",
            "location": "body",
            "auto_fixable": False,
        })

    # 5) Word count
    wc = len(strip_html(body_html).split()) if body_html else 0
    if wc > 300:
        fix_id += 1
        fixes.append({
            "id": f"fix_{fix_id}",
            "dimension": "word_count",
            "severity": "medium",
            "category": "word_count",
            "message": f"Email is {wc} words. Trim to under 200 for best cold email engagement.",
            "original": "",
            "replacement": "",
            "location": "body",
            "auto_fixable": False,
        })
    elif wc < 30 and wc > 0:
        fix_id += 1
        fixes.append({
            "id": f"fix_{fix_id}",
            "dimension": "word_count",
            "severity": "low",
            "category": "word_count",
            "message": f"Email is only {wc} words. Add more context for credibility.",
            "original": "",
            "replacement": "",
            "location": "body",
            "auto_fixable": False,
        })

    # 6) Compliance — missing unsubscribe
    html_lower = body_html.lower()
    has_unsub = ("unsubscribe" in body_lower or "{{unsubscribe_link}}" in html_lower
                 or "opt out" in body_lower or "opt-out" in body_lower)
    if not has_unsub:
        fix_id += 1
        fixes.append({
            "id": f"fix_{fix_id}",
            "dimension": "compliance",
            "severity": "high",
            "category": "compliance",
            "message": "Add unsubscribe link for CAN-SPAM compliance.",
            "original": "",
            "replacement": '<p style="font-size:11px;color:#999;">{{unsubscribe_link}}</p>',
            "location": "body",
            "auto_fixable": True,
        })

    # 7) Readability — long sentences
    text = strip_html(body_html)
    sentences = [s.strip() for s in re.split(r'[.!?]+', text) if s.strip()]
    long_sentences = [s for s in sentences if len(s.split()) > 30]
    if long_sentences:
        fix_id += 1
        fixes.append({
            "id": f"fix_{fix_id}",
            "dimension": "clarity",
            "severity": "medium",
            "category": "readability",
            "message": f"{len(long_sentences)} sentence(s) over 30 words. Consider breaking them up.",
            "original": "",
            "replacement": "",
            "location": "body",
            "auto_fixable": False,
        })

    # Sort: high severity first, then auto-fixable first
    severity_order = {"high": 0, "medium": 1, "low": 2}
    fixes.sort(key=lambda f: (severity_order.get(f["severity"], 2), 0 if f["auto_fixable"] else 1))

    auto_fixable_count = sum(1 for f in fixes if f["auto_fixable"])

    return {
        "fixes": fixes,
        "fix_count": len(fixes),
        "auto_fixable_count": auto_fixable_count,
    }


# ─── Apply Fixes ─────────────────────────────────────────────────────────────

def apply_fixes(
    subject: str,
    body_html: str,
    body_text: str,
    fix_ids: List[str],
) -> Dict[str, Any]:
    """Apply selected auto-fixable fixes and return updated content + score delta."""
    # Get before score
    before_result = score_template(subject, body_html, body_text)
    before_score = before_result["overall_score"]

    # Get the fixes
    fixes_result = get_fixes(subject, body_html, body_text)
    all_fixes = {f["id"]: f for f in fixes_result["fixes"]}

    applied: List[str] = []
    skipped: List[str] = []

    updated_subject = subject
    updated_body_html = body_html
    updated_body_text = body_text

    for fid in fix_ids:
        fix = all_fixes.get(fid)
        if not fix:
            skipped.append(fid)
            continue
        if not fix["auto_fixable"]:
            skipped.append(fid)
            continue

        if fix["category"] == "spam_words":
            original = fix["original"]
            replacement = fix["replacement"]
            # Case-insensitive replacement in subject and body
            pattern = re.compile(re.escape(original), re.IGNORECASE)
            updated_subject = pattern.sub(replacement, updated_subject)
            updated_body_html = pattern.sub(replacement, updated_body_html)
            if updated_body_text:
                updated_body_text = pattern.sub(replacement, updated_body_text)
            applied.append(fid)

        elif fix["category"] == "subject_length":
            if fix["replacement"] and fix["location"] == "subject":
                updated_subject = fix["replacement"]
                applied.append(fid)
            else:
                skipped.append(fid)

        elif fix["category"] == "compliance":
            # Append unsubscribe link to body
            if fix["replacement"] and "{{unsubscribe_link}}" not in updated_body_html.lower():
                updated_body_html = updated_body_html.rstrip() + "\n" + fix["replacement"]
                applied.append(fid)
            else:
                skipped.append(fid)

        else:
            skipped.append(fid)

    # Get after score
    after_result = score_template(updated_subject, updated_body_html, updated_body_text)
    after_score = after_result["overall_score"]

    return {
        "subject": updated_subject,
        "body_html": updated_body_html,
        "body_text": updated_body_text,
        "applied_fixes": applied,
        "skipped_fixes": skipped,
        "before_score": before_score,
        "after_score": after_score,
        "delta": after_score - before_score,
    }
