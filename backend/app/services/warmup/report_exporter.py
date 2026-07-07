"""Warmup Report Exporter - CSV and JSON export of warmup data."""
import csv
import io
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from app.db.models.warmup_daily_log import WarmupDailyLog
from app.db.models.sender_mailbox import SenderMailbox


def build_report_data(mailbox_ids: Optional[List[int]], days: int, db: Session) -> List[Dict[str, Any]]:
    start_date = (datetime.utcnow() - timedelta(days=days)).date()
    query = db.query(WarmupDailyLog).filter(WarmupDailyLog.log_date >= start_date)

    if mailbox_ids:
        query = query.filter(WarmupDailyLog.mailbox_id.in_(mailbox_ids))

    logs = query.order_by(WarmupDailyLog.log_date, WarmupDailyLog.mailbox_id).all()

    # Get mailbox emails for reference
    mb_ids = list(set(log.mailbox_id for log in logs))
    mailboxes = {mb.mailbox_id: mb.email for mb in db.query(SenderMailbox).filter(SenderMailbox.mailbox_id.in_(mb_ids)).all()} if mb_ids else {}

    data = []
    for log in logs:
        data.append({
            "date": str(log.log_date),
            "mailbox_id": log.mailbox_id,
            "email": mailboxes.get(log.mailbox_id, ""),
            "emails_sent": log.emails_sent,
            "emails_received": log.emails_received,
            "opens": log.opens,
            "replies": log.replies,
            "bounces": log.bounces,
            "health_score": log.health_score,
            "warmup_day": log.warmup_day,
            "phase": log.phase,
            "daily_limit": log.daily_limit,
            "bounce_rate": log.bounce_rate,
            "reply_rate": log.reply_rate,
        })
    return data


def export_csv(mailbox_ids: Optional[List[int]], days: int, db: Session) -> str:
    data = build_report_data(mailbox_ids, days, db)
    if not data:
        return "No data available for export"

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=data[0].keys())
    writer.writeheader()
    writer.writerows(data)
    return output.getvalue()


def export_json(mailbox_ids: Optional[List[int]], days: int, db: Session) -> str:
    data = build_report_data(mailbox_ids, days, db)
    return json.dumps({"report": data, "generated_at": str(datetime.utcnow()), "days": days, "total_records": len(data)}, indent=2)
