"""CAN-SPAM unsubscribe footer tests (ELR-012).

Every commercial email must carry a valid physical postal address. The footer
uses the sending tenant's address, falling back to the global config address.
"""
import pytest

from app.services.pipelines.outreach import generate_unsub_footer

pytestmark = pytest.mark.unit


def test_footer_includes_company_address():
    addr = "123 Real St, Springfield, IL 62704"
    f = generate_unsub_footer("trk123", base_url="https://x.test", company_address=addr)
    assert addr in f["html"]
    assert addr in f["text"]
    assert f["address"] == addr


def test_footer_falls_back_to_global_address(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "BILLING_COMPANY_ADDRESS", "Global HQ, 1 Main St, City ST")
    f = generate_unsub_footer("trk", base_url="https://x.test")  # no per-tenant address
    assert "Global HQ, 1 Main St, City ST" in f["html"]
    assert f["address"] == "Global HQ, 1 Main St, City ST"


def test_footer_has_unsub_link_and_reply_instruction():
    f = generate_unsub_footer("trk", base_url="https://x.test", company_address="A St")
    assert "/unsub/trk" in f["html"]
    assert "UNSUBSCRIBE" in f["text"].upper()
    assert "/unsub/trk" in f["text"]
