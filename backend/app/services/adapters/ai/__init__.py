"""AI/LLM adapters for email content generation."""
from app.services.adapters.ai.groq import GroqAdapter
from app.services.adapters.ai.openai_adapter import OpenAIAdapter
from app.services.adapters.ai.anthropic_adapter import AnthropicAdapter
from app.services.adapters.ai.gemini import GeminiAdapter
from app.services.adapters.ai.deepseek import DeepSeekAdapter

__all__ = ["GroqAdapter", "OpenAIAdapter", "AnthropicAdapter", "GeminiAdapter", "DeepSeekAdapter"]
