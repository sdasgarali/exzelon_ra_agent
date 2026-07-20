"""Unit tests for mailbox phone normalization and signature logo rendering."""
import json
import pytest

from app.schemas.sender_mailbox import normalize_us_phone, SenderMailboxUpdate
from app.services.pipelines.outreach import render_signature_html

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("raw,expected", [
    ("5551234567", "(555) 123-4567"),
    ("555-123-4567", "(555) 123-4567"),
    ("(555) 123-4567", "(555) 123-4567"),
    ("+1 555.123.4567", "(555) 123-4567"),
    ("1-555-123-4567", "(555) 123-4567"),
    ("", None),
    (None, None),
])
def test_normalize_us_phone_valid(raw, expected):
    assert normalize_us_phone(raw) == expected


@pytest.mark.parametrize("bad", ["12", "555-123", "abcdefghij", "123456789012"])
def test_normalize_us_phone_invalid(bad):
    with pytest.raises(ValueError):
        normalize_us_phone(bad)


def test_schema_normalizes_phone():
    assert SenderMailboxUpdate(phone="555.123.4567").phone == "(555) 123-4567"


def test_signature_includes_logo_img():
    html = render_signature_html(json.dumps({
        "logo_url": "cdn.example.com/logo.png",
        "sender_name": "Jane Doe",
        "title": "Account Manager",
        "company": "Acme Inc.",
    }))
    assert "<img" in html
    assert "https://cdn.example.com/logo.png" in html  # scheme added
    assert "Jane Doe" in html


def test_signature_without_logo_has_no_img():
    html = render_signature_html(json.dumps({"sender_name": "Jane Doe"}))
    assert "<img" not in html
    assert "Jane Doe" in html
