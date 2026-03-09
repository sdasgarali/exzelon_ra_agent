"""APScheduler Integration - background job scheduler for warmup tasks."""
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

        _scheduler.add_job(job_lead_sourcing_run, CronTrigger(hour="6,12,18", minute=0), id="lead_sourcing_run", name="Scheduled Lead Sourcing", replace_existing=True)

        _scheduler.add_job(job_campaign_processor, IntervalTrigger(minutes=2), id="campaign_processor", name="Campaign Sequence Processor", replace_existing=True)
        _scheduler.add_job(job_inbox_sync, CronTrigger(hour="8-19", minute="*/5"), id="inbox_sync", name="Inbox Sync", replace_existing=True)
        _scheduler.add_job(job_lead_scoring, CronTrigger(hour=3, minute=0), id="lead_scoring", name="Daily Lead Scoring", replace_existing=True)

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


def job_daily_assessment():
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
    logger.info("Running peer warmup cycle")
    db = _get_db()
    try:
        from app.services.warmup.peer_warmup import run_peer_warmup_cycle
        result = run_peer_warmup_cycle(db)
        logger.info("Peer warmup cycle complete", result=result)
    except Exception as e:
        logger.error("Peer warmup cycle failed", error=str(e))
    finally:
        db.close()




def job_auto_reply_cycle():
    logger.info("Running auto-reply cycle")
    db = _get_db()
    try:
        from app.services.warmup.peer_warmup import run_auto_reply_cycle
        result = run_auto_reply_cycle(db)
        logger.info("Auto-reply cycle complete", result=result)
    except Exception as e:
        logger.error("Auto-reply cycle failed", error=str(e))
    finally:
        db.close()


def job_daily_count_reset():
    logger.info("Resetting daily email counts")
    db = _get_db()
    try:
        from app.db.models.sender_mailbox import SenderMailbox
        db.query(SenderMailbox).update({SenderMailbox.emails_sent_today: 0}, synchronize_session=False)
        db.commit()
        logger.info("Daily count reset complete")
    except Exception as e:
        logger.error("Daily count reset failed", error=str(e))
    finally:
        db.close()


def job_dns_checks():
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
                run_dns_health_check(mb.mailbox_id, db)
            except Exception as e:
                logger.error("DNS check failed", mailbox=mb.email, error=str(e))
    except Exception as e:
        logger.error("DNS checks failed", error=str(e))
    finally:
        db.close()


def job_blacklist_checks():
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
                run_blacklist_check(mb.mailbox_id, db)
            except Exception as e:
                logger.error("Blacklist check failed", mailbox=mb.email, error=str(e))
    except Exception as e:
        logger.error("Blacklist checks failed", error=str(e))
    finally:
        db.close()


def job_daily_log_snapshot():
    logger.info("Taking daily log snapshot")
    db = _get_db()
    try:
        from app.db.models.sender_mailbox import SenderMailbox
        from app.db.models.warmup_daily_log import WarmupDailyLog
        from app.services.pipelines.warmup_engine import calculate_health_score, load_warmup_config, get_warmup_phase

        config = load_warmup_config(db)
        today = date.today()
        mailboxes = db.query(SenderMailbox).filter(SenderMailbox.is_active == True).all()
        for mb in mailboxes:
            existing = db.query(WarmupDailyLog).filter(WarmupDailyLog.mailbox_id == mb.mailbox_id, WarmupDailyLog.log_date == today).first()
            if existing:
                continue
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
    logger.info("Running auto-recovery check")
    db = _get_db()
    try:
        from app.services.warmup.auto_recovery import run_auto_recovery_check
        result = run_auto_recovery_check(db)
        logger.info("Auto-recovery check complete", result=result)
    except Exception as e:
        logger.error("Auto-recovery check failed", error=str(e))
    finally:
        db.close()


def job_check_outreach_replies():
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
    logger.info("Running scheduled lead sourcing pipeline")
    db = _get_db()
    try:
        from app.services.pipelines.lead_sourcing import run_lead_sourcing_pipeline
        result = run_lead_sourcing_pipeline(sources=["auto"], triggered_by="scheduler")
        logger.info("Scheduled lead sourcing complete",
                    inserted=result.get("inserted", 0),
                    skipped=result.get("skipped", 0),
                    sources=result.get("sources_used", []))
        from app.services.automation_logger import log_automation_event
        inserted = result.get("inserted", 0)
        log_automation_event(db, "lead_sourcing", f"Lead sourcing: {inserted} leads found", details=result)
    except Exception as e:
        logger.error("Scheduled lead sourcing failed", error=str(e))
        try:
            from app.services.automation_logger import log_automation_event
            log_automation_event(db, "lead_sourcing", f"Lead sourcing failed: {str(e)[:100]}", status="error")
        except Exception:
            pass
    finally:
        db.close()


def job_daily_backup():
    logger.info("Running daily database backup")
    try:
        from app.services.backup_service import create_backup
        result = create_backup()
        logger.info("Daily backup complete", filename=result["filename"], size=result["size_human"])
    except Exception as e:
        logger.error("Daily backup failed", error=str(e))


def job_backup_cleanup():
    logger.info("Running backup cleanup")
    db = _get_db()
    try:
        from app.core.config import get_setting
        retention = get_setting(db, "backup_retention_days", 3)
        from app.services.backup_service import cleanup_old_backups
        deleted = cleanup_old_backups(int(retention))
        logger.info("Backup cleanup complete", deleted_count=deleted, retention_days=retention)
    except Exception as e:
        logger.error("Backup cleanup failed", error=str(e))
    finally:
        db.close()


def job_campaign_processor():
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


def get_scheduler_status() -> dict:
    if not _scheduler:
        return {"running": False, "jobs": []}
    jobs = []
    for job in _scheduler.get_jobs():
        jobs.append({"id": job.id, "name": job.name, "next_run": str(job.next_run_time) if job.next_run_time else None})
    return {"running": _scheduler.running, "jobs": jobs}
