"""Reacher email validation adapter (open-source)."""
from typing import List, Dict, Any
import httpx
from app.services.adapters.base import EmailValidationAdapter
from app.core.config import settings
from app.db.models.email_validation import ValidationStatus


class ReacherAdapter(EmailValidationAdapter):
    """Adapter for Reacher email verification API.

    Free tier: 50 verifications/month (cloud). Unlimited if self-hosted.
    Cloud API: https://app.reacher.email
    Self-hosted: https://github.com/reacherhq/check-if-email-exists
    Docs: https://help.reacher.email/reacher-api-documentation
    """

    STATUS_MAP = {
        "safe": ValidationStatus.VALID,
        "invalid": ValidationStatus.INVALID,
        "risky": ValidationStatus.CATCH_ALL,
        "unknown": ValidationStatus.UNKNOWN,
    }

    def __init__(self, api_key: str = None, base_url: str = None):
        self.api_key = api_key or settings.REACHER_API_KEY
        self.base_url = base_url or settings.REACHER_BASE_URL

    def test_connection(self) -> bool:
        if not self.api_key and not self.base_url:
            return False
        try:
            with httpx.Client() as client:
                headers = {}
                if self.api_key:
                    headers["Authorization"] = f"Bearer {self.api_key}"
                response = client.post(
                    f"{self.base_url}/v0/check_email",
                    headers=headers,
                    json={"to_email": "test@example.com"},
                    timeout=10
                )
                return response.status_code in [200, 400]
        except Exception:
            return False

    def validate_email(self, email: str) -> Dict[str, Any]:
        if not self.api_key and not self.base_url:
            raise ValueError("Reacher API key or self-hosted URL not configured")

        try:
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            with httpx.Client() as client:
                response = client.post(
                    f"{self.base_url}/v0/check_email",
                    headers=headers,
                    json={"to_email": email},
                    timeout=60
                )
                response.raise_for_status()
                data = response.json()

                is_reachable = data.get("is_reachable", "unknown")
                status = self.STATUS_MAP.get(is_reachable, ValidationStatus.UNKNOWN)

                return {
                    "email": email.lower(),
                    "status": status,
                    "sub_status": is_reachable,
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
        return [self.validate_email(email) for email in emails]
