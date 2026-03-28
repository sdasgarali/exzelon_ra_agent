"""APScheduler Integration - background job scheduler for warmup tasks."""
import json
from datetime import date
import structlog


logger = structlog.get_logger()
_scheduler = None


def get_scheduler():
    global _scheduler
    return _scheduler


def init_scheduler():
    global _scheduler
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
        from apscheduler.triggers.interval import IntervalTrigger

        _scheduler = BackgroundScheduler(timezone="UTC")

        _scheduler.add_job(job_daily_assessment, CronTrigger(hour=0, minute=5), id="daily_assessment", name="Daily Warmup Assessment", replace_existing=True)
        _scheduler.add_job(job_peer_warmup_cycle, CronTrigger(hour="9-17", minute=0), id="peer_warmup_cycle", name="Peer Warmup Cycle", replace_existing=True)
        _scheduler.add_job(job_auto_reply_cycle, CronTrigger(hour="9-17", minute=30), id="auto_reply_cycle", name="Auto Reply Cycle", replace_existing=True)
        _scheduler.add_job(job_daily_count_reset, CronTrigger(hour=0, minute=0), id="daily_count_reset", name="Daily Count Reset", replace_existing=True)
        _scheduler.add_job(job_dns_checks, IntervalTrigger(hours=12), id="dns_checks", name="DNS Health Checks", replace_existing=True)
        _scheduler.add_job(job_blacklist_checks, IntervalTrigger(hours=12), id="blacklist_checks", name="Blacklist Checks", replace_existing=True)
        _scheduler.add_job(job_daily_log_snapshot, CronTrigger(hour=23, minute=55), id="daily_log_snapshot", name="Daily Log Snapshot", replace_existing=True)
        _scheduler.add_job(job_auto_recovery_check, CronTrigger(hour=6, minute=0), id="auto_recovery_check", name="Auto Recovery Check", replace_existing=True)

        _scheduler.add_job(job_check_outreach_replies, CronTrigger(hour="8-19", minute="*/15"), id="check_outreach_replies", name="Check Outreach Replies", replace_existing=True)

        _scheduler.add_job(job_daily_backup, CronTrigger(hour=2, minute=0), id="daily_backup", name="Daily Database Backup", replace_existing=True)
        _scheduler.add_job(job_backup_cleanup, CronTrigger(hour=2, minute=30), id="backup_cleanup", name="Backup Cleanup", replace_existing=True)

        _scheduler.add_job(job_lead_sourcing_run, CronTrigger(hour="0,4,8,12,16,20", minute=0), id="lead_sourcing_run", name="Scheduled Lead Sourcing", replace_existing=True)

        _scheduler.add_job(job_campaign_processor, IntervalTrigger(minutes=2), id="campaign_processor", name="Campaign Sequence Processor", replace_existing=True)
        _scheduler.add_job(job_inbox_sync, CronTrigger(hour="8-19", minute="*/5"), id="inbox_sync", name="Inbox Sync", replace_existing=True)
        _scheduler.add_job(job_lead_scoring, CronTrigger(hour=3, minute=0), id="lead_scoring", name="Daily Lead Scoring", replace_existing=True)

        _scheduler.add_job(job_imap_read_cycle, IntervalTrigger(minutes=30), id="imap_read_cycle", name="IMAP Read Emulation", replace_existing=True)
        _scheduler.add_job(job_crm_sync, CronTrigger(hour=4, minute=0), id="crm_sync", name="Nightly CRM Sync", replace_existing=True)
        _scheduler.add_job(job_auto_enrollment, IntervalTrigger(minutes=30), id="auto_enrollment", name="Campaign Auto-Enrollment", replace_existing=True)

        _scheduler.add_job(job_daily_cost_aggregation, CronTrigger(hour=23, minute=45), id="cost_aggregation", name="Daily Cost Aggregation", replace_existing=True)
        _scheduler.add_job(job_monthly_cost_analysis, CronTrigger(day=1, hour=3, minute=30), id="cost_analysis", name="Monthly Cost Analysis", replace_existing=True)

        _scheduler.add_job(job_cleanup_stale_tenants, CronTrigger(hour=3, minute=0), id="cleanup_stale_tenants", name="Cleanup Stale Tenants", replace_existing=True)

        _scheduler.start()
        logger.info("Warmup scheduler started", jobs=len(_scheduler.get_jobs()))
        return _scheduler
    except ImportError:
        logger.warning("APScheduler not installed - scheduler disabled")
        return None
    except Exception as e:
        logger.error("Failed to start scheduler", error=str(e))
        return None


