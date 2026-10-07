"""Seed a throwaway NeuraLeads database for the MCP end-to-end tests.

Run with the *backend's* Python (it imports the backend app), with
DATABASE_URL pointing at the same SQLite file the test server uses, after the
server has created the tables. Prints one JSON object describing the fixture.

Two workspaces (A and B) let the tests prove one tenant's key never reaches the
other tenant's data.
"""
import hashlib
import json
import os
import secrets
import sys
from datetime import date

sys.path.insert(0, os.environ["NEURALEADS_BACKEND_DIR"])

from app.core.security import get_password_hash  # noqa: E402
from app.db.base import SessionLocal  # noqa: E402
from app.db.models.api_key import ApiKey  # noqa: E402
from app.db.models.client import ClientInfo  # noqa: E402
from app.db.models.contact import ContactDetails  # noqa: E402
from app.db.models.lead import LeadDetails, LeadStatus  # noqa: E402
from app.db.models.lead_contact import LeadContactAssociation  # noqa: E402
from app.db.models.sender_mailbox import SenderMailbox, WarmupStatus  # noqa: E402
from app.db.models.tenant import Tenant, TenantPlan  # noqa: E402
from app.db.models.user import User, UserRole  # noqa: E402


def _key(db, tenant, user, scopes):
    raw = f"exz_{secrets.token_hex(32)}"
    db.add(ApiKey(tenant_id=tenant.tenant_id, name=f"e2e-{'-'.join(scopes)}",
                  key_hash=hashlib.sha256(raw.encode()).hexdigest(), key_prefix=raw[:8],
                  scopes_json=json.dumps(scopes), user_id=user.user_id, is_active=True))
    return raw


def _workspace(db, tag):
    t = Tenant(name=f"MCP E2E {tag}", slug=f"mcp-e2e-{tag.lower()}", plan=TenantPlan.ENTERPRISE,
               max_users=99, max_mailboxes=99, max_contacts=99999, max_campaigns=99, max_leads=99999)
    db.add(t)
    db.flush()
    admin = User(email=f"admin-{tag.lower()}@mcp-e2e.example.com", password_hash=get_password_hash("SecurePass123!"),
                 full_name=f"Admin {tag}", role=UserRole.ADMIN, is_active=True, is_verified=True,
                 tenant_id=t.tenant_id)
    db.add(admin)
    db.flush()
    mb = SenderMailbox(tenant_id=t.tenant_id, email=f"sender-{tag.lower()}@mcp-e2e.example.com",
                       display_name=f"Sender {tag}", password="not-a-real-password",
                       warmup_status=WarmupStatus.COLD_READY, is_active=True, connection_status="successful",
                       smtp_host="127.0.0.1", smtp_port=1, imap_host="127.0.0.1", imap_port=1,
                       daily_send_limit=30, emails_sent_today=0, total_emails_sent=40, bounce_count=1,
                       reply_count=4, complaint_count=0, warmup_days_completed=21)
    client = ClientInfo(tenant_id=t.tenant_id, client_name=f"Acme {tag}")
    lead = LeadDetails(tenant_id=t.tenant_id, client_name=f"Acme {tag}", job_title=f"Plant Manager {tag}",
                       state="TX", posting_date=date.today(), job_link=f"https://jobs.example.com/{tag}",
                       salary_min=70000, salary_max=95000, source="linkedin", lead_status=LeadStatus.NEW)
    db.add_all([mb, client, lead])
    db.flush()
    contacts = []
    for i, status in enumerate(("valid", "valid", "invalid")):
        c = ContactDetails(tenant_id=t.tenant_id, client_name=f"Acme {tag}", first_name=f"Pat{i}",
                           last_name=f"Lee{tag}", title="HR Manager", email=f"pat{i}.{tag.lower()}@acme-e2e.example.com",
                           validation_status=status, lead_id=lead.lead_id)
        db.add(c)
        db.flush()
        db.add(LeadContactAssociation(lead_id=lead.lead_id, contact_id=c.contact_id))
        contacts.append(c.contact_id)
    keys = {s: _key(db, t, admin, [s]) for s in ("read", "write", "admin")}
    return {"tenant_id": t.tenant_id, "mailbox_id": mb.mailbox_id, "lead_id": lead.lead_id,
            "client_id": client.client_id, "contact_ids": contacts, "keys": keys}


def _super_admin(db, home_tenant_id):
    """A platform super admin (home workspace A) with an admin-scoped key, for workspace selection."""
    user = User(email="root@mcp-e2e.example.com", password_hash=get_password_hash("SecurePass123!"),
                full_name="Super Admin", role=UserRole.SUPER_ADMIN, is_active=True, is_verified=True,
                tenant_id=home_tenant_id)
    db.add(user)
    db.flush()
    tenant = db.get(Tenant, home_tenant_id)
    return {"user_id": user.user_id, "key": _key(db, tenant, user, ["admin"])}


def main():
    db = SessionLocal()
    try:
        out = {"A": _workspace(db, "A"), "B": _workspace(db, "B")}
        out["super"] = _super_admin(db, out["A"]["tenant_id"])
        db.commit()
    finally:
        db.close()
    print(json.dumps(out))


if __name__ == "__main__":
    main()
