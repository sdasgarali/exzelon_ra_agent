"""News Signal Adapter — monitors Google News RSS for LOB-specific trigger events.

Uses Google News RSS feeds (free, no API key, no rate limits) to detect
business events that signal buying intent: practice expansions, funding
announcements, rebranding, digital transformation initiatives, etc.

Zero cost, zero dependencies beyond stdlib.
"""
import re
import structlog
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import List, Dict, Any, Optional
from urllib.request import urlopen, Request
from urllib.parse import quote_plus
from urllib.error import URLError

from app.services.adapters.base import LeadSourceAdapter

logger = structlog.get_logger()

# LOB-specific news queries and their signal names
NEWS_QUERIES: Dict[str, List[Dict[str, str]]] = {
    "rcm": [
        {"query": "healthcare practice expansion", "signal": "practice_expansion"},
        {"query": "new medical office opening", "signal": "new_practice"},
        {"query": "HIPAA audit healthcare", "signal": "compliance_issue"},
        {"query": "medical practice acquisition", "signal": "practice_acquisition"},
    ],
    "software_dev": [
        {"query": "digital transformation initiative", "signal": "digital_transformation"},
        {"query": "legacy system modernization", "signal": "legacy_modernization"},
        {"query": "startup series funding round", "signal": "startup_funding"},
        {"query": "company technology migration", "signal": "tech_migration"},
    ],
    "ai_services": [
        {"query": "company AI initiative launch", "signal": "ai_initiative"},
        {"query": "enterprise AI adoption strategy", "signal": "ai_adoption"},
        {"query": "company automation strategy", "signal": "automation_strategy"},
        {"query": "AI transformation enterprise", "signal": "ai_transformation"},
    ],
    "digital_marketing": [
        {"query": "company rebranding announcement", "signal": "rebranding"},
        {"query": "new website launch company", "signal": "website_launch"},
        {"query": "brand refresh announcement", "signal": "brand_refresh"},
        {"query": "company digital presence expansion", "signal": "digital_expansion"},
    ],
}

# Google News RSS base URL
GOOGLE_NEWS_RSS_URL = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"


def _extract_company_name(title: str) -> Optional[str]:
    """Extract company name from news headline using heuristics.

    Patterns matched:
    - "Company Name announces..."
    - "Company Name launches..."
    - "Company Name to expand..."
    - Quoted names: "Company Name" in headline
    """
    if not title:
        return None

    # Try quoted company name first
    quoted = re.findall(r'"([^"]{2,50})"', title)
    if quoted:
        return quoted[0]

    # Try "X announces/launches/expands/acquires/partners"
    patterns = [
        r'^([A-Z][A-Za-z0-9\s&\.\-]{2,40})\s+(?:announces?|launches?|expands?|acquires?|partners?|unveils?|opens?|raises?|secures?|completes?)',
        r'^([A-Z][A-Za-z0-9\s&\.\-]{2,40})\s+(?:to\s+(?:launch|expand|open|acquire|partner))',
    ]
    for pattern in patterns:
        match = re.match(pattern, title)
        if match:
            name = match.group(1).strip()
            # Filter out common false positives
            skip_words = {"The", "A", "New", "How", "Why", "What", "This", "Report"}
            if name.split()[0] not in skip_words:
                return name

    return None


class NewsSignalAdapter(LeadSourceAdapter):
    """Adapter that monitors Google News RSS for LOB-specific business triggers.

    Uses free Google News RSS feeds — no API key needed, no rate limits.
    Parses RSS XML with stdlib xml.etree.ElementTree.
    """

    def __init__(self):
        self._api_calls = 0

    def fetch_leads(
        self,
        query: str = "",
        location: str = "United States",
        limit: int = 100,
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """Fetch leads from news signals.

        Args:
            query: Optional custom query (overrides LOB defaults)
            location: Not used for RSS
            limit: Max results
            lob_type: Required — determines which queries to run

        Returns:
            List of normalized lead dicts with news signal metadata.
        """
        lob_type = kwargs.get("lob_type", "")

        if not lob_type or lob_type not in NEWS_QUERIES:
            logger.warning("news_signal_no_lob_type", lob_type=lob_type)
            return []

        queries = NEWS_QUERIES[lob_type]
        all_leads: Dict[str, Dict[str, Any]] = {}  # company_key -> lead

        for query_def in queries:
            search_query = query_def["query"]
            signal_name = query_def["signal"]

            try:
                items = self._fetch_rss(search_query)
                self._api_calls += 1

                for item in items:
                    title = item.get("title", "")
                    company = _extract_company_name(title)
                    if not company:
                        continue

                    company_key = company.lower().strip()
                    if company_key in all_leads:
                        # Add signal to existing company
                        existing = all_leads[company_key]
                        if signal_name not in existing["metadata"]["signals"]:
                            existing["metadata"]["signals"].append(signal_name)
                        if title not in existing["metadata"]["headlines"]:
                            existing["metadata"]["headlines"].append(title)
                        existing["metadata"]["signal_count"] += 1
                        continue

                    all_leads[company_key] = {
                        "client_name": company,
                        "job_title": "Prospect",
                        "source": "news_signal",
                        "job_link": item.get("link", ""),
                        "metadata": {
                            "signal_type": "news_signal",
                            "lob_type": lob_type,
                            "signals": [signal_name],
                            "headlines": [title],
                            "signal_count": 1,
                            "published_date": item.get("pub_date", ""),
                        },
                    }

            except Exception as e:
                logger.warning(
                    "news_signal_query_error",
                    query=search_query,
                    error=str(e),
                )

        # Sort by signal count, limit
        results = sorted(
            all_leads.values(),
            key=lambda x: x["metadata"]["signal_count"],
            reverse=True,
        )[:limit]

        logger.info(
            "news_signal_results",
            lob_type=lob_type,
            queries_run=len(queries),
            companies=len(results),
        )
        return results

    def _fetch_rss(self, query: str, max_items: int = 20) -> List[Dict[str, str]]:
        """Fetch and parse Google News RSS feed.

        Args:
            query: Search query
            max_items: Max RSS items to parse

        Returns:
            List of dicts with title, link, pub_date keys.
        """
        url = GOOGLE_NEWS_RSS_URL.format(query=quote_plus(query))
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})

        try:
            with urlopen(req, timeout=15) as response:
                xml_data = response.read()
        except URLError as e:
            logger.warning("news_rss_fetch_error", query=query, error=str(e))
            return []

        items = []
        try:
            root = ET.fromstring(xml_data)
            for item in root.findall(".//item")[:max_items]:
                title_el = item.find("title")
                link_el = item.find("link")
                pub_date_el = item.find("pubDate")

                items.append({
                    "title": title_el.text if title_el is not None else "",
                    "link": link_el.text if link_el is not None else "",
                    "pub_date": pub_date_el.text if pub_date_el is not None else "",
                })
        except ET.ParseError as e:
            logger.warning("news_rss_parse_error", query=query, error=str(e))

        return items

    def normalize(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Already normalized in fetch_leads."""
        return raw_data

    def test_connection(self) -> bool:
        """Test RSS feed accessibility."""
        try:
            items = self._fetch_rss("test", max_items=1)
            return True  # If no exception, feed is accessible
        except Exception:
            return False
