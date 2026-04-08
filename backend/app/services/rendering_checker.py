"""Email rendering checker — Gap 11 fix.

Scans email HTML for patterns that cause rendering issues across email
clients (Outlook, Gmail, Apple Mail, mobile). Returns warnings so users
can fix emails before sending.

Why: Poorly rendered emails get lower engagement and higher spam reports.
Outlook uses Word rendering engine which doesn't support many CSS features.
Gmail strips <style> tags. Mobile clients have narrow viewports.
"""
import re
from typing import Dict, Any, List
from html.parser import HTMLParser

import structlog

logger = structlog.get_logger()


class _HTMLTagCounter(HTMLParser):
    """Count tags and attributes in HTML for rendering analysis."""

    def __init__(self):
        super().__init__()
        self.tags: Dict[str, int] = {}
        self.attrs: Dict[str, int] = {}
        self.inline_styles = 0
        self.external_css = False
        self.images = 0
        self.links = 0
        self.total_chars = 0
        self.has_viewport_meta = False
        self.font_tags = 0
        self.table_layouts = 0
        self.div_nesting = 0
        self.max_div_depth = 0
        self._current_div_depth = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        self.tags[tag] = self.tags.get(tag, 0) + 1
        for name, value in attrs:
            name = name.lower()
            self.attrs[name] = self.attrs.get(name, 0) + 1
            if name == "style":
                self.inline_styles += 1
        if tag == "img":
            self.images += 1
        if tag == "a":
            self.links += 1
        if tag == "link":
            for name, value in attrs:
                if name.lower() == "rel" and value and "stylesheet" in value.lower():
                    self.external_css = True
        if tag == "font":
            self.font_tags += 1
        if tag == "table":
            self.table_layouts += 1
        if tag == "div":
            self._current_div_depth += 1
            if self._current_div_depth > self.max_div_depth:
                self.max_div_depth = self._current_div_depth
        if tag == "meta":
            for name, value in attrs:
                if name.lower() == "name" and value and value.lower() == "viewport":
                    self.has_viewport_meta = True

    def handle_endtag(self, tag):
        if tag.lower() == "div":
            self._current_div_depth = max(0, self._current_div_depth - 1)

    def handle_data(self, data):
        self.total_chars += len(data.strip())


# CSS properties that Outlook doesn't support (Word rendering engine)
OUTLOOK_UNSUPPORTED_CSS = [
    "background-image",
    "border-radius",
    "box-shadow",
    "text-shadow",
    "opacity",
    "position:\\s*(?:absolute|fixed|sticky)",
    "display:\\s*(?:flex|grid|inline-flex|inline-grid)",
    "float",
    "max-width",
    "calc\\(",
    "rgba\\(",
    "hsla?\\(",
    "gradient",
    "animation",
    "transition",
    "transform",
    "@media",
]

# Patterns that Gmail strips
GMAIL_STRIPPED = [
    "<style[^>]*>",           # Gmail strips <style> blocks in non-AMP
    "class=",                  # Classes only work with inline styles in Gmail
    "position:\\s*absolute",
]


