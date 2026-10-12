"""Operational alerting + small shared ops state (Plan_Launch_Readiness_6 M1/M3/M4).

Three things live here because they share one storage helper (Redis when reachable,
else a file under ``backend/data/ops/``) and must stay importable without the database:

* ``send_alert(kind, subject, body)`` — emails ``ALERT_EMAIL`` through the global
  system mailer (Resend, or global SMTP — the same provider that sends verification
  mail). De-duplicated: at most one email per ``kind`` per
  ``ALERT_MIN_INTERVAL_MINUTES``. Never raises.
* Scheduler heartbeat — the one uvicorn worker that owns APScheduler writes a
  timestamp every minute; ``/ready`` (served by any worker) reads it.
* A CLI used by the VPS watchdog (``deploy/watchdog/``)::

      python -m app.services.alerting send --subject "..." --body "..." [--kind watchdog] [--no-dedup]

  It imports only config + the transactional mail adapter, so it still works when
  the API is down or MySQL is unreachable. Exit code 0 = sent, 1 = not sent.

Nothing in here touches the request body or any tenant data.
"""
from __future__ import annotations

import html
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import structlog

from app.core.config import settings

logger = structlog.get_logger()

# backend/data/ops — shared by every worker on the host (same filesystem).
OPS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "ops"

HEARTBEAT_KEY = "neuraleads:ops:scheduler_heartbeat"
HEARTBEAT_FILE = "scheduler_heartbeat"
ALERT_KEY_PREFIX = "neuraleads:ops:alert:"

_REDIS_RETRY_SECONDS = 60
_redis_client = None
_redis_failed_at: float = 0.0


# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------
def _get_redis():
    """A connected Redis client, or None. A failed connect is cached for 60s so a
    missing Redis never adds latency to every call."""
    global _redis_client, _redis_failed_at
    if not settings.REDIS_URL:
        return None
    if _redis_client is not None:
        return _redis_client
    if _redis_failed_at and time.monotonic() - _redis_failed_at < _REDIS_RETRY_SECONDS:
        return None
    try:
        import redis
        client = redis.Redis.from_url(
            settings.REDIS_URL, socket_connect_timeout=0.5, socket_timeout=0.5,
        )
        client.ping()
        _redis_client = client
        return client
    except Exception:
        _redis_failed_at = time.monotonic()
        return None


def _ops_dir() -> Path:
    OPS_DIR.mkdir(parents=True, exist_ok=True)
    return OPS_DIR


def _write_file(name: str, value: str) -> None:
    """Atomic write (tmp + replace) so a reader never sees a half-written value."""
    d = _ops_dir()
    tmp = d / f".{name}.{os.getpid()}.tmp"
    tmp.write_text(value, encoding="utf-8")
    os.replace(tmp, d / name)


def _read_file(name: str) -> Optional[str]:
    try:
        return (OPS_DIR / name).read_text(encoding="utf-8").strip()
    except (FileNotFoundError, OSError):
        return None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Scheduler heartbeat (M1)
# ---------------------------------------------------------------------------
def record_scheduler_heartbeat(now: Optional[datetime] = None) -> None:
    """Called every minute by the scheduler-owning worker. Never raises."""
    ts = (now or _utcnow()).timestamp()
    try:
        _write_file(HEARTBEAT_FILE, f"{ts:.3f}")
    except Exception as e:
        logger.warning("scheduler_heartbeat_file_write_failed", error=str(e))
    try:
        r = _get_redis()
        if r is not None:
            r.set(HEARTBEAT_KEY, f"{ts:.3f}", ex=24 * 3600)
    except Exception:
        pass


def get_scheduler_heartbeat() -> Optional[datetime]:
    """Most recent heartbeat from either store (UTC), or None if never written."""
    candidates: list[float] = []
    raw = _read_file(HEARTBEAT_FILE)
    if raw:
        try:
            candidates.append(float(raw))
        except ValueError:
            pass
    try:
        r = _get_redis()
        if r is not None:
            val = r.get(HEARTBEAT_KEY)
            if val:
                candidates.append(float(val))
    except Exception:
        pass
    if not candidates:
        return None
    return datetime.fromtimestamp(max(candidates), tz=timezone.utc)


# ---------------------------------------------------------------------------
# De-duplication (M4)
# ---------------------------------------------------------------------------
def _safe_kind(kind: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in (kind or "general"))[:64]


