"""Tests for ICP wizard JSON safety and error handling."""
import pytest
from unittest.mock import patch, MagicMock

pytestmark = pytest.mark.unit


class TestICPWizardJsonSafety:
    """Test that AI ICP wizard handles malformed JSON gracefully."""

    @patch("app.services.adapters.ai_content.get_ai_adapter")
    def test_valid_json_response(self, mock_get_adapter):
        """Valid JSON should be parsed normally."""
        mock_adapter = MagicMock()
        mock_adapter.generate_content.return_value = {
            "content": '{"industries": ["Healthcare"], "job_titles": ["HR Manager"], "states": ["TX"], "company_sizes": ["50-200"], "rationale": "Good fit"}'
        }
        mock_get_adapter.return_value = mock_adapter

        from app.services.ai_icp_wizard import _generate_with_ai
        result = _generate_with_ai("desc", "offering", "pains")
        assert result["industries"] == ["Healthcare"]

    @patch("app.services.adapters.ai_content.get_ai_adapter")
    def test_malformed_json_raises_valueerror(self, mock_get_adapter):
        """Malformed JSON should raise ValueError, not crash."""
        mock_adapter = MagicMock()
        mock_adapter.generate_content.return_value = {
            "content": "This is not JSON at all"
        }
        mock_get_adapter.return_value = mock_adapter

        from app.services.ai_icp_wizard import _generate_with_ai
        with pytest.raises(ValueError, match="AI returned invalid JSON"):
            _generate_with_ai("desc", "offering", "pains")

    @patch("app.services.adapters.ai_content.get_ai_adapter")
    def test_json_in_markdown_code_block(self, mock_get_adapter):
        """JSON wrapped in markdown code blocks should be extracted."""
        mock_adapter = MagicMock()
        mock_adapter.generate_content.return_value = {
            "content": '```json\n{"industries": ["Retail"], "job_titles": ["CEO"], "states": ["CA"], "company_sizes": ["10-50"], "rationale": "Test"}\n```'
        }
        mock_get_adapter.return_value = mock_adapter

        from app.services.ai_icp_wizard import _generate_with_ai
        result = _generate_with_ai("desc", "offering", "pains")
        assert result["industries"] == ["Retail"]

    @patch("app.services.adapters.ai_content.get_ai_adapter")
    def test_missing_fields_get_defaults(self, mock_get_adapter):
        """Missing fields should get empty list defaults."""
        mock_adapter = MagicMock()
        mock_adapter.generate_content.return_value = {
            "content": '{"industries": ["Logistics"]}'
        }
        mock_get_adapter.return_value = mock_adapter

        from app.services.ai_icp_wizard import _generate_with_ai
        result = _generate_with_ai("desc", "offering", "pains")
        assert result["industries"] == ["Logistics"]
        assert result["job_titles"] == []
        assert result["states"] == []
