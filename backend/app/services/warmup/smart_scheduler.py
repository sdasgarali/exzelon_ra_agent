"""Smart Send Scheduling - human-like send timing."""
import random
from datetime import datetime, timedelta
from typing import List, Dict, Any
import json
from sqlalchemy.orm import Session

from app.core.settings_resolver import get_tenant_setting


def get_send_window(db: Session, tenant_id=None) -> Dict[str, Any]:
    start = get_tenant_setting(db, "warmup_send_window_start", tenant_id=tenant_id, default="09:00")
    end = get_tenant_setting(db, "warmup_send_window_end", tenant_id=tenant_id, default="17:00")
    tz = get_tenant_setting(db, "warmup_timezone", tenant_id=tenant_id, default="US/Eastern")
    return {"start": start, "end": end, "timezone": tz}


def calculate_send_times(count: int, db: Session, tenant_id=None) -> List[datetime]:
    window = get_send_window(db, tenant_id=tenant_id)
    start_h, start_m = map(int, window["start"].split(":"))
    end_h, end_m = map(int, window["end"].split(":"))

    now = datetime.utcnow()
    base = now.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
    end_time = now.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
    total_minutes = int((end_time - base).total_seconds() / 60)

    if count <= 0 or total_minutes <= 0:
        return []

    min_gap = int(get_tenant_setting(db, "warmup_min_gap_minutes", tenant_id=tenant_id, default=15))
    max_gap = int(get_tenant_setting(db, "warmup_max_gap_minutes", tenant_id=tenant_id, default=60))

    times = []
    current = base + timedelta(minutes=random.randint(0, min(30, total_minutes)))
    for _ in range(count):
        if current > end_time:
            break
        times.append(add_human_jitter(current))
        gap = random.randint(min_gap, max_gap)
        current += timedelta(minutes=gap)

    return times


def add_human_jitter(timestamp: datetime, max_jitter_seconds: int = 120) -> datetime:
    jitter = random.randint(-max_jitter_seconds, max_jitter_seconds)
    return timestamp + timedelta(seconds=jitter)


def should_skip_weekend(db: Session, tenant_id=None) -> bool:
    skip = get_tenant_setting(db, "warmup_skip_weekends", tenant_id=tenant_id, default=True)
    if skip:
        today = datetime.utcnow().weekday()
        return today >= 5
    return False
