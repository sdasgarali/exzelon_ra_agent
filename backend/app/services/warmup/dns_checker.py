"""DNS Health Check Service - SPF, DKIM, DMARC, MX checks via dnspython."""
import json
import logging
from datetime import datetime
from typing import Dict, Any, List
from sqlalchemy.orm import Session

from app.db.models.sender_mailbox import SenderMailbox
from app.db.models.dns_check_result import DNSCheckResult
from app.core.settings_resolver import get_tenant_setting

logger = logging.getLogger(__name__)

# Common DKIM selectors by provider (detected from MX records)
_PROVIDER_SELECTORS: Dict[str, List[str]] = {
    "outlook": ["selector1", "selector2"],
    "google": ["google", "google2"],
    "zoho": ["zmail", "zoho"],
    "yahoo": ["s1024", "s2048"],
    "protonmail": ["protonmail", "protonmail2", "protonmail3"],
    "fastmail": ["fm1", "fm2", "fm3"],
    "mimecast": ["mimecast20190104"],
    "barracuda": ["barracuda"],
}

# Fallback selectors to try when provider is unknown
_FALLBACK_SELECTORS = [
    "selector1", "selector2",  # Microsoft 365
    "google",                   # Google Workspace
    "default",                  # Generic
    "mail",                     # Common
    "s1", "s2",                 # Generic
    "k1",                       # Mailchimp / SendGrid
    "zmail",                    # Zoho
    "dkim",                     # Generic
    "smtp",                     # Generic
]


def _detect_provider_from_mx(mx_result: Dict[str, Any]) -> str | None:
    """Detect email provider from MX records."""
    records = mx_result.get("records", [])
    for rec in records:
        host = rec.get("host", "").lower()
        if "google" in host or "gmail" in host or "googlemail" in host:
            return "google"
        if "outlook" in host or "microsoft" in host:
            return "outlook"
        if "zoho" in host:
            return "zoho"
        if "yahoodns" in host or "yahoo" in host:
            return "yahoo"
        if "protonmail" in host or "proton" in host:
            return "protonmail"
        if "fastmail" in host or "messagingengine" in host:
            return "fastmail"
        if "mimecast" in host:
            return "mimecast"
        if "barracuda" in host:
            return "barracuda"
    return None


def check_spf(domain: str) -> Dict[str, Any]:
    try:
        import dns.resolver
        answers = dns.resolver.resolve(domain, "TXT")
        for rdata in answers:
            txt = rdata.to_text().strip('"')
            if txt.startswith("v=spf1"):
                return {"valid": True, "record": txt}
        return {"valid": False, "record": None}
    except Exception as e:
        return {"valid": False, "record": None, "error": str(e)}


def _try_dkim_selector(domain: str, selector: str) -> Dict[str, Any] | None:
    """Try a single DKIM selector. Returns result dict if valid, None otherwise."""
    try:
        import dns.resolver
        dkim_domain = f"{selector}._domainkey.{domain}"
        answers = dns.resolver.resolve(dkim_domain, "TXT")
        for rdata in answers:
            txt = rdata.to_text().strip('"')
            if "v=DKIM1" in txt or "p=" in txt:
                return {"valid": True, "record": txt, "selector": selector}
    except Exception:
        pass
    return None


def check_dkim(domain: str, selector: str = "default", mx_result: Dict[str, Any] | None = None) -> Dict[str, Any]:
    # 1. If an explicit selector was configured (not "default"), try it first
    if selector != "default":
        result = _try_dkim_selector(domain, selector)
        if result:
            return result

    # 2. Auto-detect provider from MX and try provider-specific selectors
    if mx_result:
        provider = _detect_provider_from_mx(mx_result)
        if provider and provider in _PROVIDER_SELECTORS:
            for sel in _PROVIDER_SELECTORS[provider]:
                if sel == selector:
                    continue  # Already tried
                result = _try_dkim_selector(domain, sel)
                if result:
                    logger.info("DKIM found for %s with selector '%s' (provider: %s)", domain, sel, provider)
                    return result

    # 3. Try the explicit selector if we haven't yet (it was "default")
    if selector == "default":
        result = _try_dkim_selector(domain, selector)
        if result:
            return result

    # 4. Fallback: try common selectors
    for sel in _FALLBACK_SELECTORS:
        if sel == selector:
            continue  # Already tried
        result = _try_dkim_selector(domain, sel)
        if result:
            logger.info("DKIM found for %s with fallback selector '%s'", domain, sel)
            return result

    return {"valid": False, "record": None, "selector": selector, "error": "No DKIM record found with any known selector"}


def check_dmarc(domain: str) -> Dict[str, Any]:
    try:
        import dns.resolver
        dmarc_domain = f"_dmarc.{domain}"
        answers = dns.resolver.resolve(dmarc_domain, "TXT")
        for rdata in answers:
            txt = rdata.to_text().strip('"')
            if txt.startswith("v=DMARC1"):
                policy = "none"
                if "p=reject" in txt:
                    policy = "reject"
                elif "p=quarantine" in txt:
                    policy = "quarantine"
                return {"valid": True, "record": txt, "policy": policy}
        return {"valid": False, "record": None, "policy": None}
    except Exception as e:
        return {"valid": False, "record": None, "policy": None, "error": str(e)}


def check_mx(domain: str) -> Dict[str, Any]:
    try:
        import dns.resolver
        answers = dns.resolver.resolve(domain, "MX")
        records = [{"priority": r.preference, "host": str(r.exchange)} for r in answers]
        return {"valid": len(records) > 0, "records": records}
    except Exception as e:
        return {"valid": False, "records": [], "error": str(e)}


def calculate_dns_score(spf_valid: bool, dkim_valid: bool, dmarc_valid: bool) -> int:
    score = 0
    if spf_valid:
        score += 35
    if dkim_valid:
        score += 35
    if dmarc_valid:
        score += 30
    return score


def run_dns_health_check(mailbox_id: int, db: Session, tenant_id=None) -> Dict[str, Any]:
    mailbox = db.query(SenderMailbox).filter(SenderMailbox.mailbox_id == mailbox_id).first()
    if not mailbox:
        return {"error": "Mailbox not found"}

    domain = mailbox.email.split("@")[1]
    selector = get_tenant_setting(db, "warmup_dkim_selector", tenant_id=tenant_id, default="default")

    spf = check_spf(domain)
    mx = check_mx(domain)
    dkim = check_dkim(domain, selector, mx_result=mx)
    dmarc = check_dmarc(domain)

    score = calculate_dns_score(spf["valid"], dkim["valid"], dmarc["valid"])

    result = DNSCheckResult(
        mailbox_id=mailbox_id,
        domain=domain,
        spf_record=spf.get("record"),
        spf_valid=spf["valid"],
        dkim_selector=dkim.get("selector", selector),
        dkim_valid=dkim["valid"],
        dmarc_record=dmarc.get("record"),
        dmarc_valid=dmarc["valid"],
        dmarc_policy=dmarc.get("policy"),
        mx_records_json=json.dumps(mx.get("records", [])),
        overall_score=score,
    )
    db.add(result)
    mailbox.dns_score = score
    mailbox.last_dns_check_at = datetime.utcnow()
    db.commit()
    db.refresh(result)

    return {"id": result.id, "domain": domain, "score": score, "spf": spf, "dkim": dkim, "dmarc": dmarc, "mx": mx}