def _claim_slot(kind: str, interval_s: int) -> bool:
    """True if no alert of this kind went out within the interval (and claim it)."""
    kind = _safe_kind(kind)
    now = time.time()
    r = _get_redis()
    if r is not None:
        try:
            # SET NX EX is atomic across workers.
            return bool(r.set(ALERT_KEY_PREFIX + kind, f"{now:.0f}", nx=True, ex=max(interval_s, 1)))
        except Exception:
            pass
    name = f"alert_{kind}"
    raw = _read_file(name)
    if raw:
        try:
            if now - float(raw) < interval_s:
                return False
        except ValueError:
            pass
    _write_file(name, f"{now:.0f}")
    return True


def _release_slot(kind: str) -> None:
    """Undo a claim when the email did not go, so the next occurrence retries."""
    kind = _safe_kind(kind)
    try:
        r = _get_redis()
        if r is not None:
            r.delete(ALERT_KEY_PREFIX + kind)
    except Exception:
        pass
    try:
        (OPS_DIR / f"alert_{kind}").unlink(missing_ok=True)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Sending
# ---------------------------------------------------------------------------
def _deliver(subject: str, body: str) -> bool:
    """Send via the GLOBAL system mailer (no DB lookup — works with MySQL down)."""
    to = (settings.ALERT_EMAIL or "").strip()
    if not to:
        logger.warning("alert_not_sent_no_alert_email", subject=subject)
        return False
    from app.services.adapters.transactional import resolve_sender

    resolved = resolve_sender(None, None)
    mailer = resolved["mailer"]
    if mailer is None:
        logger.warning("alert_not_sent_no_mailer", subject=subject, provider=resolved["provider"])
        return False
    html_body = (
        '<div style="font-family:Arial,sans-serif;max-width:720px;">'
        f"<h3 style=\"color:#b91c1c;\">{html.escape(subject)}</h3>"
        f'<pre style="white-space:pre-wrap;font-size:12px;">{html.escape(body)}</pre>'
        f"<p style=\"color:#6b7280;font-size:12px;\">env={html.escape(settings.APP_ENV)} · "
        f"{_utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}</p></div>"
    )
    result = mailer.send(
        to_email=to, subject=subject, html_body=html_body,
        from_email=resolved["sender_email"], from_name=resolved["sender_name"],
    )
    if result.ok:
        logger.info("alert_sent", subject=subject, provider=result.provider)
    else:
        logger.error("alert_send_failed", subject=subject, provider=result.provider, error=result.detail)
    return bool(result.ok)


def send_alert(kind: str, subject: str, body: str, *, dedup: bool = True) -> bool:
    """Email an operational alert. Returns True when an email went out.

    At most one email per ``kind`` per ``ALERT_MIN_INTERVAL_MINUTES`` (suppressed
    duplicates return False). Never raises — alerting must not break its caller.
    """
    try:
        full_subject = f"[NeuraLeads ALERT] {subject}"[:200]
        body = (body or "")[:20000]
        if dedup:
            interval_s = max(int(settings.ALERT_MIN_INTERVAL_MINUTES or 0), 0) * 60
            if interval_s and not _claim_slot(kind, interval_s):
                logger.info("alert_suppressed_duplicate", kind=kind)
                return False
        sent = _deliver(full_subject, body)
        if not sent and dedup:
            _release_slot(kind)
        return sent
    except Exception as e:  # never raise
        try:
            logger.error("alert_internal_error", kind=kind, error=str(e))
        except Exception:
            pass
        return False


# ---------------------------------------------------------------------------
# CLI (used by deploy/watchdog/neuraleads-watchdog.sh)
# ---------------------------------------------------------------------------
def _main(argv: Optional[list[str]] = None) -> int:
    import argparse

    p = argparse.ArgumentParser(prog="python -m app.services.alerting")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("send", help="email an alert to ALERT_EMAIL")
    s.add_argument("--subject", required=True)
    s.add_argument("--body", default="", help="body text, or '-' to read stdin")
    s.add_argument("--kind", default="watchdog")
    s.add_argument("--no-dedup", action="store_true",
                   help="skip the per-kind rate limit (the caller de-duplicates itself)")
    args = p.parse_args(argv)

    body = sys.stdin.read() if args.body == "-" else args.body
    ok = send_alert(args.kind, args.subject, body, dedup=not args.no_dedup)
    print("sent" if ok else "not sent")
    return 0 if ok else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(_main())
