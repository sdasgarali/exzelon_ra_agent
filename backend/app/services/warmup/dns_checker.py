"""DNS Health Check Service - SPF, DKIM, DMARC, MX checks via dnspython."""
import json
from datetime import datetime
from typing import Dict, Any
from sqlalchemy.orm import Session

from app.db.models.sender_mailbox import SenderMailbox
from app.db.models.dns_check_result import DNSCheckResult
from app.db.models.settings import Settings


def _get_setting(db: Session, key: str, default=None):
    setting = db.query(Settings).filter(Settings.key == key).first()
    if setting and setting.value_json:
        try:
            return json.loads(setting.value_json)
        except Exception:
            pass
    return default


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


def check_dkim(domain: str, selector: str = "default") -> Dict[str, Any]:
    try:
        import dns.resolver
        dkim_domain = f"{selector}._domainkey.{domain}"
        answers = dns.resolver.resolve(dkim_domain, "TXT")
        for rdata in answers:
            txt = rdata.to_text().strip('"')
            if "v=DKIM1" in txt or "p=" in txt:
                return {"valid": True, "record": txt, "selector": selector}
        return {"valid": False, "record": None, "selector": selector}
    except Exception as e:
        return {"valid": False, "record": None, "selector": selector, "error": str(e)}


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


def run_dns_health_check(mailbox_id: int, db: Session) -> Dict[str, Any]:
    mailbox = db.query(SenderMailbox).filter(SenderMailbox.mailbox_id == mailbox_id).first()
    if not mailbox:
        return {"error": "Mailbox not found"}

    domain = mailbox.email.split("@")[1]
    selector = _get_setting(db, "warmup_dkim_selector", "default")

    spf = check_spf(domain)
    dkim = check_dkim(domain, selector)
    dmarc = check_dmarc(domain)
    mx = check_mx(domain)

    score = calculate_dns_score(spf["valid"], dkim["valid"], dmarc["valid"])

    result = DNSCheckResult(
        mailbox_id=mailbox_id,
        domain=domain,
        spf_record=spf.get("record"),
        spf_valid=spf["valid"],
        dkim_selector=selector,
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
