"""Open/Click Tracking Service - tracking pixel and link redirect."""
from datetime import datetime
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
    pixel_tag = f'<img src="{pixel_url}" width="1" height="1" alt="" border="0" />'

    if "</body>" in html_body:
        html_body = html_body.replace("</body>", f"{pixel_tag}</body>")
    else:
        html_body += pixel_tag

    return html_body


def record_open(tracking_id: str, db: Session) -> bool:
    # Try warmup email first
    email = db.query(WarmupEmail).filter(WarmupEmail.tracking_id == tracking_id).first()
    if email:
        if not email.opened_at:
            email.opened_at = datetime.utcnow()
            from app.db.models.warmup_email import WarmupEmailStatus
            if email.status == WarmupEmailStatus.SENT:
                email.status = WarmupEmailStatus.OPENED
            db.commit()
        return True

    # Try outreach event
    from app.db.models.outreach import OutreachEvent
    event = db.query(OutreachEvent).filter(OutreachEvent.tracking_id == tracking_id).first()
    if event:
        if not event.opened_at:
            event.opened_at = datetime.utcnow()
            # Update campaign/step open stats
            if event.campaign_id:
                _increment_open_stats(db, event)
            db.commit()
        return True

    return False


def record_click(tracking_id: str, url: str, db: Session) -> bool:
    # Try warmup email first
    email = db.query(WarmupEmail).filter(WarmupEmail.tracking_id == tracking_id).first()
    if email:
        if not email.opened_at:
            email.opened_at = datetime.utcnow()
        db.commit()
        return True

    # Try outreach event
    from app.db.models.outreach import OutreachEvent
    event = db.query(OutreachEvent).filter(OutreachEvent.tracking_id == tracking_id).first()
    if event:
        now = datetime.utcnow()
        if not event.opened_at:
            event.opened_at = now
        if not event.clicked_at:
            event.clicked_at = now
            # Update campaign/step click stats
            if event.campaign_id:
                _increment_click_stats(db, event)
        db.commit()
        return True

    return False


def _increment_open_stats(db: Session, event) -> None:
    """Increment open counters on campaign and step."""
    try:
        from app.db.models.campaign import Campaign, SequenceStep
        if event.campaign_id:
            campaign = db.query(Campaign).filter(
                Campaign.campaign_id == event.campaign_id
            ).first()
            if campaign:
                campaign.total_opened = (campaign.total_opened or 0) + 1
        if event.step_id:
            step = db.query(SequenceStep).filter(
                SequenceStep.step_id == event.step_id
            ).first()
            if step:
                step.total_opened = (step.total_opened or 0) + 1
    except Exception:
        pass


def _increment_click_stats(db: Session, event) -> None:
    """Increment click counters on step."""
    try:
        from app.db.models.campaign import SequenceStep
        if event.step_id:
            step = db.query(SequenceStep).filter(
                SequenceStep.step_id == event.step_id
            ).first()
            if step:
                step.total_clicked = (step.total_clicked or 0) + 1
    except Exception:
        pass
