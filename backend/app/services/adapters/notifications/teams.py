"""Microsoft Teams notification adapter."""
import httpx
import structlog
from typing import Dict, Any

logger = structlog.get_logger()


def send_teams_notification(webhook_url: str, event_type: str, payload: Dict[str, Any]) -> bool:
    """Send a notification to Teams via incoming webhook."""
    if not webhook_url:
        return False

    facts = [{"name": k, "value": str(v)} for k, v in payload.items()]

    card = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "summary": event_type,
        "themeColor": "0076D7",
        "title": event_type,
        "sections": [{"facts": facts}],
    }

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.post(webhook_url, json=card)
            return resp.status_code == 200
    except Exception as e:
        logger.error("Teams notification failed", error=str(e))
        return False