def shutdown_scheduler():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        logger.info("Warmup scheduler stopped")
        _scheduler = None


def _get_db():
    from app.db.base import SessionLocal
    return SessionLocal()


def _is_job_enabled(job_id: str) -> bool:
    """Check master + individual automation toggle (global, not per-tenant)."""
    db = _get_db()
    try:
        from app.core.settings_resolver import get_tenant_setting_bool
        if not get_tenant_setting_bool(db, "automation_master_enabled", default=True):
            return False
        return get_tenant_setting_bool(db, f"automation_{job_id}_enabled", default=True)
    except Exception as e:
        logger.warning("Failed to check job toggle, defaulting to enabled", job_id=job_id, error=str(e))
        return True
    finally:
        db.close()


def _get_active_tenant_ids():
    """Return list of active tenant IDs for per-tenant job iteration."""
    db = _get_db()
    try:
        from app.db.models.tenant import Tenant
        rows = db.query(Tenant.tenant_id).filter(Tenant.is_active == True).all()
        return [r[0] for r in rows]
    except Exception as e:
        logger.warning("Failed to get active tenants, falling back to [1]", error=str(e))
        return [1]
    finally:
        db.close()


# ─── Job functions ───────────────────────────────────────────────────────────


def job_daily_assessment():
    if not _is_job_enabled("daily_assessment"):
        logger.info("Job daily_assessment skipped (disabled)")
        return
    logger.info("Running daily warmup assessment")
    db = _get_db()
    try:
        from app.services.pipelines.warmup_engine import run_warmup_assessment
        result = run_warmup_assessment(triggered_by="scheduler")
        logger.info("Daily assessment complete", result=result)
    except Exception as e:
        logger.error("Daily assessment failed", error=str(e))
    finally:
        db.close()


def job_peer_warmup_cycle():
    if not _is_job_enabled("peer_warmup_cycle"):
        logger.info("Job peer_warmup_cycle skipped (disabled)")
        return
    logger.info("Running peer warmup cycle")
    for tid in _get_active_tenant_ids():
        db = _get_db()
        try:
            from app.services.warmup.peer_warmup import run_peer_warmup_cycle
            result = run_peer_warmup_cycle(db, tenant_id=tid)
            logger.info("Peer warmup cycle complete", tenant_id=tid, result=result)
        except Exception as e:
            logger.error("Peer warmup cycle failed", tenant_id=tid, error=str(e))
        finally:
            db.close()


def job_auto_reply_cycle():
    if not _is_job_enabled("auto_reply_cycle"):
        logger.info("Job auto_reply_cycle skipped (disabled)")
        return
    logger.info("Running auto-reply cycle")
    for tid in _get_active_tenant_ids():
        db = _get_db()
        try:
            from app.services.warmup.peer_warmup import run_auto_reply_cycle
            result = run_auto_reply_cycle(db, tenant_id=tid)
            logger.info("Auto-reply cycle complete", tenant_id=tid, result=result)
        except Exception as e:
            logger.error("Auto-reply cycle failed", tenant_id=tid, error=str(e))
        finally:
            db.close()


