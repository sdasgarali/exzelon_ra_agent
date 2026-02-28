"""Integration tests for audit trail and state machine enforcement."""
import pytest
from datetime import date

pytestmark = pytest.mark.integration


class TestAuditTrail:
    """Test audit logging on lead operations."""

    def test_status_change_creates_audit(self, client, db_session, auth_headers, sample_lead):
        """Changing lead status should create audit log."""
        resp = client.put(
            "/api/v1/leads/bulk/status",
            json={"lead_ids": [sample_lead.lead_id], "status": "open"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["updated_count"] == 1

        # Check audit log
        audit_resp = client.get(
            f"/api/v1/audit/lead/{sample_lead.lead_id}",
            headers=auth_headers,
        )
        assert audit_resp.status_code == 200
        logs = audit_resp.json()
        assert len(logs) >= 1
        assert logs[0]["action"] == "status_change"
        assert "lead_status" in logs[0]["changed_fields"]

    def test_invalid_transition_rejected(self, client, db_session, auth_headers, sample_lead):
        """Invalid status transition should be rejected."""
        # NEW -> SENT is not allowed
        resp = client.put(
            "/api/v1/leads/bulk/status",
            json={"lead_ids": [sample_lead.lead_id], "status": "sent"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["updated_count"] == 0
        assert len(data["rejected"]) == 1
        assert data["rejected"][0]["current"] == "new"

    def test_update_lead_validates_transition(self, client, db_session, auth_headers, sample_lead):
        """PUT /leads/{id} should validate status transitions."""
        # NEW -> SENT should fail
        resp = client.put(
            f"/api/v1/leads/{sample_lead.lead_id}",
            json={"lead_status": "sent"},
            headers=auth_headers,
        )
        assert resp.status_code == 400
        assert "Cannot transition" in resp.json()["detail"]

    def test_update_lead_valid_transition(self, client, db_session, auth_headers, sample_lead):
        """PUT /leads/{id} with valid transition should succeed."""
        resp = client.put(
            f"/api/v1/leads/{sample_lead.lead_id}",
            json={"lead_status": "open"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["lead_status"] == "open"

    def test_archive_creates_audit(self, client, db_session, auth_headers, sample_lead):
        """Archiving a lead should create audit log."""
        client.delete(
            f"/api/v1/leads/{sample_lead.lead_id}",
            headers=auth_headers,
        )
        audit_resp = client.get(
            f"/api/v1/audit/lead/{sample_lead.lead_id}",
            headers=auth_headers,
        )
        assert audit_resp.status_code == 200
        logs = audit_resp.json()
        assert any(log["action"] == "archive" for log in logs)


class TestAuditEndpoints:
    """Test audit API endpoints."""

    def test_list_audit_admin_only(self, client, db_session, viewer_headers):
        """Viewers should not access audit logs."""
        resp = client.get("/api/v1/audit", headers=viewer_headers)
        assert resp.status_code == 403

    def test_list_audit_admin(self, client, db_session, auth_headers):
        """Admin should access audit logs."""
        resp = client.get("/api/v1/audit", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "items" in data


class TestStatusTransitionsEndpoint:
    """Test the status transitions endpoint."""

    def test_get_all_transitions(self, client, db_session, auth_headers):
        resp = client.get("/api/v1/leads/status-transitions", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "new" in data
        assert "open" in data["new"]

    def test_get_transitions_for_status(self, client, db_session, auth_headers):
        resp = client.get(
            "/api/v1/leads/status-transitions?current_status=new",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["current"] == "new"
        assert "open" in data["allowed"]
