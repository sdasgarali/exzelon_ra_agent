"""Tests for AI resilience layer — retry with backoff and provider fallback."""
import pytest
from unittest.mock import patch, MagicMock
from app.services.ai_resilience import retry_with_backoff, call_ai_with_fallback


pytestmark = pytest.mark.unit


class TestRetryWithBackoff:
    """Test exponential backoff retry."""

    def test_succeeds_first_try(self):
        func = MagicMock(return_value="ok")
        result = retry_with_backoff(func, max_retries=3, base_delay=0)
        assert result == "ok"
        assert func.call_count == 1

    def test_succeeds_on_second_try(self):
        func = MagicMock(side_effect=[ValueError("fail"), "ok"])
        result = retry_with_backoff(func, max_retries=3, base_delay=0)
        assert result == "ok"
        assert func.call_count == 2

    def test_succeeds_on_third_try(self):
        func = MagicMock(side_effect=[ValueError("1"), ValueError("2"), "ok"])
        result = retry_with_backoff(func, max_retries=3, base_delay=0)
        assert result == "ok"
        assert func.call_count == 3

    def test_raises_after_max_retries(self):
        func = MagicMock(side_effect=ValueError("always fail"))
        with pytest.raises(ValueError, match="always fail"):
            retry_with_backoff(func, max_retries=3, base_delay=0)
        assert func.call_count == 3

    def test_passes_args_and_kwargs(self):
        func = MagicMock(return_value="ok")
        retry_with_backoff(func, "arg1", "arg2", max_retries=1, base_delay=0, key="val")
        func.assert_called_with("arg1", "arg2", key="val")


class TestCallAIWithFallback:
    """Test provider fallback chain."""

    @patch("app.services.ai_resilience._try_get_adapter")
    @patch("app.core.settings_resolver.get_tenant_setting", return_value="groq")
    def test_uses_primary_provider(self, mock_setting, mock_get_adapter):
        adapter = MagicMock()
        adapter.generate_email.return_value = {"subject": "Hi"}
        mock_get_adapter.return_value = adapter

        db = MagicMock()
        result = call_ai_with_fallback(db, 1, "generate_email", "name", "title")
        assert result == {"subject": "Hi"}

    @patch("app.services.ai_resilience._try_get_adapter")
    @patch("app.core.settings_resolver.get_tenant_setting", return_value="groq")
    def test_falls_back_on_failure(self, mock_setting, mock_get_adapter):
        failing_adapter = MagicMock()
        failing_adapter.generate_email.side_effect = Exception("API down")

        ok_adapter = MagicMock()
        ok_adapter.generate_email.return_value = {"subject": "Fallback"}

        # First call returns failing, second returns working
        mock_get_adapter.side_effect = [failing_adapter, ok_adapter, None, None]

        db = MagicMock()
        result = call_ai_with_fallback(db, 1, "generate_email")
        assert result == {"subject": "Fallback"}

    @patch("app.services.ai_resilience._try_get_adapter", return_value=None)
    @patch("app.core.settings_resolver.get_tenant_setting", return_value="groq")
    def test_returns_fallback_when_all_fail(self, mock_setting, mock_get_adapter):
        db = MagicMock()
        result = call_ai_with_fallback(
            db, 1, "generate_email", fallback_result={"error": "No AI available"}
        )
        assert result == {"error": "No AI available"}

    @patch("app.services.ai_resilience._try_get_adapter")
    @patch("app.core.settings_resolver.get_tenant_setting", return_value="groq")
    def test_skips_adapters_without_method(self, mock_setting, mock_get_adapter):
        adapter = MagicMock(spec=[])  # No methods
        mock_get_adapter.return_value = adapter

        db = MagicMock()
        result = call_ai_with_fallback(
            db, 1, "nonexistent_method", fallback_result="fallback"
        )
        assert result == "fallback"