def job_daily_count_reset():
    if not _is_job_enabled("daily_count_reset"):
        logger.info("Job daily_count_reset skipped (disabled)")
        return
    logger.info("Resetting daily email counts")
    db = _get_db()
    try:
        from app.db.models.sender_mailbox import SenderMailbox
        db.query(SenderMailbox).update({SenderMailbox.emails_sent_today: 0}, synchronize_session=False)
        db.commit()
        logger.info("Daily count reset complete")
        # Reset campaign auto-enrollment daily counters
        from app.db.models.campaign import Campaign
        db.query(Campaign).update({Campaign.auto_enrolled_today: 0}, synchronize_session=False)
        db.commit()
        logger.info("Campaign auto-enrollment daily counters reset")
    except Exception as e:
        logger.error("Daily count reset failed", error=str(e))
    finally:
        db.close()


def job_dns_checks():
    if not _is_job_enabled("dns_checks"):
        logger.info("Job dns_checks skipped (disabled)")
        return
    logger.info("Running DNS health checks")
    db = _get_db()
    try:
        from app.db.models.sender_mailbox import SenderMailbox, WarmupStatus
        from app.services.warmup.dns_checker import run_dns_health_check
        mailboxes = db.query(SenderMailbox).filter(
            SenderMailbox.warmup_status.in_([WarmupStatus.WARMING_UP, WarmupStatus.RECOVERING, WarmupStatus.COLD_READY, WarmupStatus.ACTIVE]),
            SenderMailbox.is_active == True,
        ).all()
        for mb in mailboxes:
            try:
                run_dns_health_check(mb.mailbox_id, db, tenant_id=mb.tenant_id)
            except Exception as e:
                logger.error("DNS check failed", mailbox=mb.email, error=str(e))
    except Exception as e:
        logger.error("DNS checks failed", error=str(e))
    finally:
        db.close()


def job_blacklist_checks():
    if not _is_job_enabled("blacklist_checks"):
        logger.info("Job blacklist_checks skipped (disabled)")
        return
    logger.info("Running blacklist checks")
    db = _get_db()
    try:
        from app.db.models.sender_mailbox import SenderMailbox, WarmupStatus
        from app.services.warmup.blacklist_monitor import run_blacklist_check
        mailboxes = db.query(SenderMailbox).filter(
            SenderMailbox.warmup_status.in_([WarmupStatus.WARMING_UP, WarmupStatus.RECOVERING, WarmupStatus.COLD_READY, WarmupStatus.ACTIVE]),
            SenderMailbox.is_active == True,
        ).all()
        for mb in mailboxes:
            try:
                run_blacklist_check(mb.mailbox_id, db, tenant_id=mb.tenant_id)
            except Exception as e:
                logger.error("Blacklist check failed", mailbox=mb.email, error=str(e))
    except Exception as e:
        logger.error("Blacklist checks failed", error=str(e))
    finally:
        db.close()


def job_daily_log_snapshot():
    if not _is_job_enabled("daily_log_snapshot"):
        logger.info("Job daily_log_snapshot skipped (disabled)")
        return
    logger.info("Taking daily log snapshot")
    db = _get_db()
    try:
        from app.db.models.sender_mailbox import SenderMailbox
        from app.db.models.warmup_daily_log import WarmupDailyLog
        from app.services.pipelines.warmup_engine import calculate_health_score, load_warmup_config, get_warmup_phase

        today = date.today()
        mailboxes = db.query(SenderMailbox).filter(SenderMailbox.is_active == True).all()
        # Cache warmup config per tenant to avoid repeated DB queries
        _config_cache = {}
        for mb in mailboxes:
            existing = db.query(WarmupDailyLog).filter(WarmupDailyLog.mailbox_id == mb.mailbox_id, WarmupDailyLog.log_date == today).first()
            if existing:
                continue
            tid = mb.tenant_id
            if tid not in _config_cache:
                _config_cache[tid] = load_warmup_config(db, tenant_id=tid)
            config = _config_cache[tid]
            health = calculate_health_score(mb, config)
            total_sent = mb.total_emails_sent or 0
            bounce_rate = (mb.bounce_count / total_sent * 100) if total_sent > 0 else 0
            reply_rate = (mb.reply_count / total_sent * 100) if total_sent > 0 else 0
            day = mb.warmup_days_completed or 0
            phase = 1 if day == 0 else 0
            if day > 0:
                phase, _ = get_warmup_phase(day, config)
            log = WarmupDailyLog(
                mailbox_id=mb.mailbox_id, log_date=today, emails_sent=mb.emails_sent_today,
                emails_received=mb.warmup_emails_received or 0, opens=mb.warmup_opens or 0,
                replies=mb.warmup_replies or 0, bounces=mb.bounce_count,
                health_score=health["health_score"], warmup_day=day, phase=phase,
                daily_limit=mb.daily_send_limit, bounce_rate=round(bounce_rate, 2),
                reply_rate=round(reply_rate, 2), blacklisted=mb.is_blacklisted or False,
            )
            db.add(log)
        db.commit()
        logger.info("Daily log snapshot complete")
    except Exception as e:
        logger.error("Daily log snapshot failed", error=str(e))
    finally:
        db.close()


