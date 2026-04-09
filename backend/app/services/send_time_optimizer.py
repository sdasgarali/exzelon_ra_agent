"""Send-time optimization — Gap 10 fix.

Calculates optimal send times based on recipient timezone, day of week,
and historical engagement data. Ensures emails arrive during business
hours in the recipient's local timezone.

Why: Sending at random times reduces open/reply rates. Emails sent
during the recipient's business hours (9-11 AM, 2-3 PM local) get
2-3x higher engagement. This is a standard deliverability best practice.
"""
from datetime import datetime, timedelta, time
from typing import Dict, Any, Optional, Tuple
from zoneinfo import ZoneInfo

import structlog

logger = structlog.get_logger()

# US state → timezone mapping (covers the 50 US states + DC)
STATE_TIMEZONES = {
    "AL": "America/Chicago", "AK": "America/Anchorage", "AZ": "America/Phoenix",
    "AR": "America/Chicago", "CA": "America/Los_Angeles", "CO": "America/Denver",
    "CT": "America/New_York", "DE": "America/New_York", "FL": "America/New_York",
    "GA": "America/New_York", "HI": "Pacific/Honolulu", "ID": "America/Boise",
    "IL": "America/Chicago", "IN": "America/Indiana/Indianapolis",
    "IA": "America/Chicago", "KS": "America/Chicago", "KY": "America/New_York",
    "LA": "America/Chicago", "ME": "America/New_York", "MD": "America/New_York",
    "MA": "America/New_York", "MI": "America/Detroit", "MN": "America/Chicago",
    "MS": "America/Chicago", "MO": "America/Chicago", "MT": "America/Denver",
    "NE": "America/Chicago", "NV": "America/Los_Angeles", "NH": "America/New_York",
    "NJ": "America/New_York", "NM": "America/Denver", "NY": "America/New_York",
    "NC": "America/New_York", "ND": "America/Chicago", "OH": "America/New_York",
    "OK": "America/Chicago", "OR": "America/Los_Angeles", "PA": "America/New_York",
    "RI": "America/New_York", "SC": "America/New_York", "SD": "America/Chicago",
    "TN": "America/Chicago", "TX": "America/Chicago", "UT": "America/Denver",
    "VT": "America/New_York", "VA": "America/New_York", "WA": "America/Los_Angeles",
    "WV": "America/New_York", "WI": "America/Chicago", "WY": "America/Denver",
    "DC": "America/New_York",
}

# Optimal send windows (local time) — ranked by B2B engagement data
# Source: Multiple cold email benchmarks (Woodpecker, Mailshake, Lemlist)
OPTIMAL_WINDOWS = [
    (time(9, 0), time(11, 0), 1.0),    # Morning: highest open rates
    (time(14, 0), time(15, 30), 0.85),  # Early afternoon: second peak
    (time(7, 30), time(9, 0), 0.70),    # Pre-work: mobile checks
    (time(11, 0), time(12, 0), 0.60),   # Late morning: still good
]

# Days ranked by engagement (0=Monday, 6=Sunday)
DAY_SCORES = {
    0: 0.85,  # Monday — slightly lower (inbox overload)
    1: 1.00,  # Tuesday — best day for cold email
    2: 0.95,  # Wednesday — second best
    3: 0.90,  # Thursday — good
    4: 0.70,  # Friday — lower engagement (weekend mode)
    5: 0.20,  # Saturday — poor for B2B
    6: 0.15,  # Sunday — poorest for B2B
}


def get_recipient_timezone(state: Optional[str] = None) -> str:
    """Resolve recipient's timezone from US state code.

    Falls back to America/New_York (Eastern) as it covers
    the largest US business population.
    """
    if state and state.upper() in STATE_TIMEZONES:
        return STATE_TIMEZONES[state.upper()]
    return "America/New_York"


