"""Unit tests for email draft HTML conversion and signature preservation."""
import pytest

from app.services.email_preview_service import _message_to_html
from app.services.email_humanizer import humanize_email, _split_signature

pytestmark = pytest.mark.unit

SIG = (
    '<div style="margin-top:20px;padding-top:12px;border-top:1px solid #cccccc;'
    'font-family:Arial,sans-serif;"><strong>Zane Martin</strong><br>'
    '<span>Business Development Manager</span><br>'
    '<a href="mailto:zane@exzelon.com">zane@exzelon.com</a></div>'
)


class TestMessageToHtml:
    def test_plaintext_newlines_become_br(self):
        assert _message_to_html("Hi,\n\nHello there.\nRegards,") == "Hi,<br><br>Hello there.<br>Regards,"

    def test_crlf_normalized(self):
        assert _message_to_html("a\r\nb") == "a<br>b"

    def test_existing_html_left_untouched(self):
        html = "<p>Hi</p><p>Hello</p>"
        assert _message_to_html(html) == html

    def test_empty(self):
        assert _message_to_html("") == ""


class TestHumanizerSignaturePreservation:
    def test_split_signature(self):
        body = "Hi,\n\nMessage.\n\n" + SIG
        msg, sig = _split_signature(body)
        assert "border-top" not in msg
        assert "mailto:zane@exzelon.com" in sig

    def test_no_signature_returns_empty(self):
        msg, sig = _split_signature("Just a message, no sig.")
        assert sig == ""

    def test_humanize_keeps_signature(self):
        body = "Hi Rodolfo,\n\nMy name is Zane from Exzelon. We help teams hire.\n\nRegards,\n\n" + SIG
        result = humanize_email("Quick intro", body, "", "medium")
        # signature block + its mailto link must survive humanization
        assert "border-top:1px solid #cccccc" in result["body_html"]
        assert "mailto:zane@exzelon.com" in result["body_html"]
        assert "Zane Martin" in result["body_html"]