def job_auto_recovery_check():
    if not _is_job_enabled("auto_recovery_check"):
        logger.info("Job auto_recovery_check skipped (disabled)")
        return
    logger.info("Running auto-recovery check")
    for tid in _get_active_tenant_ids():
        db = _get_db()
        try:
            from app.services.warmup.auto_recovery import run_auto_recovery_check
            result = run_auto_recovery_check(db, tenant_id=tid)
            logger.info("Auto-recovery check complete", tenant_id=tid, result=result)
        except Exception as e:
            logger.error("Auto-recovery check failed", tenant_id=tid, error=str(e))
        finally:
            db.close()


def job_check_outreach_replies():
    if not _is_job_enabled("check_outreach_replies"):
        logger.info("Job check_outreach_replies skipped (disabled)")
        return
    logger.info("Running outreach reply check")
    db = _get_db()
    try:
        from app.services.reply_tracker import check_all_mailbox_replies
        result = check_all_mailbox_replies(db)
        logger.info("Outreach reply check complete", result=result)
        from app.services.automation_logger import log_automation_event
        replies_found = result.get("replies_found", 0) if isinstance(result, dict) else 0
        if replies_found > 0:
            log_automation_event(db, "reply_detected", f"Detected {replies_found} new replies", details=result)
    except Exception as e:
        logger.error("Outreach reply check failed", error=str(e))
        try:
            from app.services.automation_logger import log_automation_event
            log_automation_event(db, "reply_detected", f"Reply check failed: {str(e)[:100]}", status="error")
        except Exception:
            pass
    finally:
        db.close()


def job_lead_sourcing_run():
    if not _is_job_enabled("lead_sourcing_run"):
        logger.info("Job lead_sourcing_run skipped (disabled)")
        return
    logger.info("Running scheduled lead sourcing pipeline")
    for tid in _get_active_tenant_ids():
        db = _get_db()
        try:
            from app.services.pipelines.lead_sourcing import run_lead_sourcing_pipeline
            result = run_lead_sourcing_pipeline(sources=["auto"], triggered_by="scheduler", tenant_id=tid)
            logger.info("Scheduled lead sourcing complete",
                        tenant_id=tid,
                        inserted=result.get("inserted", 0),
                        skipped=result.get("skipped", 0),
                        sources=result.get("sources_used", []))
            from app.services.automation_logger import log_automation_event
            inserted = result.get("inserted", 0)
            log_automation_event(db, "lead_sourcing", f"Lead sourcing: {inserted} leads found", details=result)

            # Auto-chain: sourcing → enrichment → validation
            _run_auto_chain(db, inserted, tenant_id=tid)
        except Exception as e:
            logger.error("Scheduled lead sourcing failed", tenant_id=tid, error=str(e))
            try:
                from app.services.automation_logger import log_automation_event
                log_automation_event(db, "lead_sourcing", f"Lead sourcing failed: {str(e)[:100]}", status="error")
            except Exception:
                pass
        finally:
            db.close()


