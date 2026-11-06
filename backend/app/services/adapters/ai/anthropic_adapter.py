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
    PROVIDER_NAME = "anthropic"

    # Available models. The Claude 3.x ids this adapter used to list were retired by
    # Anthropic (Sonnet 3.5 2025-10-28, Opus 3 2026-01-05, Haiku 3.5 2026-02-19) and
    # now fail every call. Use the current-generation aliases, never dated snapshots.
    MODELS = {
        "claude-haiku-4-5": "Claude Haiku 4.5 - Fastest and cheapest",
        "claude-sonnet-5": "Claude Sonnet 5 - Balanced",
        "claude-opus-5": "Claude Opus 5 - Most capable",
    }

    DEFAULT_MODEL = "claude-haiku-4-5"

    # Models that reject sampling parameters (temperature/top_p/top_k) with a 400.
    _NO_SAMPLING_PREFIXES = (
        "claude-opus-5", "claude-sonnet-5", "claude-opus-4-7", "claude-opus-4-8", "claude-fable",
    )

    @classmethod
    def _accepts_sampling(cls, model: str) -> bool:
        return not (model or "").startswith(cls._NO_SAMPLING_PREFIXES)

    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or getattr(settings, 'ANTHROPIC_API_KEY', None)
        # A model saved for another provider (e.g. "gpt-4.1-nano" left behind after the
        # platform switched to Anthropic) would 404 here; use the default instead.
        self.model = model if (model or "").startswith("claude-") else self.DEFAULT_MODEL
        self._last_usage = {"input_tokens": 0, "output_tokens": 0}

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
                        "model": self.model,  # the model we will actually call
                        "max_tokens": 10,
                        "messages": [{"role": "user", "content": "Hi"}]
                    },
                    timeout=15
                )
                return response.status_code == 200
        except Exception:
            return False

    @staticmethod
    def _to_anthropic_messages(messages: List[Dict], system: Optional[str] = None):
        """Convert OpenAI-style chat messages to the Messages API shape.

        Callers (e.g. the copilot) put instructions in a `{"role": "system"}` message,
        which Anthropic rejects with a 400: instructions go in the top-level `system`
        field. The conversation must also start with a user turn and have no empty
        messages. Returns (system, messages).
        """
        system_parts = [system] if system else []
        chat = []
        for m in messages or []:
            role = m.get("role")
            content = m.get("content")
            if role == "system":
                if content:
                    system_parts.append(content if isinstance(content, str) else str(content))
                continue
            if role not in ("user", "assistant") or content in (None, "", []):
                continue
            chat.append({"role": role, "content": content})
        while chat and chat[0]["role"] != "user":
            chat.pop(0)  # e.g. a UI greeting shown before the user typed anything
        return ("\n\n".join(system_parts) or None), chat

    def _call_api(self, messages: List[Dict], system: str = None, temperature: float = 0.7, max_tokens: int = 1000) -> str:
        """Make API call to Anthropic."""
        if not self.api_key:
            raise ValueError("Anthropic API key not configured")

        system, messages = self._to_anthropic_messages(messages, system)
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        if self._accepts_sampling(self.model):
            payload["temperature"] = temperature

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
            usage = data.get("usage", {})
            self._last_usage = {
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
            }
            self._track_ai_cost()
            # Join the text blocks: the first block is not always text (e.g. a
            # thinking block on models that think by default).
            return "".join(
                block.get("text", "")
                for block in data.get("content", [])
                if block.get("type") == "text"
            )

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
{{"website": "company website URL or null", "linkedin_url": "LinkedIn company page URL like https://www.linkedin.com/company/company-name or null", "industry": "primary industry or null", "description": "1-2 sentence company description or null", "company_size": "employee range like 1-50, 51-200, 201-500, 501-1000, 1001-5000, 5000+ or null", "headquarters": "city, state or null", "founded_year": year_as_integer_or_null, "employee_count": approximate_integer_or_null}}"""
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
                messages=[{"role": "user", "content": user_prompt}],
                system=OUTREACH_SYSTEM_PROMPT
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
