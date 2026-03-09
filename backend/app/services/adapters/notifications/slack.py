"""Slack notification adapter."""
import httpx
import structlog
from typing import Dict, Any

logger = structlog.get_logger()


def send_slack_notification(webhook_url: str, event_type: str, payload: Dict[str, Any]) -> bool:
    """Send a notification to Slack via incoming webhook."""
    if not webhook_url:
        return False

    text = f"*{event_type}*\n"
    for key, value in payload.items():
        text += f"- {key}: {value}\n"

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.post(webhook_url, json={"text": text})
            return resp.status_code == 200
    except Exception as e:
        logger.error("Slack notification failed", error=str(e))
        return False
