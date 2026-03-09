"""Twilio adapter for calling and SMS (Phase 4)."""
import structlog
from typing import Dict, Any

logger = structlog.get_logger()


class TwilioAdapter:
    """Twilio integration for click-to-call and SMS."""

    def __init__(self, account_sid: str = "", auth_token: str = "", from_number: str = ""):
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.from_number = from_number

    def send_sms(self, to_number: str, body: str) -> Dict[str, Any]:
        """Send an SMS message."""
        if not self.account_sid:
            return {"success": False, "error": "Twilio not configured"}
        try:
            import httpx
            with httpx.Client(timeout=10) as client:
                resp = client.post(
                    f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json",
                    data={"To": to_number, "From": self.from_number, "Body": body},
                    auth=(self.account_sid, self.auth_token),
                )
                if resp.status_code == 201:
                    return {"success": True, "sid": resp.json().get("sid")}
                return {"success": False, "error": resp.text[:200]}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def initiate_call(self, to_number: str, twiml_url: str = "") -> Dict[str, Any]:
        """Initiate an outbound call."""
        if not self.account_sid:
            return {"success": False, "error": "Twilio not configured"}
        try:
            import httpx
            with httpx.Client(timeout=10) as client:
                resp = client.post(
                    f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Calls.json",
                    data={
                        "To": to_number,
                        "From": self.from_number,
                        "Url": twiml_url or "http://demo.twilio.com/docs/voice.xml",
                    },
                    auth=(self.account_sid, self.auth_token),
                )
                if resp.status_code == 201:
                    return {"success": True, "sid": resp.json().get("sid")}
                return {"success": False, "error": resp.text[:200]}
        except Exception as e:
            return {"success": False, "error": str(e)}
