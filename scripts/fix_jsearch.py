import os

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
filepath = os.path.join(
    _project_root,
    "backend", "app", "services", "adapters", "job_sources", "jsearch.py"
)

q = chr(34)
s = chr(39)
nl = chr(10)

lines = []
def w(line=""):
    lines.append(line)

# Module docstring
w(q+q+q+"JSearch API adapter (RapidAPI) - aggregates jobs from LinkedIn, Indeed, Glassdoor, etc.")
w()
w("IMPACT ON LEAD COUNT:")
w("  - JSearch is the PRIMARY real job source, aggregating LinkedIn, Indeed, Glassdoor, ZipRecruiter.")
w("  - Previously: 37 separate API calls (1 per title), 10 results each, most quota wasted.")
w("  - Now: Titles batched into ~9 grouped queries, num_pages=3 (30 results/call) = 100-300+ leads.")
w("  - Requires a RapidAPI key (free tier: 500 requests/month).")
w(q+q+q)
w("from datetime import datetime, date, timedelta")
w("from typing import List, Dict, Any, Optional")
w("import httpx")
w("from app.services.adapters.base import JobSourceAdapter")
w("from app.core.config import settings")
w()
w()
