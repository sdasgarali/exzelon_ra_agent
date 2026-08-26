"""Observability + DR wiring is inert unless configured (ELR-017 / ELR-018)."""
import pytest

pytestmark = pytest.mark.unit


def test_sentry_init_is_noop_without_dsn(monkeypatch):
    from app.core.config import settings
    from app.main import _init_sentry
    monkeypatch.setattr(settings, "SENTRY_DSN", "")
    # Must not raise and must not require sentry-sdk to be importable.
    _init_sentry()


def test_offsite_upload_disabled_without_bucket(monkeypatch, tmp_path):
    from app.core.config import settings
    from app.services.backup_service import _upload_offsite
    monkeypatch.setattr(settings, "BACKUP_S3_BUCKET", "")
    f = tmp_path / "b.sql.gz"
    f.write_bytes(b"data")
    assert _upload_offsite(f, "deadbeef") == {"status": "disabled"}


def test_sha256_file_matches_hashlib(tmp_path):
    import hashlib
    from app.services.backup_service import _sha256_file
    f = tmp_path / "x.bin"
    payload = b"exzelon-backup-bytes" * 100
    f.write_bytes(payload)
    assert _sha256_file(f) == hashlib.sha256(payload).hexdigest()