def check_rendering(body_html: str) -> Dict[str, Any]:
    """Analyze email HTML for rendering issues across email clients.

    Returns:
        {
            "warnings": [{"severity": "high"|"medium"|"low", "message": str, "client": str}],
            "stats": {"images": int, "links": int, "total_chars": int, ...},
            "score": int (0-100, 100 = no issues),
        }
    """
    if not body_html:
        return {"warnings": [], "stats": {}, "score": 100}

    warnings: List[Dict[str, str]] = []
    parser = _HTMLTagCounter()
    try:
        parser.feed(body_html)
    except Exception:
        warnings.append({
            "severity": "high",
            "message": "HTML parsing failed — email may have malformed tags",
            "client": "all",
        })
        return {"warnings": warnings, "stats": {}, "score": 30}

    # ===== Outlook checks =====
    for css_prop in OUTLOOK_UNSUPPORTED_CSS:
        if re.search(css_prop, body_html, re.I):
            prop_name = re.sub(r"\\[s(].*", "", css_prop).replace("\\", "")
            warnings.append({
                "severity": "medium",
                "message": f"CSS '{prop_name}' not supported in Outlook (Word rendering engine)",
                "client": "outlook",
            })

    # ===== Gmail checks =====
    if "<style" in body_html.lower():
        warnings.append({
            "severity": "medium",
            "message": "<style> blocks are stripped by Gmail — use inline styles instead",
            "client": "gmail",
        })

    if parser.external_css:
        warnings.append({
            "severity": "high",
            "message": "External CSS stylesheets are not loaded by any email client",
            "client": "all",
        })

    # ===== General deliverability checks =====
    if parser.images > 3:
        warnings.append({
            "severity": "medium",
            "message": f"Too many images ({parser.images}) — image-heavy emails trigger spam filters",
            "client": "all",
        })

    if parser.images > 0 and parser.total_chars < 50:
        warnings.append({
            "severity": "high",
            "message": "Image-only email with very little text — high spam risk",
            "client": "all",
        })

    text_to_html_ratio = parser.total_chars / max(len(body_html), 1)
    if text_to_html_ratio < 0.1 and len(body_html) > 500:
        warnings.append({
            "severity": "medium",
            "message": f"Low text-to-HTML ratio ({text_to_html_ratio:.1%}) — keep HTML simple for cold email",
            "client": "all",
        })

    if parser.links > 3:
        warnings.append({
            "severity": "medium",
            "message": f"Too many links ({parser.links}) — more than 2-3 links raises spam suspicion",
            "client": "all",
        })

    # ===== Mobile checks =====
    if parser.max_div_depth > 5:
        warnings.append({
            "severity": "low",
            "message": f"Deeply nested divs (depth {parser.max_div_depth}) — may render poorly on mobile",
            "client": "mobile",
        })

    if parser.table_layouts > 2:
        warnings.append({
            "severity": "low",
            "message": f"Multiple nested tables ({parser.table_layouts}) — can break on mobile clients",
            "client": "mobile",
        })

    # ===== Cold email best practices =====
    has_html_tags = bool(re.search(r"<(?:div|table|td|span|p)\b", body_html, re.I))
    if has_html_tags and parser.inline_styles == 0 and "<style" not in body_html.lower():
        warnings.append({
            "severity": "low",
            "message": "HTML tags without inline styles — formatting may be lost in Gmail",
            "client": "gmail",
        })

    if len(body_html) > 100000:
        warnings.append({
            "severity": "high",
            "message": f"Email body very large ({len(body_html):,} chars) — Gmail clips emails > 102KB",
            "client": "gmail",
        })

    if parser.font_tags > 0:
        warnings.append({
            "severity": "low",
            "message": f"Deprecated <font> tags found ({parser.font_tags}) — use CSS instead",
            "client": "all",
        })

    # ===== Plain text cold email recommendation =====
    complex_html_tags = sum(
        parser.tags.get(t, 0)
        for t in ("table", "div", "span", "td", "tr", "img", "style")
    )
    if complex_html_tags > 10:
        warnings.append({
            "severity": "medium",
            "message": "Heavy HTML formatting detected — plain-text-style emails get higher deliverability for cold outreach",
            "client": "all",
        })

    # Calculate score (100 = no issues)
    penalty = 0
    for w in warnings:
        if w["severity"] == "high":
            penalty += 15
        elif w["severity"] == "medium":
            penalty += 8
        else:
            penalty += 3
    score = max(0, 100 - penalty)

    return {
        "warnings": warnings,
        "stats": {
            "images": parser.images,
            "links": parser.links,
            "total_chars": parser.total_chars,
            "inline_styles": parser.inline_styles,
            "table_layouts": parser.table_layouts,
            "max_div_depth": parser.max_div_depth,
            "html_length": len(body_html),
        },
        "score": score,
    }