def calculate_optimal_send_time(
    state: Optional[str] = None,
    preferred_hour: Optional[int] = None,
) -> Dict[str, Any]:
    """Calculate the next optimal send time for a recipient.

    Args:
        state: US state code for timezone resolution.
        preferred_hour: Override hour (0-23) in recipient's local time.

    Returns:
        {
            "send_at_utc": datetime,
            "recipient_local_time": str,
            "timezone": str,
            "day_score": float,
            "window_score": float,
            "combined_score": float,
        }
    """
    tz_name = get_recipient_timezone(state)
    tz = ZoneInfo(tz_name)
    now_local = datetime.now(tz)

    if preferred_hour is not None:
        # Use preferred hour, find next occurrence
        target = now_local.replace(
            hour=preferred_hour, minute=0, second=0, microsecond=0
        )
        if target <= now_local:
            target += timedelta(days=1)
        # Skip weekends
        while target.weekday() >= 5:
            target += timedelta(days=1)

        utc_time = target.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
        day_score = DAY_SCORES.get(target.weekday(), 0.5)

        return {
            "send_at_utc": utc_time,
            "recipient_local_time": target.strftime("%Y-%m-%d %H:%M %Z"),
            "timezone": tz_name,
            "day_score": day_score,
            "window_score": 0.5,
            "combined_score": day_score * 0.5,
        }

    # Find next optimal window
    best_score = 0.0
    best_time = None

    for days_ahead in range(7):
        candidate_date = now_local + timedelta(days=days_ahead)
        day_score = DAY_SCORES.get(candidate_date.weekday(), 0.5)

        if day_score < 0.5:
            continue  # Skip weekends

        for window_start, window_end, window_score in OPTIMAL_WINDOWS:
            candidate = candidate_date.replace(
                hour=window_start.hour,
                minute=window_start.minute,
                second=0,
                microsecond=0,
            )

            if candidate <= now_local:
                continue  # This window has passed today

            combined = day_score * window_score
            if combined > best_score:
                best_score = combined
                best_time = candidate

    if not best_time:
        # Fallback: tomorrow at 9 AM local
        best_time = (now_local + timedelta(days=1)).replace(
            hour=9, minute=0, second=0, microsecond=0
        )
        while best_time.weekday() >= 5:
            best_time += timedelta(days=1)
        best_score = DAY_SCORES.get(best_time.weekday(), 0.5) * 0.7

    utc_time = best_time.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

    return {
        "send_at_utc": utc_time,
        "recipient_local_time": best_time.strftime("%Y-%m-%d %H:%M %Z"),
        "timezone": tz_name,
        "day_score": DAY_SCORES.get(best_time.weekday(), 0.5),
        "window_score": best_score / max(DAY_SCORES.get(best_time.weekday(), 0.5), 0.01),
        "combined_score": round(best_score, 3),
    }


def calculate_per_contact_optimal_time(contact_id: int, db) -> Dict[str, Any]:
    """Calculate personalized optimal send time based on contact's engagement history."""
    from app.db.models.outreach import OutreachEvent
    from app.db.models.contact import ContactDetails
    from app.db.models.lead import LeadDetails
    from app.db.models.lead_contact import LeadContactAssociation

    # Get engagement events for this contact
    events = db.query(OutreachEvent).filter(
        OutreachEvent.contact_id == contact_id
    ).all()

    engagement_hours = []
    for ev in events:
        # Collect hours of engagement events (replies > clicks > opens)
        if ev.reply_detected_at:
            engagement_hours.append(ev.reply_detected_at.hour)
        elif ev.clicked_at:
            engagement_hours.append(ev.clicked_at.hour)
        elif ev.opened_at:
            engagement_hours.append(ev.opened_at.hour)

    if len(engagement_hours) >= 3:
        # Build histogram and find peak hour
        from collections import Counter
        hour_counts = Counter(engagement_hours)
        peak_hour = hour_counts.most_common(1)[0][0]
        return {
            "optimal_hour": peak_hour,
            "confidence": min(len(engagement_hours) / 10.0, 1.0),
            "engagement_count": len(engagement_hours),
            "method": "personal",
        }

    # Fallback to generic timezone-based optimization
    contact = db.query(ContactDetails).filter(
        ContactDetails.contact_id == contact_id
    ).first()
    state = None
    if contact:
        # Try to get state from associated lead
        assoc = db.query(LeadContactAssociation).filter(
            LeadContactAssociation.contact_id == contact_id
        ).first()
        if assoc:
            lead = db.query(LeadDetails).filter(
                LeadDetails.lead_id == assoc.lead_id
            ).first()
            if lead:
                state = lead.state

    optimal = calculate_optimal_send_time(state=state)
    return {
        "optimal_hour": optimal.get("send_at_utc", datetime.now()).hour if optimal.get("send_at_utc") else 10,
        "confidence": 0.3,
        "engagement_count": len(engagement_hours),
        "method": "generic",
        "timezone": optimal.get("timezone", "US/Eastern"),
    }


def is_within_send_window(
    state: Optional[str] = None,
    start_hour: int = 8,
    end_hour: int = 17,
) -> Tuple[bool, str]:
    """Check if current time is within business hours for recipient's timezone.

    Used by campaign_engine to decide whether to send now or defer.

    Returns:
        (is_within, reason)
    """
    tz_name = get_recipient_timezone(state)
    tz = ZoneInfo(tz_name)
    now_local = datetime.now(tz)

    # Weekend check
    if now_local.weekday() >= 5:
        return False, f"Weekend ({now_local.strftime('%A')}) in {tz_name}"

    # Hour check
    if now_local.hour < start_hour:
        return False, f"Too early ({now_local.strftime('%H:%M')}) in {tz_name}, opens at {start_hour}:00"
    if now_local.hour >= end_hour:
        return False, f"Too late ({now_local.strftime('%H:%M')}) in {tz_name}, closed after {end_hour}:00"

    return True, f"Within business hours ({now_local.strftime('%H:%M')}) in {tz_name}"
