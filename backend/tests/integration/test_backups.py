"""Integration tests for backup endpoints — RBAC, audit, and restore."""
import json
from unittest import mock

import pytest

from app.db.models.audit_log import AuditLog


pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# RBAC: list
# ---------------------------------------------------------------------------

class TestListBackups:
    def test_admin_can_list(self, client, auth_headers):
        with mock.patch("app.services.backup_service.list_backups", return_value=[]):
            resp = client.get("/api/v1/backups", headers=auth_headers)
        assert resp.status_code == 200

    def test_super_admin_can_list(self, client, sa_headers):
        with mock.patch("app.services.backup_service.list_backups", return_value=[]):
            resp = client.get("/api/v1/backups", headers=sa_headers)
        assert resp.status_code == 200

    def test_viewer_forbidden(self, client, viewer_headers):
        resp = client.get("/api/v1/backups", headers=viewer_headers)
        assert resp.status_code == 403

    def test_operator_forbidden(self, client, operator_headers):
        resp = client.get("/api/v1/backups", headers=operator_headers)
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# RBAC: create
# ---------------------------------------------------------------------------

class TestCreateBackup:
    _fake_result = {
        "filename": "exzelon_ra_agent_20260302_120000.sql.gz",
        "size_bytes": 1234,
        "size_human": "1.2 KB",
        "created_at": "2026-03-02T12:00:00",
    }

    def test_admin_can_create(self, client, auth_headers, db_session):
        with mock.patch("app.services.backup_service.create_backup", return_value=self._fake_result):
            resp = client.post("/api/v1/backups", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["filename"] == self._fake_result["filename"]

    def test_create_writes_audit_log(self, client, auth_headers, db_session):
        with mock.patch("app.services.backup_service.create_backup", return_value=self._fake_result):
            client.post("/api/v1/backups", headers=auth_headers)
        log = db_session.query(AuditLog).filter(AuditLog.action == "backup_create").first()
        assert log is not None
        notes = json.loads(log.notes)
        assert notes["outcome"] == "success"
        assert notes["filename"] == self._fake_result["filename"]

    def test_viewer_forbidden(self, client, viewer_headers):
        resp = client.post("/api/v1/backups", headers=viewer_headers)
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# RBAC: delete
# ---------------------------------------------------------------------------

class TestDeleteBackup:
    def test_admin_forbidden(self, client, auth_headers):
        """Admin should NOT be able to delete — super_admin only."""
        resp = client.delete("/api/v1/backups/exzelon_ra_agent_20260302_120000.sql.gz", headers=auth_headers)
        assert resp.status_code == 403

    def test_super_admin_can_delete(self, client, sa_headers, db_session):
        with mock.patch("app.services.backup_service.delete_backup", return_value=True):
            resp = client.delete(
                "/api/v1/backups/exzelon_ra_agent_20260302_120000.sql.gz",
                headers=sa_headers,
            )
        assert resp.status_code == 200
        log = db_session.query(AuditLog).filter(AuditLog.action == "backup_delete").first()
        assert log is not None

    def test_delete_not_found(self, client, sa_headers):
        with mock.patch("app.services.backup_service.delete_backup", return_value=False):
            resp = client.delete(
                "/api/v1/backups/exzelon_ra_agent_20260302_120000.sql.gz",
                headers=sa_headers,
            )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# RBAC: restore
# ---------------------------------------------------------------------------

class TestRestoreBackup:
    _fake_restore = {
        "success": True,
        "filename": "exzelon_ra_agent_20260302_120000.sql.gz",
        "pre_restore_backup": "exzelon_ra_agent_20260302_130000.sql.gz",
        "message": "Database restored successfully",
    }

    def test_admin_forbidden(self, client, auth_headers):
        """Admin should NOT be able to restore — super_admin only."""
        resp = client.post(
            "/api/v1/backups/exzelon_ra_agent_20260302_120000.sql.gz/restore",
            json={"confirm": True},
            headers=auth_headers,
        )
        assert resp.status_code == 403

    def test_requires_confirm(self, client, sa_headers):
        resp = client.post(
            "/api/v1/backups/exzelon_ra_agent_20260302_120000.sql.gz/restore",
            json={"confirm": False},
            headers=sa_headers,
        )
        assert resp.status_code == 400

    def test_file_not_found(self, client, sa_headers):
        with mock.patch("app.services.backup_service.get_backup_path") as mock_path:
            path_obj = mock.MagicMock()
            path_obj.exists.return_value = False
            mock_path.return_value = path_obj
            resp = client.post(
                "/api/v1/backups/exzelon_ra_agent_20260302_120000.sql.gz/restore",
                json={"confirm": True},
                headers=sa_headers,
            )
        assert resp.status_code == 404

    def test_super_admin_can_restore(self, client, sa_headers, db_session):
        with mock.patch("app.services.backup_service.get_backup_path") as mock_path, \
             mock.patch("app.services.backup_service.restore_backup", return_value=self._fake_restore):
            path_obj = mock.MagicMock()
            path_obj.exists.return_value = True
            mock_path.return_value = path_obj
            resp = client.post(
                "/api/v1/backups/exzelon_ra_agent_20260302_120000.sql.gz/restore",
                json={"confirm": True},
                headers=sa_headers,
            )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_restore_writes_audit_log(self, client, sa_headers, db_session):
        with mock.patch("app.services.backup_service.get_backup_path") as mock_path, \
             mock.patch("app.services.backup_service.restore_backup", return_value=self._fake_restore):
            path_obj = mock.MagicMock()
            path_obj.exists.return_value = True
            mock_path.return_value = path_obj
            client.post(
                "/api/v1/backups/exzelon_ra_agent_20260302_120000.sql.gz/restore",
                json={"confirm": True},
                headers=sa_headers,
            )
        log = db_session.query(AuditLog).filter(AuditLog.action == "backup_restore").first()
        assert log is not None
        notes = json.loads(log.notes)
        assert notes["outcome"] == "success"

    def test_restore_failure_writes_audit(self, client, sa_headers, db_session):
        with mock.patch("app.services.backup_service.get_backup_path") as mock_path, \
             mock.patch("app.services.backup_service.restore_backup", side_effect=RuntimeError("mysql failed")):
            path_obj = mock.MagicMock()
            path_obj.exists.return_value = True
            mock_path.return_value = path_obj
            resp = client.post(
                "/api/v1/backups/exzelon_ra_agent_20260302_120000.sql.gz/restore",
                json={"confirm": True},
                headers=sa_headers,
            )
        assert resp.status_code == 500
        log = db_session.query(AuditLog).filter(AuditLog.action == "backup_restore").first()
        assert log is not None
        notes = json.loads(log.notes)
        assert notes["outcome"] == "failure"

    def test_invalid_filename(self, client, sa_headers):
        resp = client.post(
            "/api/v1/backups/bad_filename.txt/restore",
            json={"confirm": True},
            headers=sa_headers,
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Download RBAC
# ---------------------------------------------------------------------------

class TestDownloadBackup:
    def test_admin_can_download(self, client, auth_headers, tmp_path):
        """Admin should pass RBAC and get a file download."""
        fake_file = tmp_path / "exzelon_ra_agent_20260302_120000.sql.gz"
        fake_file.write_bytes(b"\x1f\x8b fake gzip content")

        with mock.patch("app.services.backup_service.get_backup_path") as mock_path:
            mock_path.return_value = fake_file
            resp = client.get(
                "/api/v1/backups/exzelon_ra_agent_20260302_120000.sql.gz/download",
                headers=auth_headers,
            )
        assert resp.status_code == 200

    def test_viewer_forbidden(self, client, viewer_headers):
        resp = client.get(
            "/api/v1/backups/exzelon_ra_agent_20260302_120000.sql.gz/download",
            headers=viewer_headers,
        )
        assert resp.status_code == 403
