"""Campaign engine: sender mailboxes never cross tenants; due contacts are shared fairly.

Regressions:
- select_best_mailbox had no tenant filter, so an assigned mailbox id from another tenant
  (or the automated RA pool) could be used to send a campaign's email.
- The due-contacts batch had no ORDER BY and no per-campaign share, so contacts that can't
  be sent could fill every batch and starve other campaigns.
"""
import json
from datetime import datetime, timedelta

import pytest

from app.db.models.campaign import Campaign, CampaignContact, CampaignContactStatus, CampaignStatus
from app.db.models.contact import ContactDetails
from app.db.models.sender_mailbox import SenderMailbox, WarmupStatus
from app.db.models.tenant import Tenant, TenantPlan
from app.services import campaign_engine
from app.services.mailbox_selector import select_best_mailbox

pytestmark = pytest.mark.integration


def _mailbox(db, tenant_id, email):
    mb = SenderMailbox(tenant_id=tenant_id, email=email, display_name=email, password="x",
                       warmup_status=WarmupStatus.COLD_READY, is_active=True, connection_status="successful",
                       daily_send_limit=30, emails_sent_today=0, is_blacklisted=False)
    db.add(mb)
    db.flush()
    return mb


@pytest.fixture
def other_tenant(db_session):
    t = Tenant(name="Other", slug="other-engine", plan=TenantPlan.ENTERPRISE)
    db_session.add(t)
    db_session.flush()
    return t


def test_assigned_foreign_mailbox_is_never_selected(db_session, test_tenant, other_tenant):
    foreign = _mailbox(db_session, other_tenant.tenant_id, "theirs@b.example.com")
    db_session.commit()
    assert select_best_mailbox([foreign.mailbox_id], db_session, tenant_id=test_tenant.tenant_id) is None
    mine = _mailbox(db_session, test_tenant.tenant_id, "mine@a.example.com")
    db_session.commit()
    picked = select_best_mailbox([foreign.mailbox_id, mine.mailbox_id], db_session, tenant_id=test_tenant.tenant_id)
    assert picked is not None and picked.mailbox_id == mine.mailbox_id


def test_engine_selector_passes_campaign_tenant(db_session, test_tenant, other_tenant):
    foreign = _mailbox(db_session, other_tenant.tenant_id, "theirs2@b.example.com")
    camp = Campaign(tenant_id=test_tenant.tenant_id, name="c", status=CampaignStatus.ACTIVE,
                    mailbox_ids_json=json.dumps([foreign.mailbox_id]))
    db_session.add(camp)
    db_session.commit()
    assert campaign_engine._select_mailbox(camp, db_session) is None


def test_due_contacts_shared_fairly_across_campaigns(db_session, test_tenant, monkeypatch):
    monkeypatch.setattr(campaign_engine, "BATCH_SIZE", 4)
    monkeypatch.setattr(campaign_engine, "_is_within_send_window", lambda *a, **k: True)
    seen = []
    monkeypatch.setattr(campaign_engine, "_execute_email_step",
                        lambda cc, *a, **k: seen.append(cc.campaign_id) or False, raising=False)

    old = datetime.utcnow() - timedelta(days=90)
    camps = []
    for name, n in (("big", 10), ("small", 2)):
        c = Campaign(tenant_id=test_tenant.tenant_id, name=name, status=CampaignStatus.ACTIVE)
        db_session.add(c)
        db_session.flush()
        for i in range(n):
            ct = ContactDetails(tenant_id=test_tenant.tenant_id, client_name="Acme", first_name=f"F{i}",
                                last_name=name, email=f"{name}{i}@acme.example.com")
            db_session.add(ct)
            db_session.flush()
            db_session.add(CampaignContact(campaign_id=c.campaign_id, contact_id=ct.contact_id,
                                           status=CampaignContactStatus.ACTIVE, current_step=1,
                                           next_send_at=old + timedelta(minutes=i)))
        camps.append(c)
    db_session.commit()

    captured = {}
    # Only the selection is under test; it is logged before any per-contact processing.
    orig_info = campaign_engine.logger.info

    def capture(event, **kw):
        if event == "campaign_processor_due_contacts":
            captured["steps"] = kw["contact_steps"]
        return orig_info(event, **kw)

    monkeypatch.setattr(campaign_engine.logger, "info", capture)
    try:
        campaign_engine.process_campaign_queue(db_session)
    except Exception:
        pass  # downstream sending is not under test; selection is logged first
    picked_campaigns = [cid for (_id, cid, _step) in captured["steps"]]
    assert len(picked_campaigns) == 4
    assert picked_campaigns.count(camps[1].campaign_id) == 2  # small campaign not starved


class _StopAfterSelection(Exception):
    pass


def test_no_campaign_permanently_starved_when_more_campaigns_than_slots(db_session, test_tenant, monkeypatch):
    """With more eligible campaigns than batch slots, rotation gives every campaign a turn."""
    monkeypatch.setattr(campaign_engine, "BATCH_SIZE", 2)
    monkeypatch.setattr(campaign_engine, "_is_within_send_window", lambda *a, **k: True)
    old = datetime.utcnow() - timedelta(days=1)
    ids = []
    for n in range(5):
        c = Campaign(tenant_id=test_tenant.tenant_id, name=f"c{n}", status=CampaignStatus.ACTIVE)
        db_session.add(c)
        db_session.flush()
        ct = ContactDetails(tenant_id=test_tenant.tenant_id, client_name="Acme", first_name="F",
                            last_name=f"L{n}", email=f"rot{n}@acme.example.com")
        db_session.add(ct)
        db_session.flush()
        db_session.add(CampaignContact(campaign_id=c.campaign_id, contact_id=ct.contact_id,
                                       status=CampaignContactStatus.ACTIVE, current_step=1, next_send_at=old))
        ids.append(c.campaign_id)
    db_session.commit()

    picked = set()
    orig_info = campaign_engine.logger.info

    def capture(event, **kw):
        if event == "campaign_processor_due_contacts":
            picked.update(cid for (_id, cid, _s) in kw["contact_steps"])
            raise _StopAfterSelection  # leave contacts untouched so each run sees the same queue
        return orig_info(event, **kw)

    monkeypatch.setattr(campaign_engine.logger, "info", capture)
    real_dt = campaign_engine.datetime
    base = real_dt.utcnow()
    for minute in range(5):
        class _DT(real_dt):
            @classmethod
            def utcnow(cls, _m=minute):
                return base + timedelta(minutes=_m)
        monkeypatch.setattr(campaign_engine, "datetime", _DT)
        try:
            campaign_engine.process_campaign_queue(db_session)
        except _StopAfterSelection:
            pass
    assert picked == set(ids)
