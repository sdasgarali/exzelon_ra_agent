"""Webhook event dispatcher with HMAC signing and retry."""
import json
import hashlib
import hmac
import time
from datetime import datetime, timedelta
from typing import Dict, Any
import structlog
import httpx

from sqlalchemy.orm import Session
from app.db.models.webhook import Webhook, WebhookDelivery

logger = structlog.get_logger()

MAX_RETRIES = 3
RETRY_DELAYS = [60, 300, 900]  # 1min, 5min, 15min


def dispatch_webhook_event(
    event_type: str,
    payload: Dict[str, Any],
    db: Session,
):
    """Find matching webhooks and POST the event payload.

    Signs payload with HMAC-SHA256 if webhook has a secret.
    Records delivery attempts.
    """
    webhooks = db.query(Webhook).filter(
        Webhook.is_active == True,
        Webhook.is_archived == False,
    ).all()

    for webhook in webhooks:
        # Check if webhook subscribes to this event type
        try:
            events = json.loads(webhook.events_json) if webhook.events_json else []
        except (json.JSONDecodeError, TypeError):
            events = []

        if event_type not in events:
            continue

        _deliver_webhook(webhook, event_type, payload, db)


def _deliver_webhook(
    webhook: Webhook,
    event_type: str,
    payload: Dict[str, Any],
    db: Session,
):
    """Attempt to deliver a webhook event."""
    body = json.dumps({
        "event": event_type,
        "timestamp": datetime.utcnow().isoformat(),
        "data": payload,
    })

    headers = {"Content-Type": "application/json"}
    if webhook.secret:
        signature = hmac.new(
            webhook.secret.encode(),
            body.encode(),
            hashlib.sha256,
        ).hexdigest()
        headers["X-Webhook-Signature"] = f"sha256={signature}"

    delivery = WebhookDelivery(
        webhook_id=webhook.webhook_id,
        event=event_type,
        payload_json=body,
        attempt_count=1,
    )
    db.add(delivery)
    db.flush()

    try:
        with httpx.Client(timeout=10) as client:
            response = client.post(webhook.url, content=body, headers=headers)

        delivery.response_status = response.status_code
        delivery.response_body = response.text[:1000]
        delivery.success = 200 <= response.status_code < 300

        if delivery.success:
            webhook.last_triggered_at = datetime.utcnow()
            webhook.total_deliveries += 1
        else:
            webhook.total_failures += 1
            # Schedule retry
            if delivery.attempt_count < MAX_RETRIES:
                delay = RETRY_DELAYS[min(delivery.attempt_count - 1, len(RETRY_DELAYS) - 1)]
                delivery.next_retry_at = datetime.utcnow() + timedelta(seconds=delay)

    except Exception as e:
        delivery.response_status = 0
        delivery.response_body = str(e)[:1000]
        delivery.success = False
        webhook.total_failures += 1
        logger.error("Webhook delivery failed",
                     webhook_id=webhook.webhook_id,
                     url=webhook.url,
                     error=str(e))

    db.commit()
