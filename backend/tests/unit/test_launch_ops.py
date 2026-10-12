"""Launch readiness ops: /ready, alerting de-dup, backup integrity + retention,
exception-handler logging (Plan_Launch_Readiness_6 M1, M2, M4, B1, B3)."""
import gzip
import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import mock

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def ops(tmp_path, monkeypatch):
    """Isolate alerting state (no Redis, tmp ops dir) and the backup dir."""
    from app.services import alerting, backup_service
    ops_dir = tmp_path / "ops"
    bdir = tmp_path / "backups"
    bdir.mkdir()
    monkeypatch.setattr(alerting, "OPS_DIR", ops_dir)
    monkeypatch.setattr(alerting, "_get_redis", lambda: None)
    monkeypatch.setattr(backup_service, "BACKUP_DIR", bdir)
    return SimpleNamespace(alerting=alerting, backup_service=backup_service,
                           ops_dir=ops_dir, backup_dir=bdir)


def _touch_backup(bdir, when: datetime):
    name = f"exzelon_ra_agent_{when.strftime('%Y%m%d_%H%M%S')}.sql.gz"
    (bdir / name).write_bytes(b"x")
    return name


@pytest.fixture
def healthy(ops, monkeypatch):
    """A state where every critical readiness check passes."""
    ops.alerting.record_scheduler_heartbeat()
    _touch_backup(ops.backup_dir, datetime.now() - timedelta(hours=2))
    import app.main as main
    monkeypatch.setattr(main, "_ready_check_redis",
                        lambda: {"status": "skipped", "critical": False})
    return ops


@pytest.fixture
def api():
    from app.main import app
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# M1 /ready
# ---------------------------------------------------------------------------
def test_ready_healthy_returns_200_with_checks(healthy, api):
    for path in ("/ready", "/api/v1/ready"):
        r = api.get(path)
        assert r.status_code == 200, r.json()
        body = r.json()
        assert body["status"] == "ready"
        assert body["failed"] == []
        assert set(body["checks"]) == {"database", "redis", "scheduler", "disk", "backup"}
        assert body["checks"]["scheduler"]["status"] == "ok"
        assert body["checks"]["backup"]["status"] == "ok"


def test_ready_db_down_returns_503(healthy, api, monkeypatch):
    import app.main as main

    class _BrokenEngine:
        def connect(self):
            raise ConnectionError("mysql gone")

    monkeypatch.setattr(main, "engine", _BrokenEngine())
    r = api.get("/ready")
    assert r.status_code == 503
    assert "database" in r.json()["failed"]
    assert r.json()["checks"]["database"]["error"] == "ConnectionError"


def test_ready_stale_heartbeat_returns_503(healthy, api):
    healthy.alerting.record_scheduler_heartbeat(
        now=datetime.now(timezone.utc) - timedelta(minutes=11))
    r = api.get("/ready")
    assert r.status_code == 503
    assert r.json()["failed"] == ["scheduler"]


def test_ready_missing_heartbeat_returns_503(healthy, api):
    (healthy.ops_dir / healthy.alerting.HEARTBEAT_FILE).unlink()
    r = api.get("/ready")
    assert r.status_code == 503
    assert "scheduler" in r.json()["failed"]


def test_ready_stale_backup_returns_503(healthy, api):
    for p in healthy.backup_dir.iterdir():
        p.unlink()
    _touch_backup(healthy.backup_dir, datetime.now() - timedelta(hours=27))
    r = api.get("/ready")
    assert r.status_code == 503
    assert r.json()["failed"] == ["backup"]


def test_ready_redis_failure_is_not_critical(healthy, api, monkeypatch):
    import app.main as main
    monkeypatch.setattr(main, "_ready_check_redis",
                        lambda: {"status": "warn", "critical": False, "error": "ConnectionError"})
    r = api.get("/ready")
    assert r.status_code == 200


def test_health_unchanged(api):
    r = api.get("/health")
    assert set(r.json()) == {"status", "env", "database"}


