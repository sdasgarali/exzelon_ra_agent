"""Hunter.io email validation adapter."""
from typing import List, Dict, Any
import httpx
from app.services.adapters.base import EmailValidationAdapter
from app.core.config import settings
from app.db.models.email_validation import ValidationStatus


class HunterAdapter(EmailValidationAdapter):
    """Adapter for Hunter.io email verification API.

    Free tier: 25 verifications/month
    Docs: https://hunter.io/api/email-verifier
    """

    BASE_URL = "https://api.hunter.io/v2"

    STATUS_MAP = {
        "valid": ValidationStatus.VALID,
        "invalid": ValidationStatus.INVALID,
        "accept_all": ValidationStatus.CATCH_ALL,
        "unknown": ValidationStatus.UNKNOWN,
    }

    def __init__(self, api_key: str = None):
        self.api_key = api_key or settings.HUNTER_API_KEY

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
            raise ValueError("Hunter API key not configured")

        try:
            with httpx.Client() as client:
                response = client.get(
                    f"{self.BASE_URL}/email-verifier",
                    params={"api_key": self.api_key, "email": email},
                    timeout=30
                )
                response.raise_for_status()
                data = response.json().get("data", {})

                result_status = data.get("result", "unknown")
                status = self.STATUS_MAP.get(result_status, ValidationStatus.UNKNOWN)

                return {
                    "email": email.lower(),
                    "status": status,
                    "sub_status": data.get("score"),
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
            raise ValueError("Hunter API key not configured")
        return [self.validate_email(email) for email in emails]
