"""Integration tests for the outreach-roles 'purpose' field (add/edit/list)."""
import pytest

pytestmark = pytest.mark.integration


class TestOutreachRolePurpose:
    def test_create_with_purpose(self, client, sa_headers):
        r = client.post(
            "/api/v1/outreach-roles",
            headers=sa_headers,
            json={"role_name": "Account Exec", "description": "AE", "purpose": "closes deals"},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["role_name"] == "Account Exec"
        assert body["description"] == "AE"
        assert body["purpose"] == "closes deals"

    def test_purpose_round_trips_on_list_and_update(self, client, sa_headers, auth_headers):
        created = client.post(
            "/api/v1/outreach-roles",
            headers=sa_headers,
            json={"role_name": "Sourcer", "purpose": "finds candidates"},
        ).json()
        role_id = created["role_id"]

        # list (admin) returns purpose
        listed = client.get("/api/v1/outreach-roles", headers=auth_headers)
        assert listed.status_code == 200
        item = next(x for x in listed.json() if x["role_id"] == role_id)
        assert item["purpose"] == "finds candidates"

        # update purpose
        upd = client.put(
            f"/api/v1/outreach-roles/{role_id}",
            headers=sa_headers,
            json={"purpose": "sources & qualifies candidates"},
        )
        assert upd.status_code == 200
        assert upd.json()["purpose"] == "sources & qualifies candidates"
