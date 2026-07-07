"""MailboxValidator email validation adapter."""
from typing import List, Dict, Any
import httpx
from app.services.adapters.base import EmailValidationAdapter
from app.core.config import settings
from app.db.models.email_validation import ValidationStatus


class MailboxValidatorAdapter(EmailValidationAdapter):
    """Adapter for MailboxValidator email validation API.

    Free tier: 300 free API queries every 30 days (auto-renews)
    Docs: https://www.mailboxvalidator.com/api-single-validation
    """

    BASE_URL = "https://api.mailboxvalidator.com/v2"

    STATUS_MAP = {
        "True": ValidationStatus.VALID,
        "False": ValidationStatus.INVALID,
        "": ValidationStatus.UNKNOWN,
    }

    def __init__(self, api_key: str = None):
        self.api_key = api_key or settings.MAILBOXVALIDATOR_API_KEY

    def test_connection(self) -> bool:
        if not self.api_key:
            return False
        try:
            with httpx.Client() as client:
                response = client.get(
                    f"{self.BASE_URL}/validation/single",
                    params={"key": self.api_key, "email": "test@example.com", "format": "json"},
                    timeout=10
                )
                return response.status_code == 200
        except Exception:
            return False

    def validate_email(self, email: str) -> Dict[str, Any]:
        if not self.api_key:
            raise ValueError("MailboxValidator API key not configured")

        try:
            with httpx.Client() as client:
                response = client.get(
                    f"{self.BASE_URL}/validation/single",
                    params={"key": self.api_key, "email": email, "format": "json"},
                    timeout=30
                )
                response.raise_for_status()
                data = response.json()

                is_valid = data.get("is_verified", "")
                if data.get("is_catchall", "") == "True":
                    status = ValidationStatus.CATCH_ALL
                elif data.get("is_disposable", "") == "True":
                    status = ValidationStatus.INVALID
                else:
                    status = self.STATUS_MAP.get(str(is_valid), ValidationStatus.UNKNOWN)

                return {
                    "email": email.lower(),
                    "status": status,
                    "sub_status": data.get("status"),
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
            raise ValueError("MailboxValidator API key not configured")
        return [self.validate_email(email) for email in emails]
