"""Blacklist Monitoring Service - DNS-based DNSBL queries."""
import json
from datetime import datetime
from typing import Dict, Any, List
from sqlalchemy.orm import Session

from app.db.models.sender_mailbox import SenderMailbox, WarmupStatus
from app.db.models.blacklist_check_result import BlacklistCheckResult
from app.db.models.settings import Settings


DEFAULT_PROVIDERS = [
    "zen.spamhaus.org",
    "bl.spamcop.net",
    "b.barracudacentral.org",
    "dnsbl.sorbs.net",
    "cbl.abuseat.org",
    "dnsbl-1.uceprotect.net",
]


def _get_setting(db: Session, key: str, default=None):
    setting = db.query(Settings).filter(Settings.key == key).first()
    if setting and setting.value_json:
        try:
            return json.loads(setting.value_json)
        except Exception:
            pass
    return default


def resolve_domain_ip(domain: str) -> str:
    try:
        import dns.resolver
        answers = dns.resolver.resolve(domain, "A")
        return str(answers[0])
    except Exception:
        return ""


def check_ip_blacklist(ip: str, provider: str) -> Dict[str, Any]:
    try:
        import dns.resolver
        reversed_ip = ".".join(reversed(ip.split(".")))
        query = f"{reversed_ip}.{provider}"
        dns.resolver.resolve(query, "A")
        return {"provider": provider, "listed": True, "details": "IP found on blacklist"}
    except Exception:
        return {"provider": provider, "listed": False, "details": "Not listed"}


def run_blacklist_check(mailbox_id: int, db: Session) -> Dict[str, Any]:
    mailbox = db.query(SenderMailbox).filter(SenderMailbox.mailbox_id == mailbox_id).first()
    if not mailbox:
        return {"error": "Mailbox not found"}

    domain = mailbox.email.split("@")[1]
    ip = resolve_domain_ip(domain)

    providers = _get_setting(db, "warmup_blacklist_providers", DEFAULT_PROVIDERS)
    if isinstance(providers, str):
        providers = [p.strip() for p in providers.split(",")]

    results = []
    if ip:
        for provider in providers:
            result = check_ip_blacklist(ip, provider)
            results.append(result)
    else:
        results = [{"provider": p, "listed": False, "details": "Could not resolve IP"} for p in providers]

    total_checked = len(results)
    total_listed = sum(1 for r in results if r["listed"])
    is_clean = total_listed == 0

    bl_result = BlacklistCheckResult(
        mailbox_id=mailbox_id,
        domain=domain,
        ip_address=ip,
        results_json=json.dumps(results),
        total_checked=total_checked,
        total_listed=total_listed,
        is_clean=is_clean,
    )
    db.add(bl_result)

    mailbox.is_blacklisted = not is_clean
    mailbox.last_blacklist_check_at = datetime.utcnow()
    db.commit()
    db.refresh(bl_result)

    auto_pause = _get_setting(db, "warmup_auto_pause_on_blacklist", True)
    if not is_clean and auto_pause:
        if mailbox.warmup_status not in [WarmupStatus.PAUSED, WarmupStatus.BLACKLISTED]:
            mailbox.warmup_status = WarmupStatus.BLACKLISTED
            db.commit()

    return {"id": bl_result.id, "domain": domain, "ip": ip, "is_clean": is_clean, "total_checked": total_checked, "total_listed": total_listed, "results": results}
