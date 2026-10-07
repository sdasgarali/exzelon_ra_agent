"""EFFECTIVE_FRONTEND_URL: the web-app URL used in verify/reset/deal emails.

It used to be special-cased on a hardcoded prod hostname, so a domain change sent
users links to the old host. It must now follow BASE_URL alone.
"""
import pytest

from app.core.config import Settings

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("base_url, expected", [
    ("https://neuraleads.ai", "https://neuraleads.ai"),
    ("https://neuraleads.ai/", "https://neuraleads.ai"),
    ("https://neuraleads.ai/api/v1", "https://neuraleads.ai"),
    ("http://localhost:8000", "http://localhost:3000"),
    ("http://localhost:8000/api/v1", "http://localhost:3000"),
])
def test_frontend_url_follows_base_url(base_url, expected):
    assert Settings(BASE_URL=base_url).EFFECTIVE_FRONTEND_URL == expected


def test_frontend_url_without_base_url_points_at_dev_web_port():
    s = Settings(BASE_URL="", HOST="127.0.0.1", PORT=8000)
    assert s.EFFECTIVE_FRONTEND_URL == "http://127.0.0.1:3000"
