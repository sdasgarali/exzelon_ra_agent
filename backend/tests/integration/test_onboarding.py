"""Integration tests for onboarding status endpoints."""
import pytest
from app.db.models.sender_mailbox import SenderMailbox
from app.db.models.lead import LeadDetails
from app.db.models.contact import ContactDetails
from app.db.models.deal import Deal, DealStage
from app.db.models.campaign import Campaign

pytestmark = [pytest.mark.integration]


class TestOnboardingStatus:
    """Tests for GET /api/v1/onboarding/status."""

    def test_empty_tenant_returns_all_false(self, client, admin_token, test_tenant):
        """Empty tenant should have 0 completed steps."""
        resp = client.get(
            "/api/v1/onboarding/status",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_dismissed"] is False
        assert data["completed_count"] == 0
        assert data["total_steps"] == 6
        assert data["completion_percentage"] == 0
        assert data["should_show_onboarding"] is True
        for v in data["steps"].values():
            assert v is False

    def test_partial_completion(self, client, admin_token, db_session, test_tenant):
        """Tenant with mailboxes and leads should show 2/6 complete."""
        # Add a mailbox
        mb = SenderMailbox(
            email="test@example.com",
            password="encrypted",
            smtp_host="smtp.example.com",
            smtp_port=587,
            is_active=True,
            tenant_id=test_tenant.tenant_id,
        )
        db_session.add(mb)
        # Add a lead
        lead = LeadDetails(
            client_name="Acme Corp",
            job_title="Engineer",
            tenant_id=test_tenant.tenant_id,
        )
        db_session.add(lead)
        db_session.commit()

        resp = client.get(
            "/api/v1/onboarding/status",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["steps"]["has_mailboxes"] is True
        assert data["steps"]["has_leads"] is True
        assert data["steps"]["has_contacts"] is False
        assert data["completed_count"] == 2
        assert data["completion_percentage"] == 33
        assert data["should_show_onboarding"] is True

    def test_unauthenticated_returns_401(self, client):
        """Unauthenticated request should return 401."""
        resp = client.get("/api/v1/onboarding/status")
        assert resp.status_code == 401

    def test_viewer_can_access(self, client, viewer_token):
        """Viewer role can read onboarding status."""
        resp = client.get(
            "/api/v1/onboarding/status",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code == 200

    def test_super_admin_can_access(self, client, super_admin_token):
        """Super admin can access onboarding status."""
        resp = client.get(
            "/api/v1/onboarding/status",
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        assert resp.status_code == 200


class TestOnboardingDismiss:
    """Tests for POST /api/v1/onboarding/dismiss."""

    def test_dismiss_sets_timestamp(self, client, admin_token, db_session, admin_user):
        """Dismiss should set onboarding_dismissed_at on user."""
        assert admin_user.onboarding_dismissed_at is None

        resp = client.post(
            "/api/v1/onboarding/dismiss",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        db_session.refresh(admin_user)
        assert admin_user.onboarding_dismissed_at is not None

    def test_dismissed_status_reflects(self, client, admin_token, db_session, admin_user):
        """After dismiss, status should show is_dismissed=True and should_show=False."""
        client.post(
            "/api/v1/onboarding/dismiss",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        resp = client.get(
            "/api/v1/onboarding/status",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        data = resp.json()
        assert data["is_dismissed"] is True
        assert data["should_show_onboarding"] is False

    def test_unauthenticated_dismiss_returns_401(self, client):
        resp = client.post("/api/v1/onboarding/dismiss")
        assert resp.status_code == 401


class TestOnboardingReset:
    """Tests for POST /api/v1/onboarding/reset."""

    def test_reset_clears_timestamp(self, client, super_admin_token, db_session, super_admin_user):
        """Super admin reset should clear onboarding_dismissed_at."""
        # First dismiss
        client.post(
            "/api/v1/onboarding/dismiss",
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        db_session.refresh(super_admin_user)
        assert super_admin_user.onboarding_dismissed_at is not None

        # Now reset
        resp = client.post(
            "/api/v1/onboarding/reset",
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
        assert resp.status_code == 200
        db_session.refresh(super_admin_user)
        assert super_admin_user.onboarding_dismissed_at is None

    def test_admin_cannot_reset(self, client, admin_token):
        """Non-super-admin should get 403 on reset."""
        resp = client.post(
            "/api/v1/onboarding/reset",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 403

    def test_operator_cannot_reset(self, client, operator_token):
        """Operator should get 403 on reset."""
        resp = client.post(
            "/api/v1/onboarding/reset",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 403

    def test_viewer_cannot_reset(self, client, viewer_token):
        """Viewer should get 403 on reset."""
        resp = client.post(
            "/api/v1/onboarding/reset",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert resp.status_code == 403
