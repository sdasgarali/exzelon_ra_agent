"""Blacklist Monitoring Service - DNS-based DNSBL queries."""
import json
from datetime import datetime
from typing import Dict, Any, List
from sqlalchemy.orm import Session

from app.db.models.sender_mailbox import SenderMailbox, WarmupStatus
from app.db.models.blacklist_check_result import BlacklistCheckResult
from app.core.settings_resolver import get_tenant_setting


DEFAULT_PROVIDERS = [
    "zen.spamhaus.org",
    "bl.spamcop.net",
    "b.barracudacentral.org",
    "dnsbl.sorbs.net",
    "cbl.abuseat.org",
    "dnsbl-1.uceprotect.net",
]


def resolve_mx_ip(domain: str) -> str:
    """Resolve the mail server IP for a domain via MX records.

    For blacklist checking, the MX IP is what matters — not the website A record.
    A domain like exzelon.com may have its website on a shared hosting IP (which
    could be blacklisted for unrelated reasons) while email goes through M365/Google
    on completely different IPs.

    Falls back to the domain A record only if no MX record exists.
    """
    try:
        import dns.resolver
        # Try MX record first — this is where email actually routes
        mx_answers = dns.resolver.resolve(domain, "MX")
        if mx_answers:
            mx_host = str(mx_answers[0].exchange).rstrip(".")
            a_answers = dns.resolver.resolve(mx_host, "A")
            return str(a_answers[0])
    except Exception:
        pass
    # Fallback to domain A record if MX lookup fails
    try:
        import dns.resolver
        answers = dns.resolver.resolve(domain, "A")
        return str(answers[0])
    except Exception:
        return ""


# Keep old name as alias for backward compatibility
resolve_domain_ip = resolve_mx_ip


def check_ip_blacklist(ip: str, provider: str) -> Dict[str, Any]:
    try:
        import dns.resolver
        reversed_ip = ".".join(reversed(ip.split(".")))
        query = f"{reversed_ip}.{provider}"
        dns.resolver.resolve(query, "A")
        return {"provider": provider, "listed": True, "details": "IP found on blacklist"}
    except Exception:
        return {"provider": provider, "listed": False, "details": "Not listed"}


def run_blacklist_check(mailbox_id: int, db: Session, tenant_id=None) -> Dict[str, Any]:
    mailbox = db.query(SenderMailbox).filter(SenderMailbox.mailbox_id == mailbox_id).first()
    if not mailbox:
        return {"error": "Mailbox not found"}

    domain = mailbox.email.split("@")[1]
    ip = resolve_mx_ip(domain)

    providers = get_tenant_setting(db, "warmup_blacklist_providers", tenant_id=tenant_id, default=DEFAULT_PROVIDERS)
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

    auto_pause = get_tenant_setting(db, "warmup_auto_pause_on_blacklist", tenant_id=tenant_id, default=True)
    if not is_clean and auto_pause:
        if mailbox.warmup_status not in [WarmupStatus.PAUSED, WarmupStatus.BLACKLISTED]:
            mailbox.warmup_status = WarmupStatus.BLACKLISTED
            db.commit()

    return {"id": bl_result.id, "domain": domain, "ip": ip, "is_clean": is_clean, "total_checked": total_checked, "total_listed": total_listed, "results": results}
