"""Google Gemini adapter for email content generation."""
from typing import List, Dict, Any, Optional
import json
import re
import httpx
from app.services.adapters.base import AIAdapter
from app.core.config import settings


class GeminiAdapter(AIAdapter):
    """Adapter for Google Gemini API.

    To use:
    1. Go to https://aistudio.google.com/
    2. Create API key
    3. Configure in Settings → AI/LLM → Gemini API Key

    Pricing: Free tier available, then pay per token
    """

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

    # Available models
    MODELS = {
        "gemini-1.5-pro": "Gemini 1.5 Pro - Most capable",
        "gemini-1.5-flash": "Gemini 1.5 Flash - Fast and efficient",
        "gemini-1.0-pro": "Gemini 1.0 Pro - Stable",
    }

    DEFAULT_MODEL = "gemini-1.5-flash"

    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or getattr(settings, 'GEMINI_API_KEY', None)
        self.model = model or self.DEFAULT_MODEL

    def test_connection(self) -> bool:
        """Test connection to Gemini API."""
        if not self.api_key:
            return False

        try:
            with httpx.Client() as client:
                response = client.get(
                    f"{self.BASE_URL}/models",
                    params={"key": self.api_key},
                    timeout=10
                )
                return response.status_code == 200
        except Exception:
            return False

    def _call_api(self, prompt: str, system_instruction: str = None, temperature: float = 0.7, max_tokens: int = 1000) -> str:
        """Make API call to Gemini."""
        if not self.api_key:
            raise ValueError("Gemini API key not configured")

        payload = {
            "contents": [
                {
                    "parts": [{"text": prompt}]
                }
            ],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens
            }
        }

        if system_instruction:
            payload["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
            }

        with httpx.Client() as client:
            response = client.post(
                f"{self.BASE_URL}/models/{self.model}:generateContent",
                params={"key": self.api_key},
                json=payload,
                timeout=60
            )
            response.raise_for_status()
            data = response.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]

    def research_company(
        self,
        company_name: str,
        domain: Optional[str] = None,
        location: Optional[str] = None
    ) -> Dict[str, Any]:
        """Research a company using Google Gemini."""
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
                prompt=user_prompt,
                system_instruction=system_prompt,
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
        """Generate personalized cold email content using shared outreach prompts."""
        from app.services.adapters.ai.prompts import (
            OUTREACH_SYSTEM_PROMPT,
            build_outreach_user_prompt,
            parse_ai_email_response,
        )

        context = context or {}
        step_number = context.get("step_number", 1)

        user_prompt = build_outreach_user_prompt(
            contact_name=contact_name,
            contact_title=contact_title,
            company_name=company_name,
            job_title=job_title,
            context=context,
            step_number=step_number,
        )

        if template:
            user_prompt += f"\n\nUse this template as a guide: {template}"

        try:
            result = self._call_api(
                prompt=user_prompt,
                system_instruction=OUTREACH_SYSTEM_PROMPT
            )
            return parse_ai_email_response(result, contact_name, job_title)
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
                prompt=f"Generate {count} variations of this subject line. Make them engaging and different from each other. Return only the subject lines, one per line:\n\nOriginal: {base_subject}",
                system_instruction="You are an email marketing expert. Generate compelling subject line variations.",
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
                prompt=f"""Analyze this email response:

Original email:
{email_content}

Response:
{response_content}

Respond in this exact JSON format:
{{"sentiment": "positive|negative|neutral", "intent": "interested|not_interested|question|out_of_office|bounce", "suggested_action": "follow_up|archive|respond|escalate"}}""",
                system_instruction="You are an email analyst. Analyze responses to determine sender intent.",
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