# ---------------------------------------------------------------------------
# M4 alerting
# ---------------------------------------------------------------------------
def test_send_alert_dedups_per_kind(ops, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "ALERT_MIN_INTERVAL_MINUTES", 15)
    sent = []
    monkeypatch.setattr(ops.alerting, "_deliver", lambda s, b: sent.append(s) or True)
    assert ops.alerting.send_alert("k1", "first", "b") is True
    assert ops.alerting.send_alert("k1", "second", "b") is False  # suppressed
    assert ops.alerting.send_alert("k2", "other kind", "b") is True
    assert ops.alerting.send_alert("k1", "forced", "b", dedup=False) is True
    assert len(sent) == 3


def test_send_alert_failed_delivery_does_not_consume_slot(ops, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "ALERT_MIN_INTERVAL_MINUTES", 15)
    results = iter([False, True])
    monkeypatch.setattr(ops.alerting, "_deliver", lambda s, b: next(results))
    assert ops.alerting.send_alert("k", "s", "b") is False
    assert ops.alerting.send_alert("k", "s", "b") is True


def test_send_alert_never_raises(ops, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("mailer exploded")
    monkeypatch.setattr(ops.alerting, "_deliver", boom)
    assert ops.alerting.send_alert("k", "s", "b") is False
    monkeypatch.setattr(ops.alerting, "_claim_slot", boom)
    assert ops.alerting.send_alert("k", "s", "b") is False


def test_deliver_uses_global_mailer_to_alert_email_without_db(ops, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "ALERT_EMAIL", "info@neuraleads.ai")
    fake = mock.Mock()
    fake.send.return_value = SimpleNamespace(ok=True, provider="resend", detail="")
    with mock.patch("app.services.adapters.transactional.resolve_sender",
                    return_value={"mailer": fake, "provider": "resend", "source": "global",
                                  "sender_email": "noreply@neuraleads.ai", "sender_name": None}) as rs:
        assert ops.alerting._deliver("subj", "<b>body</b>") is True
    rs.assert_called_once_with(None, None)  # no DB session -> works with MySQL down
    kwargs = fake.send.call_args.kwargs
    assert kwargs["to_email"] == "info@neuraleads.ai"
    assert "&lt;b&gt;body" in kwargs["html_body"]  # escaped


def test_deliver_without_mailer_returns_false(ops):
    with mock.patch("app.services.adapters.transactional.resolve_sender",
                    return_value={"mailer": None, "provider": "none", "source": "none",
                                  "sender_email": None, "sender_name": None}):
        assert ops.alerting._deliver("s", "b") is False


def test_cli_exit_codes(ops, monkeypatch):
    monkeypatch.setattr(ops.alerting, "send_alert", lambda *a, **k: True)
    assert ops.alerting._main(["send", "--subject", "x", "--body", "y", "--no-dedup"]) == 0
    monkeypatch.setattr(ops.alerting, "send_alert", lambda *a, **k: False)
    assert ops.alerting._main(["send", "--subject", "x"]) == 1


def test_heartbeat_roundtrip(ops):
    assert ops.alerting.get_scheduler_heartbeat() is None
    ops.alerting.record_scheduler_heartbeat()
    hb = ops.alerting.get_scheduler_heartbeat()
    assert hb is not None
    assert (datetime.now(timezone.utc) - hb).total_seconds() < 5


# ---------------------------------------------------------------------------
# B3 backup integrity
# ---------------------------------------------------------------------------
def _write_dump(path, body: bytes):
    with gzip.open(path, "wb") as f:
        f.write(body)


GOOD_SQL = (b"-- MySQL dump\nCREATE TABLE `t` (id int);\n"
            b"INSERT INTO t VALUES (1);\n-- Dump completed on 2026-10-12  2:00:01\n")


def test_verify_backup_ok(ops, tmp_path):
    p = tmp_path / "a.sql.gz"
    _write_dump(p, GOOD_SQL)
    assert ops.backup_service.verify_backup(p, min_bytes=10) == (True, "ok")


def test_verify_backup_too_small(ops, tmp_path):
    p = tmp_path / "a.sql.gz"
    _write_dump(p, GOOD_SQL)
    ok, reason = ops.backup_service.verify_backup(p)  # default 1 MB floor
    assert not ok and "too small" in reason


def test_verify_backup_corrupt_gzip(ops, tmp_path):
    p = tmp_path / "a.sql.gz"
    _write_dump(p, GOOD_SQL * 50)
    data = p.read_bytes()
    p.write_bytes(data[: len(data) // 2])  # truncated stream
    ok, reason = ops.backup_service.verify_backup(p, min_bytes=10)
    assert not ok and "gzip" in reason


def test_verify_backup_no_create_table(ops, tmp_path):
    p = tmp_path / "a.sql.gz"
    _write_dump(p, b"-- empty\n-- Dump completed\n")
    ok, reason = ops.backup_service.verify_backup(p, min_bytes=10)
    assert not ok and "CREATE TABLE" in reason


def test_verify_backup_missing_trailer(ops, tmp_path):
    p = tmp_path / "a.sql.gz"
    _write_dump(p, b"CREATE TABLE x (id int);\nINSERT INTO x VALUES (1);\n")
    ok, reason = ops.backup_service.verify_backup(p, min_bytes=10)
    assert not ok and "Dump completed" in reason


def test_create_backup_integrity_failure_alerts_and_quarantines(ops, monkeypatch):
    bs = ops.backup_service
    monkeypatch.setattr(bs.subprocess, "run",
                        lambda *a, **k: SimpleNamespace(returncode=0, stdout=b"tiny", stderr=b""))
    alerts = []
    monkeypatch.setattr(ops.alerting, "send_alert", lambda kind, s, b: alerts.append(kind) or True)
    with pytest.raises(bs.BackupIntegrityError):
        bs.create_backup()
    assert alerts == ["backup_failed"]
    assert list(ops.backup_dir.glob("*.sql.gz")) == []          # not counted as a backup
    assert len(list(ops.backup_dir.glob("*.sql.gz.failed"))) == 1


def test_mysqldump_uses_no_tablespaces(ops, monkeypatch):
    bs = ops.backup_service
    seen = {}

    def fake_run(cmd, **k):
        seen["cmd"] = cmd
        return SimpleNamespace(returncode=1, stdout=b"", stderr=b"denied")
    monkeypatch.setattr(bs.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError):
        bs.create_backup()
    assert "--no-tablespaces" in seen["cmd"]


def test_offsite_failure_alerts(ops, monkeypatch, tmp_path):
    from app.core.config import settings
    bs = ops.backup_service
    monkeypatch.setattr(settings, "BACKUP_S3_BUCKET", "bucket")
    monkeypatch.setattr(settings, "BACKUP_ENCRYPT", False)

    def no_client():
        raise RuntimeError("bad creds")
    monkeypatch.setattr(bs, "_s3_client", no_client)
    alerts = []
    monkeypatch.setattr(ops.alerting, "send_alert", lambda kind, s, b: alerts.append(kind) or True)
    f = tmp_path / "exzelon_ra_agent_20261012_020000.sql.gz"
    f.write_bytes(b"d")
    out = bs._upload_offsite(f, "abc")
    assert out["status"] == "failed"
    assert alerts == ["backup_offsite_failed"]


def test_region_derived_from_b2_endpoint(ops):
    bs = ops.backup_service
    assert bs._region_from_endpoint("https://s3.us-west-004.backblazeb2.com") == "us-west-004"
    assert bs._region_from_endpoint("https://s3.eu-central-003.backblazeb2.com/") == "eu-central-003"
    assert bs._region_from_endpoint("https://example.com") is None


def test_offsite_prune_deletes_only_old_backup_objects(ops, monkeypatch):
    from app.core.config import settings
    bs = ops.backup_service
    monkeypatch.setattr(settings, "BACKUP_S3_BUCKET", "bucket")
    monkeypatch.setattr(settings, "BACKUP_S3_PREFIX", "db-backups")
    now = datetime.now(timezone.utc)
    objs = [
        {"Key": "db-backups/exzelon_ra_agent_20260101_020000.sql.gz.enc", "LastModified": now - timedelta(days=40)},
        {"Key": "db-backups/exzelon_ra_agent_20261010_020000.sql.gz.enc", "LastModified": now - timedelta(days=2)},
        {"Key": "db-backups/notes.txt", "LastModified": now - timedelta(days=400)},
    ]
    s3 = mock.Mock()
    s3.get_paginator.return_value.paginate.return_value = [{"Contents": objs}]
    assert bs._prune_offsite(s3) == 1
    s3.delete_object.assert_called_once_with(Bucket="bucket", Key=objs[0]["Key"])


# ---------------------------------------------------------------------------
# B1 retention floor
# ---------------------------------------------------------------------------
def test_effective_retention_floor(ops, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "BACKUP_LOCAL_RETENTION_DAYS", 14)
    f = ops.backup_service.effective_retention_days
    assert f(3) == 14       # old default 3 is lifted to the floor
    assert f(30) == 30      # a longer admin setting wins
    assert f(None) == 14
    assert f("bad") == 14


def test_cleanup_keeps_14_days(ops):
    bs = ops.backup_service
    keep = _touch_backup(ops.backup_dir, datetime.now() - timedelta(days=10))
    old = _touch_backup(ops.backup_dir, datetime.now() - timedelta(days=20))
    assert bs.cleanup_old_backups(14) == 1
    names = {p.name for p in ops.backup_dir.iterdir()}
    assert keep in names and old not in names


def test_job_backup_cleanup_applies_floor(ops, monkeypatch):
    from app.services.warmup import scheduler
    from app.core.config import settings
    monkeypatch.setattr(settings, "BACKUP_LOCAL_RETENTION_DAYS", 14)
    monkeypatch.setattr(scheduler, "_is_job_enabled", lambda j: True)
    monkeypatch.setattr(scheduler, "_get_db", lambda: mock.Mock())
    monkeypatch.setattr("app.core.settings_resolver.get_tenant_setting", lambda *a, **k: 3)
    seen = []
    monkeypatch.setattr(ops.backup_service, "cleanup_old_backups", lambda d: seen.append(d) or 0)
    scheduler.job_backup_cleanup()
    assert seen == [14]


def test_job_daily_backup_failure_alerts(ops, monkeypatch):
    from app.services.warmup import scheduler
    monkeypatch.setattr(scheduler, "_is_job_enabled", lambda j: True)

    def fail():
        raise RuntimeError("mysqldump failed (exit 2)")
    monkeypatch.setattr(ops.backup_service, "create_backup", fail)
    alerts = []
    monkeypatch.setattr(ops.alerting, "send_alert", lambda kind, s, b: alerts.append(kind) or True)
    scheduler.job_daily_backup()  # must not raise
    assert alerts == ["backup_failed"]


def test_scheduler_heartbeat_job_writes_heartbeat(ops):
    from app.services.warmup import scheduler
    scheduler.job_scheduler_heartbeat()
    assert ops.alerting.get_scheduler_heartbeat() is not None


# ---------------------------------------------------------------------------
# M2 exception handler
# ---------------------------------------------------------------------------
def test_global_exception_handler_logs_traceback_not_body(monkeypatch):
    import app.main as main
    fake_logger = mock.Mock()
    monkeypatch.setattr(main, "logger", fake_logger)
    alerts = []
    monkeypatch.setattr("app.services.alerting.send_alert",
                        lambda kind, s, b: alerts.append((kind, s, b)) or True)
    try:
        raise ValueError("kaboom")
    except ValueError as e:
        exc = e
    request = SimpleNamespace(method="POST", url=SimpleNamespace(path="/api/v1/leads"),
                              body=mock.Mock(side_effect=AssertionError("body must not be read")))
    resp = asyncio.run(main.global_exception_handler(request, exc))
    assert resp.status_code == 500
    _, kwargs = fake_logger.error.call_args
    assert kwargs["exc_info"][1] is exc and kwargs["exc_info"][2] is not None
    assert kwargs["path"] == "/api/v1/leads" and kwargs["method"] == "POST"
    assert "body" not in kwargs
    assert alerts and alerts[0][0] == "unhandled_exception"
    assert "Traceback" in alerts[0][2] and "kaboom" in alerts[0][2]
    request.body.assert_not_called()


def test_unhandled_exception_returns_generic_500(api, monkeypatch):
    import app.main as main
    monkeypatch.setattr("app.services.alerting.send_alert", lambda *a, **k: False)
    monkeypatch.setattr(main, "readiness_report", mock.Mock(side_effect=RuntimeError("secret detail")))
    r = api.get("/ready")
    assert r.status_code == 500
    assert r.json() == {"detail": "Internal server error"}
