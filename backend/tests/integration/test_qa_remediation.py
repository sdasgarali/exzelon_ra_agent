"""Regression tests for the enterprise QA remediation (run 20260818-235735).

Covers:
  RA-QA-001  outreach send/mailmerge/check-replies must be role-gated
  RA-QA-002  clients/contacts/lob/validation mutations must be role-gated (recruiter blocked)
  RA-QA-004  lob column-config must require auth
  RA-QA-007  /deals/forecast and /deals/stale must not be shadowed by /deals/{deal_id}
"""
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.integration

API = "/api/v1"


# ── RA-QA-001: outreach spend/send endpoints are role-gated ──────────────────

class TestOutreachSendAuthorization:
    def test_recruiter_cannot_send_emails(self, client, viewer_headers):
        r = client.post(f"{API}/outreach/send-emails", headers=viewer_headers)
        assert r.status_code == 403

    def test_recruiter_cannot_run_mailmerge(self, client, viewer_headers):
        r = client.post(f"{API}/outreach/run-mailmerge", headers=viewer_headers)
        assert r.status_code == 403

    def test_recruiter_cannot_check_replies(self, client, viewer_headers):
        r = client.post(f"{API}/outreach/check-replies", headers=viewer_headers)
        assert r.status_code == 403

    def test_admin_can_send_emails(self, client, auth_headers):
        # Mock the pipeline so the background task is a no-op; we are asserting the
        # authorization outcome (admin passes the role gate), not the pipeline run.
        with patch("app.services.pipelines.outreach.run_outreach_send_pipeline"):
            r = client.post(f"{API}/outreach/send-emails", headers=auth_headers)
        assert r.status_code == 200


# ── RA-QA-002: mutating / paid endpoints reject the read-only recruiter ──────

class TestRecruiterCannotMutate:
    def test_recruiter_cannot_create_client(self, client, viewer_headers):
        r = client.post(f"{API}/clients", headers=viewer_headers, json={})
        assert r.status_code == 403  # not 422 — role check must fire first

    def test_recruiter_cannot_delete_client(self, client, viewer_headers):
        r = client.delete(f"{API}/clients/999999999", headers=viewer_headers)
        assert r.status_code == 403  # not 404

    def test_recruiter_cannot_create_contact(self, client, viewer_headers):
        r = client.post(f"{API}/contacts", headers=viewer_headers, json={})
        assert r.status_code == 403

    def test_recruiter_cannot_create_lob(self, client, viewer_headers):
        r = client.post(f"{API}/lob/", headers=viewer_headers, json={})
        assert r.status_code == 403

    def test_recruiter_cannot_validate_bulk(self, client, viewer_headers):
        r = client.post(f"{API}/validation/validate-bulk", headers=viewer_headers, json={})
        assert r.status_code == 403

    def test_admin_reaches_client_create_validation(self, client, auth_headers):
        # Admin passes the role gate; empty body then fails schema validation (422),
        # proving authorization is not what blocks admin.
        r = client.post(f"{API}/clients", headers=auth_headers, json={})
        assert r.status_code == 422


# ── RA-QA-004: lob column-config requires authentication ─────────────────────

class TestColumnConfigAuth:
    def test_column_config_requires_auth(self, client):
        r = client.get(f"{API}/lob/column-config/staffing")
        assert r.status_code == 401

    def test_column_config_ok_with_auth(self, client, viewer_headers):
        r = client.get(f"{API}/lob/column-config/staffing", headers=viewer_headers)
        assert r.status_code == 200


# ── RA-QA-007: static deal routes resolve (not shadowed by /{deal_id}) ───────

class TestDealRouteResolution:
    def test_forecast_not_shadowed(self, client, auth_headers):
        r = client.get(f"{API}/deals/forecast", headers=auth_headers)
        assert r.status_code != 422  # 'forecast' must not be parsed as deal_id

    def test_stale_not_shadowed(self, client, auth_headers):
        r = client.get(f"{API}/deals/stale", headers=auth_headers)
        assert r.status_code != 422

    def test_numeric_deal_id_still_works(self, client, auth_headers):
        # A non-existent numeric id returns 404 (route matched, object missing) — not 422.
        r = client.get(f"{API}/deals/999999999", headers=auth_headers)
        assert r.status_code == 404
