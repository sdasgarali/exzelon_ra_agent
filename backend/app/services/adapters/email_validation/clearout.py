"""Clearout email validation adapter."""
from typing import List, Dict, Any
import httpx
from app.services.adapters.base import EmailValidationAdapter
from app.core.config import settings
from app.db.models.email_validation import ValidationStatus


class ClearoutAdapter(EmailValidationAdapter):
    """Adapter for Clearout email validation API.

    Free tier: 100 free credits on signup
    Docs: https://docs.clearout.io/api-reference/email-verification
    """

    BASE_URL = "https://api.clearout.io/v2"

    STATUS_MAP = {
        "valid": ValidationStatus.VALID,
        "invalid": ValidationStatus.INVALID,
        "catch_all": ValidationStatus.CATCH_ALL,
        "unknown": ValidationStatus.UNKNOWN,
        "role": ValidationStatus.VALID,
    }

    def __init__(self, api_key: str = None):
        self.api_key = api_key or settings.CLEAROUT_API_KEY

    def test_connection(self) -> bool:
        if not self.api_key:
            return False
        try:
            with httpx.Client() as client:
                response = client.get(
                    f"{self.BASE_URL}/account/credits",
                    headers={"Authorization": f"Bearer:{self.api_key}"},
                    timeout=10
                )
                return response.status_code == 200
        except Exception:
            return False

    def validate_email(self, email: str) -> Dict[str, Any]:
        if not self.api_key:
            raise ValueError("Clearout API key not configured")

        try:
            with httpx.Client() as client:
                response = client.post(
                    f"{self.BASE_URL}/email_verify/instant",
                    headers={"Authorization": f"Bearer:{self.api_key}"},
                    json={"email": email},
                    timeout=30
                )
                response.raise_for_status()
                data = response.json().get("data", {})

                result_status = data.get("status", "unknown").lower()
                status = self.STATUS_MAP.get(result_status, ValidationStatus.UNKNOWN)

                return {
                    "email": email.lower(),
                    "status": status,
                    "sub_status": data.get("sub_status"),
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
            raise ValueError("Clearout API key not configured")
        return [self.validate_email(email) for email in emails]
