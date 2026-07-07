"""Emailable email validation adapter."""
from typing import List, Dict, Any
import httpx
from app.services.adapters.base import EmailValidationAdapter
from app.core.config import settings
from app.db.models.email_validation import ValidationStatus


class EmailableAdapter(EmailValidationAdapter):
    """Adapter for Emailable email verification API.

    Free tier: 250 free credits (one-time, never expire)
    Docs: https://emailable.com/docs/api
    """

    BASE_URL = "https://api.emailable.com/v1"

    STATUS_MAP = {
        "deliverable": ValidationStatus.VALID,
        "undeliverable": ValidationStatus.INVALID,
        "risky": ValidationStatus.CATCH_ALL,
        "unknown": ValidationStatus.UNKNOWN,
        "duplicate": ValidationStatus.VALID,
    }

    def __init__(self, api_key: str = None):
        self.api_key = api_key or settings.EMAILABLE_API_KEY

    def test_connection(self) -> bool:
        if not self.api_key:
            return False
        try:
            with httpx.Client() as client:
                response = client.get(
                    f"{self.BASE_URL}/account",
                    params={"api_key": self.api_key},
                    timeout=10
                )
                return response.status_code == 200
        except Exception:
            return False

    def validate_email(self, email: str) -> Dict[str, Any]:
        if not self.api_key:
            raise ValueError("Emailable API key not configured")

        try:
            with httpx.Client() as client:
                response = client.get(
                    f"{self.BASE_URL}/verify",
                    params={"api_key": self.api_key, "email": email},
                    timeout=30
                )
                response.raise_for_status()
                data = response.json()

                result_state = data.get("state", "unknown")
                status = self.STATUS_MAP.get(result_state, ValidationStatus.UNKNOWN)

                return {
                    "email": email.lower(),
                    "status": status,
                    "sub_status": data.get("reason"),
                    "raw_response": data
                }
        except Exception as e:
            return {
                "email": email.lower(),
                "status": ValidationStatus.UNKNOWN,
                "sub_status": f"error: {str(e)}",
                "raw_response": {"error": str(e)}
            }

    def validate_bulk(self, emails: List[str]) -> List[Dict[str, Any]]:
        if not self.api_key:
            raise ValueError("Emailable API key not configured")
        return [self.validate_email(email) for email in emails]
