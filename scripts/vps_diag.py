"""Diagnostic script to check lead sourcing pipeline state on VPS."""
import sys
import os

os.chdir("/opt/exzelon-ra-agent/backend")
sys.path.insert(0, ".")

from app.core.config import settings as cfg
from app.db.base import SessionLocal
from app.db.models.settings import Settings
from app.db.models.job_run import JobRun

db = SessionLocal()

# Check settings
print("=== SETTINGS ===")
rows = db.query(Settings).filter(
    Settings.key.in_(["lead_sources", "jsearch_api_key"])
).all()
for r in rows:
    val = r.value_json
    if r.key == "jsearch_api_key" and val:
        val = val[:20] + "...REDACTED"
    print(f"  {r.key} = {val}")
if not rows:
    print("  (no lead_sources or jsearch_api_key found)")

# Check env config
print("\n=== ENV CONFIG ===")
jkey = getattr(cfg, "JSEARCH_API_KEY", None)
print(f"  JSEARCH_API_KEY set in .env: {bool(jkey)}")
if jkey:
    print(f"  JSEARCH_API_KEY preview: {jkey[:10]}...REDACTED")

# Last job runs
print("\n=== LAST 3 LEAD SOURCING RUNS ===")
runs = (
    db.query(JobRun)
    .filter(JobRun.pipeline_name == "lead_sourcing")
    .order_by(JobRun.started_at.desc())
    .limit(3)
    .all()
)
for r in runs:
    print(f"  Run {r.run_id}: status={r.status}, started={r.started_at}, ended={r.ended_at}")
    cj = r.counters_json or "None"
    print(f"  counters: {cj[:1200]}")
    print()

db.close()
print("=== DONE ===")
