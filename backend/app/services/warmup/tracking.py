"""Open/Click Tracking Service - tracking pixel and link redirect."""
import uuid
import json
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session

from app.db.models.warmup_email import WarmupEmail
from app.core.config import settings as app_settings
from app.core.settings_resolver import get_tenant_setting


def generate_tracking_pixel_url(tracking_id: str, base_url: str = None) -> str:
    base = base_url or app_settings.EFFECTIVE_BASE_URL
    return f"{base}/t/{tracking_id}/px.gif"


def generate_tracked_link(tracking_id: str, original_url: str, base_url: str = None) -> str:
    base = base_url or app_settings.EFFECTIVE_BASE_URL
    import urllib.parse
    encoded = urllib.parse.quote(original_url, safe="")
    return f"{base}/t/{tracking_id}/l?url={encoded}"


def inject_tracking(html_body: str, tracking_id: str, db: Session = None, tenant_id=None) -> str:
    base_url = app_settings.EFFECTIVE_BASE_URL
    if db:
        base_url = get_tenant_setting(db, "warmup_tracking_base_url", tenant_id=tenant_id, default=base_url)

    pixel_url = generate_tracking_pixel_url(tracking_id, base_url)
    pixel_tag = f'<img src="{pixel_url}" width="1" height="1" style="display:none" alt="" />'

    if "</body>" in html_body:
        html_body = html_body.replace("</body>", f"{pixel_tag}</body>")
    else:
        html_body += pixel_tag

    return html_body


def record_open(tracking_id: str, db: Session) -> bool:
    email = db.query(WarmupEmail).filter(WarmupEmail.tracking_id == tracking_id).first()
    if not email:
        return False
    if not email.opened_at:
        email.opened_at = datetime.utcnow()
        from app.db.models.warmup_email import WarmupEmailStatus
        if email.status == WarmupEmailStatus.SENT:
            email.status = WarmupEmailStatus.OPENED
        db.commit()
    return True


def record_click(tracking_id: str, url: str, db: Session) -> bool:
    email = db.query(WarmupEmail).filter(WarmupEmail.tracking_id == tracking_id).first()
    if not email:
        return False
    if not email.opened_at:
        email.opened_at = datetime.utcnow()
    db.commit()
    return True
