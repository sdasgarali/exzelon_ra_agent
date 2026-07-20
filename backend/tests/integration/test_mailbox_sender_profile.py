"""Regression: the mailbox API must return sender-profile fields
(first/last name, phone, linkedin) on update AND list — previously
mailbox_to_response dropped them, so edits looked like they didn't save.
"""
import pytest

from app.db.models.sender_mailbox import SenderMailbox

pytestmark = pytest.mark.integration


@pytest.fixture
def a_mailbox(db_session, test_tenant):
    mb = SenderMailbox(
        tenant_id=test_tenant.tenant_id,
        email="profile@example.com",
        is_active=True,
    )
    db_session.add(mb)
    db_session.commit()
    db_session.refresh(mb)
    return mb


class TestMailboxSenderProfileRoundTrip:
    def test_update_response_returns_sender_profile(self, client, auth_headers, a_mailbox):
        r = client.put(
            f"/api/v1/mailboxes/{a_mailbox.mailbox_id}",
            headers=auth_headers,
            json={
                "sender_first_name": "Ada",
                "sender_last_name": "Lovelace",
                "phone": "555-123-4567",
                "linkedin_url": "https://linkedin.com/in/ada",
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["sender_first_name"] == "Ada"
        assert body["sender_last_name"] == "Lovelace"
        assert body["phone"] == "(555) 123-4567"  # normalized US format
        assert body["linkedin_url"] == "https://linkedin.com/in/ada"

    def test_list_returns_sender_profile(self, client, auth_headers, a_mailbox):
        client.put(
            f"/api/v1/mailboxes/{a_mailbox.mailbox_id}",
            headers=auth_headers,
            json={"sender_first_name": "Grace", "sender_last_name": "Hopper", "phone": "(212) 555-0100"},
        )
        lst = client.get("/api/v1/mailboxes", headers=auth_headers)
        assert lst.status_code == 200
        item = next(m for m in lst.json()["items"] if m["mailbox_id"] == a_mailbox.mailbox_id)
        assert item["sender_first_name"] == "Grace"
        assert item["sender_last_name"] == "Hopper"
        assert item["phone"] == "(212) 555-0100"

    def test_invalid_phone_rejected(self, client, auth_headers, a_mailbox):
        r = client.put(
            f"/api/v1/mailboxes/{a_mailbox.mailbox_id}",
            headers=auth_headers,
            json={"phone": "12"},
        )
        assert r.status_code == 422