def _run_auto_chain(db, leads_inserted: int, tenant_id: int = None):
    """Auto-chain: lead sourcing → contact enrichment → email validation."""
    from app.services.automation_logger import log_automation_event
    from app.core.settings_resolver import get_tenant_setting_bool

    if leads_inserted <= 0:
        return

    # Chain step 1: enrichment
    if not get_tenant_setting_bool(db, "automation_chain_enrichment", tenant_id=tenant_id, default=False):
        return

    logger.info("Auto-chain: starting contact enrichment", leads_inserted=leads_inserted, tenant_id=tenant_id)
    try:
        from app.services.pipelines.contact_enrichment import run_contact_enrichment_pipeline
        enrich_result = run_contact_enrichment_pipeline(triggered_by="auto_chain", tenant_id=tenant_id)
        contacts_found = enrich_result.get("contacts_found", 0) if isinstance(enrich_result, dict) else 0
        logger.info("Auto-chain: enrichment complete", contacts_found=contacts_found)
        log_automation_event(
            db, "auto_chain",
            f"Auto-chain enrichment: {contacts_found} contacts found",
            details=enrich_result, source="auto_chain",
        )
    except Exception as e:
        logger.error("Auto-chain enrichment failed", error=str(e))
        log_automation_event(
            db, "auto_chain",
            f"Auto-chain enrichment failed: {str(e)[:100]}",
            status="error", source="auto_chain",
        )
        return

    # Chain step 2: validation
    if contacts_found <= 0:
        return
    if not get_tenant_setting_bool(db, "automation_chain_validation", tenant_id=tenant_id, default=False):
        return

    logger.info("Auto-chain: starting email validation", contacts_found=contacts_found, tenant_id=tenant_id)
    try:
        from app.services.pipelines.email_validation import run_email_validation_pipeline
        valid_result = run_email_validation_pipeline(triggered_by="auto_chain", tenant_id=tenant_id)
        validated = valid_result.get("validated", 0) if isinstance(valid_result, dict) else 0
        logger.info("Auto-chain: validation complete", validated=validated)
        log_automation_event(
            db, "auto_chain",
            f"Auto-chain validation: {validated} emails validated",
            details=valid_result, source="auto_chain",
        )
    except Exception as e:
        logger.error("Auto-chain validation failed", error=str(e))
        log_automation_event(
            db, "auto_chain",
            f"Auto-chain validation failed: {str(e)[:100]}",
            status="error", source="auto_chain",
        )

    # Chain step 3: enrollment
    if validated <= 0:
        return
    if not get_tenant_setting_bool(db, "automation_chain_enrollment", tenant_id=tenant_id, default=False):
        return

    logger.info("Auto-chain: starting campaign auto-enrollment", validated=validated, tenant_id=tenant_id)
    try:
        from app.services.auto_enrollment import run_auto_enrollment
        enroll_result = run_auto_enrollment(db)
        total_enrolled = enroll_result.get("total_enrolled", 0)
        logger.info("Auto-chain: enrollment complete", total_enrolled=total_enrolled)
        log_automation_event(
            db, "auto_chain",
            f"Auto-chain enrollment: {total_enrolled} contacts enrolled",
            details=enroll_result, source="auto_chain",
        )
    except Exception as e:
        logger.error("Auto-chain enrollment failed", error=str(e))
        log_automation_event(
            db, "auto_chain",
            f"Auto-chain enrollment failed: {str(e)[:100]}",
            status="error", source="auto_chain",
        )


def job_daily_backup():
    if not _is_job_enabled("daily_backup"):
        logger.info("Job daily_backup skipped (disabled)")
        return
    logger.info("Running daily database backup")
    try:
        from app.services.backup_service import create_backup
        result = create_backup()
        logger.info("Daily backup complete", filename=result["filename"], size=result["size_human"])
    except Exception as e:
        logger.error("Daily backup failed", error=str(e))


