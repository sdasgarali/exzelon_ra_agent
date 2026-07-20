"""Permission tests for email-preview draft deletion.

Admins (not only super admins) may delete preview drafts.
"""
import pytest

pytestmark = pytest.mark.integration


class TestDraftDeletePermissions:
    def test_admin_can_bulk_delete_drafts(self, client, auth_headers):
        # auth_headers is an ADMIN — previously this required SUPER_ADMIN (403).
        r = client.request(
            "DELETE", "/api/v1/email-preview/drafts/bulk",
            headers=auth_headers, json={"draft_ids": [999999]},
        )
        assert r.status_code == 200
        assert r.json()["deleted_count"] == 0

    def test_admin_can_delete_all_drafts(self, client, auth_headers):
        r = client.request(
            "DELETE", "/api/v1/email-preview/drafts/all", headers=auth_headers,
        )
        assert r.status_code == 200

    def test_operator_cannot_bulk_delete_drafts(self, client, operator_headers):
        r = client.request(
            "DELETE", "/api/v1/email-preview/drafts/bulk",
            headers=operator_headers, json={"draft_ids": [1]},
        )
        assert r.status_code == 403
