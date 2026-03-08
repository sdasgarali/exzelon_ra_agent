"""Anthropic Claude adapter for email content generation."""
from typing import List, Dict, Any, Optional
import json
import re
import httpx
from app.services.adapters.base import AIAdapter
from app.core.config import settings


class AnthropicAdapter(AIAdapter):
    """Adapter for Anthropic Claude API.

    To use:
    1. Sign up at https://console.anthropic.com/
    2. Create API key
    3. Configure in Settings → AI/LLM → Anthropic API Key

    Pricing: Pay per token (varies by model)
    """

    BASE_URL = "https://api.anthropic.com/v1"

    # Available models
    MODELS = {
        "claude-3-5-sonnet-20241022": "Claude 3.5 Sonnet - Best balance",
        "claude-3-5-haiku-20241022": "Claude 3.5 Haiku - Fast and affordable",
        "claude-3-opus-20240229": "Claude 3 Opus - Most capable",
    }

    DEFAULT_MODEL = "claude-3-5-sonnet-20241022"

    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or getattr(settings, 'ANTHROPIC_API_KEY', None)
        self.model = model or self.DEFAULT_MODEL

    def test_connection(self) -> bool:
        """Test connection to Anthropic API."""
        if not self.api_key:
            return False

        try:
            # Anthropic doesn't have a simple health check, so we make a minimal request
            with httpx.Client() as client:
                response = client.post(
                    f"{self.BASE_URL}/messages",
                    headers={
                        "x-api-key": self.api_key,
                        "anthropic-version": "2023-06-01",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "claude-3-5-haiku-20241022",
                        "max_tokens": 10,
                        "messages": [{"role": "user", "content": "Hi"}]
                    },
                    timeout=15
                )
                return response.status_code == 200
        except Exception:
            return False

    def _call_api(self, messages: List[Dict], system: str = None, temperature: float = 0.7, max_tokens: int = 1000) -> str:
        """Make API call to Anthropic."""
        if not self.api_key:
            raise ValueError("Anthropic API key not configured")

        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature
        }

        if system:
            payload["system"] = system

        with httpx.Client() as client:
            response = client.post(
                f"{self.BASE_URL}/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json"
                },
                json=payload,
                timeout=60
            )
            response.raise_for_status()
            data = response.json()
            return data["content"][0]["text"]

    def research_company(
        self,
        company_name: str,
        domain: Optional[str] = None,
        location: Optional[str] = None
    ) -> Dict[str, Any]:
        """Research a company using Anthropic Claude."""
        system_prompt = "You are a business research assistant. Return ONLY valid JSON with no markdown formatting, no code blocks, no explanation."
        hints = f"Company name: {company_name}"
        if domain:
            hints += f"\nKnown domain: {domain}"
        if location:
            hints += f"\nLocation: {location}"
        user_prompt = f"""{hints}

Return a JSON object with these fields (use null for any field you are not confident about):
{{"website": "company website URL or null", "industry": "primary industry or null", "description": "1-2 sentence company description or null", "company_size": "employee range like 1-50, 51-200, 201-500, 501-1000, 1001-5000, 5000+ or null", "headquarters": "city, state or null", "founded_year": year_as_integer_or_null, "employee_count": approximate_integer_or_null}}"""
        try:
            result = self._call_api(
                messages=[{"role": "user", "content": user_prompt}],
                system=system_prompt,
                temperature=0.3,
                max_tokens=500
            )
            cleaned = re.sub(r"```(?:json)?\s*", "", result).strip().rstrip("`")
            return json.loads(cleaned)
        except Exception:
            return {}

    def generate_email(
        self,
        contact_name: str,
        contact_title: str,
        company_name: str,
        job_title: str,
        template: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Generate personalized cold email content."""
        context = context or {}

        system_prompt = """You are an expert cold email copywriter for staffing/recruitment services.
Write compelling, personalized emails that:
- Are concise (under 150 words)
- Focus on the recipient's needs
- Include a clear call-to-action
- Sound natural and human, not salesy
- Reference the specific job posting when relevant"""

        user_prompt = f"""Write a personalized cold email to:
- Name: {contact_name}
- Title: {contact_title}
- Company: {company_name}
- Job Posting: {job_title}

Our company offers staffing/recruitment services for their industry.

{f'Additional context: {context}' if context else ''}
{f'Use this template as a guide: {template}' if template else ''}

Respond in this exact format:
SUBJECT: [subject line]
---
[email body - HTML formatted with <p> tags]
---
[email body - plain text version]"""

        try:
            result = self._call_api(
                messages=[{"role": "user", "content": user_prompt}],
                system=system_prompt
            )

            # Parse the response
            parts = result.split("---")
            subject_line = parts[0].replace("SUBJECT:", "").strip()
            body_html = parts[1].strip() if len(parts) > 1 else parts[0]
            body_text = parts[2].strip() if len(parts) > 2 else body_html

            return {
                "subject": subject_line,
                "body_html": body_html,
                "body_text": body_text
            }
        except Exception as e:
            return {
                "subject": f"Regarding your {job_title} opening",
                "body_html": f"<p>Hi {contact_name},</p><p>I noticed your {job_title} posting and wanted to reach out about how our staffing services could help.</p><p>Best regards</p>",
                "body_text": f"Hi {contact_name},\n\nI noticed your {job_title} posting and wanted to reach out about how our staffing services could help.\n\nBest regards",
                "error": str(e)
            }

    def generate_subject_variations(
        self,
        base_subject: str,
        count: int = 3
    ) -> List[str]:
        """Generate subject line variations for A/B testing."""
        try:
            result = self._call_api(
                messages=[{"role": "user", "content": f"Generate {count} variations of this subject line. Make them engaging and different from each other. Return only the subject lines, one per line:\n\nOriginal: {base_subject}"}],
                system="You are an email marketing expert. Generate compelling subject line variations.",
                temperature=0.9,
                max_tokens=200
            )

            lines = [line.strip() for line in result.strip().split("\n") if line.strip()]
            return lines[:count]
        except Exception:
            return [base_subject]

    def analyze_response(
        self,
        email_content: str,
        response_content: str
    ) -> Dict[str, Any]:
        """Analyze an email response to determine intent."""
        try:
            result = self._call_api(
                messages=[{"role": "user", "content": f"""Analyze this email response:

Original email:
{email_content}

Response:
{response_content}

Respond in this exact JSON format:
{{"sentiment": "positive|negative|neutral", "intent": "interested|not_interested|question|out_of_office|bounce", "suggested_action": "follow_up|archive|respond|escalate"}}"""}],
                system="You are an email analyst. Analyze responses to determine sender intent.",
                temperature=0.3,
                max_tokens=100
            )

            import json
            return json.loads(result)
        except Exception:
            return {
                "sentiment": "neutral",
                "intent": "unknown",
                "suggested_action": "review"
            }