def job_backup_cleanup():
    if not _is_job_enabled("backup_cleanup"):
        logger.info("Job backup_cleanup skipped (disabled)")
        return
    logger.info("Running backup cleanup")
    db = _get_db()
    try:
        from app.core.settings_resolver import get_tenant_setting
        retention = get_tenant_setting(db, "backup_retention_days", default=3)
        from app.services.backup_service import cleanup_old_backups
        deleted = cleanup_old_backups(int(retention))
        logger.info("Backup cleanup complete", deleted_count=deleted, retention_days=retention)
    except Exception as e:
        logger.error("Backup cleanup failed", error=str(e))
    finally:
        db.close()


def job_campaign_processor():
    if not _is_job_enabled("campaign_processor"):
        logger.info("Job campaign_processor skipped (disabled)")
        return
    logger.info("Running campaign sequence processor")
    db = _get_db()
    try:
        from app.services.campaign_engine import process_campaign_queue
        result = process_campaign_queue(db)
        logger.info("Campaign processor complete", result=result)
        from app.services.automation_logger import log_automation_event
        log_automation_event(db, "campaign_send", f"Campaign processor ran", details=result)
    except Exception as e:
        logger.error("Campaign processor failed", error=str(e))
        try:
            from app.services.automation_logger import log_automation_event
            log_automation_event(db, "campaign_send", f"Campaign processor failed: {str(e)[:100]}", status="error")
        except Exception:
            pass
    finally:
        db.close()


def job_inbox_sync():
    if not _is_job_enabled("inbox_sync"):
        logger.info("Job inbox_sync skipped (disabled)")
        return
    logger.info("Running inbox sync")
    db = _get_db()
    try:
        from app.services.inbox_syncer import sync_inbox
        result = sync_inbox(db)
        logger.info("Inbox sync complete", result=result)
        from app.services.automation_logger import log_automation_event
        sent = result.get("sent_synced", 0)
        replies = result.get("replies_synced", 0)
        if sent > 0 or replies > 0:
            log_automation_event(db, "inbox_sync", f"Inbox sync: {sent} sent, {replies} replies synced", details=result)
    except Exception as e:
        logger.error("Inbox sync failed", error=str(e))
        try:
            from app.services.automation_logger import log_automation_event
            log_automation_event(db, "inbox_sync", f"Inbox sync failed: {str(e)[:100]}", status="error")
        except Exception:
            pass
    finally:
        db.close()


def job_lead_scoring():
    if not _is_job_enabled("lead_scoring"):
        logger.info("Job lead_scoring skipped (disabled)")
        return
    logger.info("Running daily lead scoring")
    db = _get_db()
    try:
        from app.services.lead_scorer import recalculate_all_scores
        result = recalculate_all_scores(db)
        logger.info("Lead scoring complete", result=result)
    except Exception as e:
        logger.error("Lead scoring failed", error=str(e))
    finally:
        db.close()


def job_imap_read_cycle():
    if not _is_job_enabled("imap_read_cycle"):
        logger.info("Job imap_read_cycle skipped (disabled)")
        return
    logger.info("Running IMAP read emulation cycle")
    db = _get_db()
    try:
        from app.services.warmup.imap_reader import run_imap_read_cycle
        result = run_imap_read_cycle(db)
        logger.info("IMAP read cycle complete", result=result)
    except Exception as e:
        logger.error("IMAP read cycle failed", error=str(e))
    finally:
        db.close()


def job_crm_sync():
    if not _is_job_enabled("crm_sync"):
        logger.info("Job crm_sync skipped (disabled)")
        return
    logger.info("Running nightly CRM sync")
    for tid in _get_active_tenant_ids():
        db = _get_db()
        try:
            from app.services.crm_sync_engine import run_crm_sync
            result = run_crm_sync(db, tenant_id=tid)
            logger.info("CRM sync complete", tenant_id=tid, result=result)
            from app.services.automation_logger import log_automation_event
            log_automation_event(db, "crm_sync", "Nightly CRM sync completed", details=result)
        except Exception as e:
            logger.error("CRM sync failed", tenant_id=tid, error=str(e))
        finally:
            db.close()


