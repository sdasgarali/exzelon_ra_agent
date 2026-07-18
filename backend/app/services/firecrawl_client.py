"""Minimal Firecrawl scrape client.

Firecrawl renders JavaScript and bypasses common anti-bot blocks, which plain
``httpx`` cannot — required to read applicant counts off LinkedIn/Indeed job
pages. Deliberately tiny and best-effort: any failure returns ``None`` so the
caller (a recall-preserving enrichment step) simply keeps the lead.
"""
from __future__ import annotations

from typing import Optional

import httpx
import structlog

logger = structlog.get_logger()

_SCRAPE_URL = "https://api.firecrawl.dev/v1/scrape"


def scrape_markdown(url: str, api_key: str, timeout: int = 20) -> Optional[str]:
    """Return the page's main content as markdown, or ``None`` on any failure.

    Never raises — network errors, non-200s, quota errors, and malformed
    responses all resolve to ``None`` (best-effort enrichment).
    """
    if not url or not api_key:
        return None
    try:
        resp = httpx.post(
            _SCRAPE_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"url": url, "formats": ["markdown"], "onlyMainContent": True},
            timeout=timeout,
        )
        if resp.status_code != 200:
            logger.warning("Firecrawl scrape non-200", url=url, status=resp.status_code)
            return None
        data = resp.json()
        # v1 shape: {"success": true, "data": {"markdown": "..."}}
        md = (data.get("data") or {}).get("markdown")
        return md if isinstance(md, str) and md.strip() else None
    except (httpx.HTTPError, ValueError, KeyError) as e:
        logger.warning("Firecrawl scrape failed", url=url, error=str(e))
        return None