def job_auto_enrollment():
    if not _is_job_enabled("auto_enrollment"):
        logger.info("Job auto_enrollment skipped (disabled)")
        return
    logger.info("Running campaign auto-enrollment")
    db = _get_db()
    try:
        from app.services.auto_enrollment import run_auto_enrollment
        result = run_auto_enrollment(db)
        logger.info("Auto-enrollment complete", result=result)
        from app.services.automation_logger import log_automation_event
        total = result.get("total_enrolled", 0)
        if total > 0:
            log_automation_event(db, "auto_enrollment", f"Auto-enrollment: {total} contacts enrolled", details=result)
    except Exception as e:
        logger.error("Auto-enrollment failed", error=str(e))
        try:
            from app.services.automation_logger import log_automation_event
            log_automation_event(db, "auto_enrollment", f"Auto-enrollment failed: {str(e)[:100]}", status="error")
        except Exception:
            pass
    finally:
        db.close()


def job_daily_cost_aggregation():
    if not _is_job_enabled("cost_aggregation"):
        logger.info("Job cost_aggregation skipped (disabled)")
        return
    logger.info("Running daily cost aggregation")
    db = _get_db()
    try:
        from app.services.cost_tracker import aggregate_daily_costs
        result = aggregate_daily_costs(db)
        logger.info("Daily cost aggregation complete", total_cost=result.get("total_cost", 0))
    except Exception as e:
        logger.error("Daily cost aggregation failed", error=str(e))
    finally:
        db.close()


def job_monthly_cost_analysis():
    if not _is_job_enabled("cost_analysis"):
        logger.info("Job cost_analysis skipped (disabled)")
        return
    logger.info("Running monthly cost analysis")
    db = _get_db()
    try:
        from app.services.cost_tracker import generate_monthly_analysis
        result = generate_monthly_analysis(db)
        suggestions = result.get("suggestions", [])
        logger.info("Monthly cost analysis complete", suggestions=len(suggestions))
    except Exception as e:
        logger.error("Monthly cost analysis failed", error=str(e))
    finally:
        db.close()


def job_cleanup_stale_tenants():
    """Delete unverified users and empty tenants older than 72 hours. Runs daily at 3 AM UTC."""
    if not _is_job_enabled("cleanup_stale_tenants"):
        logger.info("Job cleanup_stale_tenants skipped (disabled)")
        return
    logger.info("Running stale tenant cleanup")
    from app.db.session import SessionLocal
    from app.db.models.user import User
    from app.db.models.tenant import Tenant
    from datetime import datetime, timedelta

    db = SessionLocal()
    try:
        cutoff = datetime.utcnow() - timedelta(hours=72)

        # Delete unverified users older than 72 hours
        stale_users = db.query(User).filter(
            User.is_verified == False,
            User.created_at < cutoff,
        ).all()

        deleted_users = 0
        for user in stale_users:
            db.delete(user)
            deleted_users += 1

        # Find and deactivate empty tenants (no active users) older than 72 hours
        # Skip Tenant #1 (system tenant)
        from sqlalchemy import func
        tenants_with_users = db.query(User.tenant_id).filter(User.is_active == True).distinct().subquery()
        empty_tenants = db.query(Tenant).filter(
            Tenant.tenant_id != 1,
            Tenant.is_active == True,
            ~Tenant.tenant_id.in_(db.query(tenants_with_users)),
        ).all()

        deactivated_tenants = 0
        for tenant in empty_tenants:
            tenant.is_active = False
            deactivated_tenants += 1

        db.commit()

        if deleted_users or deactivated_tenants:
            logger.info("Tenant cleanup complete",
                       deleted_users=deleted_users,
                       deactivated_tenants=deactivated_tenants)
    except Exception as e:
        logger.error("Tenant cleanup failed", error=str(e))
        db.rollback()
    finally:
        db.close()


def get_scheduler_status() -> dict:
    if not _scheduler:
        return {"running": False, "jobs": []}
    jobs = []
    for job in _scheduler.get_jobs():
        jobs.append({"id": job.id, "name": job.name, "next_run": str(job.next_run_time) if job.next_run_time else None})
    return {"running": _scheduler.running, "jobs": jobs}
