"""Main FastAPI application."""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, Response
import structlog

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.config import settings
from app.core.exceptions import AppException
from app.api.router import api_router
from app.db.base import engine, Base

structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


def _seed_warmup_profiles():
    import json
    from app.db.base import SessionLocal
    from app.db.models.warmup_profile import WarmupProfile
    db = SessionLocal()
    try:
        existing = db.query(WarmupProfile).filter(WarmupProfile.is_system == True).count()
        if existing > 0:
            return
        profiles = [
            {
                "name": "Conservative",
                "description": "Slow and safe warmup over 45 days. Best for new domains.",
                "config_json": json.dumps({
                    "total_days": 45,
                    "phase_1": {"days": 10, "min_emails": 1, "max_emails": 3},
                    "phase_2": {"days": 10, "min_emails": 3, "max_emails": 8},
                    "phase_3": {"days": 10, "min_emails": 8, "max_emails": 15},
                    "phase_4": {"days": 15, "min_emails": 15, "max_emails": 25},
                }),
            },
            {
                "name": "Standard",
                "description": "Balanced warmup over 30 days. Recommended for most use cases.",
                "is_default": True,
                "config_json": json.dumps({
                    "total_days": 30,
                    "phase_1": {"days": 7, "min_emails": 2, "max_emails": 5},
                    "phase_2": {"days": 7, "min_emails": 5, "max_emails": 15},
                    "phase_3": {"days": 7, "min_emails": 15, "max_emails": 25},
                    "phase_4": {"days": 9, "min_emails": 25, "max_emails": 35},
                }),
            },
            {
                "name": "Aggressive",
                "description": "Fast warmup over 20 days. For established domains with good reputation.",
                "config_json": json.dumps({
                    "total_days": 20,
                    "phase_1": {"days": 5, "min_emails": 3, "max_emails": 8},
                    "phase_2": {"days": 5, "min_emails": 8, "max_emails": 20},
                    "phase_3": {"days": 5, "min_emails": 20, "max_emails": 35},
                    "phase_4": {"days": 5, "min_emails": 35, "max_emails": 50},
                }),
            },
        ]
        for p in profiles:
            profile = WarmupProfile(
                name=p["name"],
                description=p["description"],
                is_system=True,
                is_default=p.get("is_default", False),
                config_json=p["config_json"],
            )
            db.add(profile)
        db.commit()
        logger.info("Seeded 3 system warmup profiles")
    except Exception as e:
        logger.error("Failed to seed warmup profiles", error=str(e))
    finally:
        db.close()


def _seed_default_email_template():
    """Seed the default Exzelon outreach email template if none exists."""
    from app.db.base import SessionLocal
    from app.db.models.email_template import EmailTemplate, TemplateStatus
    db = SessionLocal()
    try:
        existing = db.query(EmailTemplate).filter(EmailTemplate.is_default == True).first()
        if existing:
            return

        default_subject = "Free candidate preview for {{job_title}} position"

        default_body_html = (
            '<div style=\"font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; color: #333;\">\n'
            '  <p>Hi {{contact_first_name}},</p>\n'
            '  \n'
            '  <p>My name is {{sender_first_name}} from <strong>Exzelon Consulting Inc.</strong></p>\n'
            '  \n'
            '  <p>I noticed {{company_name}} is hiring for the <strong>{{job_title}}</strong> position in <strong>{{job_location}}</strong>. We specialize in connecting companies with top-tier talent and would love to help you find the perfect candidate.</p>\n'
            '  \n'
            '  <p>We offer a <strong>free candidate preview</strong> &#8212; no commitment required. Just let us know your requirements, and we\'ll present pre-screened profiles that match your needs.</p>\n'
            '  \n'
            '  <p><strong>Why Exzelon?</strong></p>\n'
            '  <ul style=\"padding-left: 20px;\">\n'
            '    <li>Pre-vetted, interview-ready candidates</li>\n'
            '    <li>Quick turnaround -- profiles within 48 hours</li>\n'
            '    <li>No upfront cost -- pay only when you hire</li>\n'
            '    <li>Specialists in IT, Engineering, Healthcare, and more</li>\n'
            '  </ul>\n'
            '  \n'
            '  <p>Would you be open to a quick 10-minute call this week to discuss how we can support your hiring needs?</p>\n'
            '  \n'
            '  <p>Looking forward to hearing from you.</p>\n'
            '  \n'
            '  <p>Best regards,</p>\n'
            '  \n'
            '  {{signature}}\n'
            '  \n'
            '  <div style=\"margin-top: 20px; text-align: left;\">\n'
            '    <img src=\"{{logo_url}}\" alt=\"Exzelon Consulting Inc.\" style=\"max-width: 150px; height: auto;\" />\n'
            '  </div>\n'
            '  \n'
            '  <hr style=\"border: none; border-top: 1px solid #eee; margin-top: 20px;\" />\n'
            '  <p style=\"font-size: 11px; color: #999;\">{{unsubscribe_link}}</p>\n'
            '</div>'
        )

        default_body_text = (
            "Hi {{contact_first_name}},\n"
            "\n"
            "My name is {{sender_first_name}} from Exzelon Consulting Inc.\n"
            "\n"
            "I noticed {{company_name}} is hiring for the {{job_title}} position in {{job_location}}. We specialize in connecting companies with top-tier talent and would love to help you find the perfect candidate.\n"
            "\n"
            "We offer a free candidate preview -- no commitment required. Just let us know your requirements, and we'll present pre-screened profiles that match your needs.\n"
            "\n"
            "Why Exzelon?\n"
            "- Pre-vetted, interview-ready candidates\n"
            "- Quick turnaround -- profiles within 48 hours\n"
            "- No upfront cost -- pay only when you hire\n"
            "- Specialists in IT, Engineering, Healthcare, and more\n"
            "\n"
            "Would you be open to a quick 10-minute call this week to discuss how we can support your hiring needs?\n"
            "\n"
            "Looking forward to hearing from you.\n"
            "\n"
            "Best regards,\n"
            "{{sender_first_name}}\n"
            "\n"
            "{{unsubscribe_link}}"
        )

        template = EmailTemplate(
            name="Exzelon Default Outreach",
            subject=default_subject,
            body_html=default_body_html,
            body_text=default_body_text,
            status=TemplateStatus.ACTIVE,
            is_default=True,
            description="Default Exzelon Consulting outreach template with free candidate preview offer.",
        )
        db.add(template)
        db.commit()
        logger.info("Seeded default email template")
    except Exception as e:
        logger.error("Failed to seed default email template", error=str(e))
    finally:
        db.close()


def _seed_deal_stages():
    """Seed default CRM deal pipeline stages if none exist."""
    from app.db.base import SessionLocal
    from app.db.models.deal import DealStage
    db = SessionLocal()
    try:
        existing = db.query(DealStage).count()
        if existing > 0:
            return
        stages = [
            {"name": "New Lead", "stage_order": 1, "color": "#6366f1"},
            {"name": "Contacted", "stage_order": 2, "color": "#3b82f6"},
            {"name": "Qualified", "stage_order": 3, "color": "#0ea5e9"},
            {"name": "Proposal", "stage_order": 4, "color": "#f59e0b"},
            {"name": "Negotiation", "stage_order": 5, "color": "#f97316"},
            {"name": "Won", "stage_order": 6, "color": "#22c55e", "is_won": True},
            {"name": "Lost", "stage_order": 7, "color": "#ef4444", "is_lost": True},
        ]
        for s in stages:
            db.add(DealStage(
                name=s["name"],
                stage_order=s["stage_order"],
                color=s["color"],
                is_won=s.get("is_won", False),
                is_lost=s.get("is_lost", False),
            ))
        db.commit()
        logger.info("Seeded 7 default deal pipeline stages")
    except Exception as e:
        logger.error("Failed to seed deal stages", error=str(e))
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting application", app_name=settings.APP_NAME, env=settings.APP_ENV)
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        # With multiple workers, race conditions can cause "table already exists" errors
        if "already exists" in str(e):
            logger.warning("Table creation race condition (harmless)", error=str(e))
        else:
            raise
    logger.info("Database tables created/verified")

    # Validate database schema
    try:
        from sqlalchemy import inspect as sa_inspect_schema
        inspector = sa_inspect_schema(engine)
        existing_tables = set(inspector.get_table_names())
        required_tables = {
            "users", "lead_details", "contact_details", "lead_contact_associations",
            "client_info", "sender_mailboxes", "outreach_events", "email_templates",
            "warmup_profiles", "job_runs", "audit_logs",
            "campaigns", "sequence_steps", "campaign_contacts",
            "inbox_messages", "webhooks", "webhook_deliveries",
            "deals", "deal_stages", "deal_activities", "api_keys",
        }
        missing = required_tables - existing_tables
        if missing:
            logger.warning("Missing database tables", missing=list(missing))
        else:
            logger.info("Database schema validated", tables=len(existing_tables))
    except Exception as e:
        logger.warning(f"Schema validation check: {e}")

    # Migration: ensure role enum includes super_admin
    try:
        from sqlalchemy import text as sa_text_role
        if settings.DB_TYPE == "mysql":
            with engine.connect() as conn:
                try:
                    conn.execute(sa_text_role(
                        "ALTER TABLE users MODIFY COLUMN role "
                        "ENUM('super_admin','admin','operator','viewer') "
                        "NOT NULL DEFAULT 'viewer'"
                    ))
                    conn.commit()
                    logger.info("Migration: updated UserRole enum to super_admin/admin/operator/viewer")
                except Exception as e2:
                    logger.debug(f"Role enum migration (may already be done): {e2}")
    except Exception as e:
        logger.warning(f"Migration check for role enum: {e}")

    # Migration: add lead_results_json column if missing
    try:
        from sqlalchemy import text as sa_text
        with engine.connect() as conn:
            try:
                conn.execute(sa_text("SELECT lead_results_json FROM job_runs LIMIT 1"))
            except Exception:
                conn.execute(sa_text("ALTER TABLE job_runs ADD COLUMN lead_results_json TEXT"))
                conn.commit()
                logger.info("Migration: added lead_results_json column to job_runs")
    except Exception as e:
        logger.warning(f"Migration check for lead_results_json: {e}")

    # Migration: add summary_json column to job_runs if missing
    try:
        from sqlalchemy import text as sa_text_summary
        with engine.connect() as conn:
            try:
                conn.execute(sa_text_summary("SELECT summary_json FROM job_runs LIMIT 1"))
            except Exception:
                conn.execute(sa_text_summary("ALTER TABLE job_runs ADD COLUMN summary_json TEXT"))
                conn.commit()
                logger.info("Migration: added summary_json column to job_runs")
    except Exception as e:
        logger.warning(f"Migration check for summary_json: {e}")

    # Migration: add is_archived column to all tables if missing
    try:
        from sqlalchemy import text as sa_text2, inspect as sa_inspect
        with engine.connect() as conn:
            inspector = sa_inspect(engine)
            tables_to_migrate = inspector.get_table_names()
            for tbl in tables_to_migrate:
                cols = [c["name"] for c in inspector.get_columns(tbl)]
                if "is_archived" not in cols:
                    try:
                        conn.execute(sa_text2(f"ALTER TABLE {tbl} ADD COLUMN is_archived BOOLEAN DEFAULT 0 NOT NULL"))
                        conn.commit()
                        logger.info(f"Migration: added is_archived column to {tbl}")
                    except Exception:
                        pass
    except Exception as e:
        logger.warning(f"Migration check for is_archived: {e}")

    # Migration: add unsubscribe columns
    try:
        from sqlalchemy import text as sa_text_unsub, inspect as sa_inspect_unsub
        with engine.connect() as conn:
            inspector_unsub = sa_inspect_unsub(engine)

            contact_cols = [c["name"] for c in inspector_unsub.get_columns("contact_details")]
            if "outreach_status" not in contact_cols:
                conn.execute(sa_text_unsub("ALTER TABLE contact_details ADD COLUMN outreach_status VARCHAR(20) DEFAULT 'active' NOT NULL"))
                conn.commit()
                logger.info("Migration: added outreach_status column to contact_details")
            if "unsubscribed_at" not in contact_cols:
                conn.execute(sa_text_unsub("ALTER TABLE contact_details ADD COLUMN unsubscribed_at DATETIME NULL"))
                conn.commit()
                logger.info("Migration: added unsubscribed_at column to contact_details")

            outreach_cols = [c["name"] for c in inspector_unsub.get_columns("outreach_events")]
            if "tracking_id" not in outreach_cols:
                conn.execute(sa_text_unsub("ALTER TABLE outreach_events ADD COLUMN tracking_id VARCHAR(64) NULL"))
                conn.commit()
                logger.info("Migration: added tracking_id column to outreach_events")

            # Sync: mark existing suppressed contacts as unsubscribed
            try:
                conn.execute(sa_text_unsub(
                    "UPDATE contact_details cd INNER JOIN suppression_list sl "
                    "ON LOWER(cd.email) = sl.email "
                    "SET cd.outreach_status='unsubscribed', cd.unsubscribed_at=cd.updated_at "
                    "WHERE cd.outreach_status != 'unsubscribed'"
                ))
                conn.commit()
            except Exception:
                pass  # May fail on SQLite
    except Exception as e:
        logger.warning(f"Migration check for unsubscribe columns: {e}")

    # Migration: add enhanced dedup columns to lead_details
    try:
        from sqlalchemy import text as sa_text_dedup, inspect as sa_inspect_dedup
        with engine.connect() as conn:
            inspector_dedup = sa_inspect_dedup(engine)
            lead_cols = [c["name"] for c in inspector_dedup.get_columns("lead_details")]
            for col_name, col_def in [
                ("external_job_id", "VARCHAR(255) NULL"),
                ("city", "VARCHAR(100) NULL"),
                ("employer_linkedin_url", "VARCHAR(500) NULL"),
                ("employer_website", "VARCHAR(500) NULL"),
            ]:
                if col_name not in lead_cols:
                    conn.execute(sa_text_dedup(f"ALTER TABLE lead_details ADD COLUMN {col_name} {col_def}"))
                    conn.commit()
                    logger.info(f"Migration: added {col_name} column to lead_details")
            # Add index on external_job_id if not exists
            try:
                conn.execute(sa_text_dedup("CREATE INDEX idx_lead_external_job_id ON lead_details(external_job_id)"))
                conn.commit()
                logger.info("Migration: added index idx_lead_external_job_id")
            except Exception:
                pass  # Index already exists
    except Exception as e:
        logger.warning(f"Migration check for dedup columns: {e}")

    # Migration: add enrichment columns to client_info
    try:
        from sqlalchemy import text as sa_text_enrich, inspect as sa_inspect_enrich
        with engine.connect() as conn:
            inspector_enrich = sa_inspect_enrich(engine)
            client_cols = [c["name"] for c in inspector_enrich.get_columns("client_info")]
            for col_name, col_def in [
                ("website", "VARCHAR(500) NULL"),
                ("linkedin_url", "VARCHAR(500) NULL"),
                ("domain", "VARCHAR(255) NULL"),
                ("description", "VARCHAR(2000) NULL"),
                ("logo_url", "VARCHAR(500) NULL"),
                ("employee_count", "INT NULL"),
                ("founded_year", "INT NULL"),
                ("headquarters", "VARCHAR(255) NULL"),
                ("phone", "VARCHAR(50) NULL"),
                ("enrichment_source", "VARCHAR(100) NULL"),
                ("enriched_at", "DATETIME NULL"),
            ]:
                if col_name not in client_cols:
                    conn.execute(sa_text_enrich(f"ALTER TABLE client_info ADD COLUMN {col_name} {col_def}"))
                    conn.commit()
                    logger.info(f"Migration: added {col_name} column to client_info")
    except Exception as e:
        logger.warning(f"Migration check for client enrichment columns: {e}")

    # Migration: make sender_mailboxes.password nullable (for OAuth2 mailboxes)
    try:
        from sqlalchemy import text as sa_text_pw_null
        if settings.DB_TYPE == "mysql":
            with engine.connect() as conn:
                try:
                    conn.execute(sa_text_pw_null(
                        "ALTER TABLE sender_mailboxes MODIFY COLUMN password VARCHAR(500) NULL"
                    ))
                    conn.commit()
                    logger.info("Migration: made sender_mailboxes.password nullable")
                except Exception as e2:
                    logger.debug(f"Password nullable migration (may already be done): {e2}")
    except Exception as e:
        logger.warning(f"Migration check for password nullable: {e}")

    # Migration: add OAuth2 columns to sender_mailboxes
    try:
        from sqlalchemy import text as sa_text_oauth, inspect as sa_inspect_oauth
        with engine.connect() as conn:
            inspector_oauth = sa_inspect_oauth(engine)
            mb_cols = [c["name"] for c in inspector_oauth.get_columns("sender_mailboxes")]
            for col_name, col_def in [
                ("auth_method", "VARCHAR(20) DEFAULT 'password'"),
                ("oauth_access_token", "TEXT NULL"),
                ("oauth_refresh_token", "TEXT NULL"),
                ("oauth_token_expires_at", "DATETIME NULL"),
                ("oauth_tenant_id", "VARCHAR(100) NULL"),
            ]:
                if col_name not in mb_cols:
                    conn.execute(sa_text_oauth(f"ALTER TABLE sender_mailboxes ADD COLUMN {col_name} {col_def}"))
                    conn.commit()
                    logger.info(f"Migration: added {col_name} column to sender_mailboxes")
    except Exception as e:
        logger.warning(f"Migration check for OAuth2 columns: {e}")

    # Migration: add campaign columns to outreach_events
    try:
        from sqlalchemy import text as sa_text_camp, inspect as sa_inspect_camp
        with engine.connect() as conn:
            inspector_camp = sa_inspect_camp(engine)
            oe_cols = [c["name"] for c in inspector_camp.get_columns("outreach_events")]
            for col_name, col_def in [
                ("campaign_id", "INT NULL"),
                ("step_id", "INT NULL"),
                ("variant_index", "INT NULL"),
            ]:
                if col_name not in oe_cols:
                    conn.execute(sa_text_camp(f"ALTER TABLE outreach_events ADD COLUMN {col_name} {col_def}"))
                    conn.commit()
                    logger.info(f"Migration: added {col_name} column to outreach_events")
    except Exception as e:
        logger.warning(f"Migration check for campaign columns on outreach_events: {e}")

    # Migration: add timezone, lead_score, CRM ID columns to contact_details
    try:
        from sqlalchemy import text as sa_text_tz, inspect as sa_inspect_tz
        with engine.connect() as conn:
            inspector_tz = sa_inspect_tz(engine)
            cd_cols = [c["name"] for c in inspector_tz.get_columns("contact_details")]
            for col_name, col_def in [
                ("timezone", "VARCHAR(50) NULL"),
                ("lead_score", "INT NULL"),
                ("lead_score_factors_json", "TEXT NULL"),
                ("lead_score_updated_at", "DATETIME NULL"),
                ("hubspot_id", "VARCHAR(50) NULL"),
                ("salesforce_id", "VARCHAR(50) NULL"),
            ]:
                if col_name not in cd_cols:
                    conn.execute(sa_text_tz(f"ALTER TABLE contact_details ADD COLUMN {col_name} {col_def}"))
                    conn.commit()
                    logger.info(f"Migration: added {col_name} column to contact_details")
    except Exception as e:
        logger.warning(f"Migration check for contact timezone/lead_score columns: {e}")

    # Migration: add smtp_relay_config_json to sender_mailboxes
    try:
        from sqlalchemy import text as sa_text_relay, inspect as sa_inspect_relay
        with engine.connect() as conn:
            inspector_relay = sa_inspect_relay(engine)
            mb_cols_relay = [c["name"] for c in inspector_relay.get_columns("sender_mailboxes")]
            if "smtp_relay_config_json" not in mb_cols_relay:
                conn.execute(sa_text_relay("ALTER TABLE sender_mailboxes ADD COLUMN smtp_relay_config_json TEXT NULL"))
                conn.commit()
                logger.info("Migration: added smtp_relay_config_json column to sender_mailboxes")
    except Exception as e:
        logger.warning(f"Migration check for smtp_relay_config_json: {e}")

    # Migration: encrypt existing plaintext mailbox passwords
    try:
        from app.core.encryption import encrypt_field, is_encrypted
        from app.db.base import SessionLocal as _MigSessionLocal
        from app.db.models.sender_mailbox import SenderMailbox as _MigMailbox
        _mig_db = _MigSessionLocal()
        try:
            _mailboxes = _mig_db.query(_MigMailbox).all()
            _migrated = 0
            for _mb in _mailboxes:
                if _mb.password and not is_encrypted(_mb.password):
                    _mb.password = encrypt_field(_mb.password)
                    _migrated += 1
            if _migrated:
                _mig_db.commit()
                logger.info(f"Migration: encrypted {_migrated} plaintext mailbox password(s)")
        finally:
            _mig_db.close()
    except Exception as e:
        logger.warning(f"Migration check for password encryption: {e}")

    # Migration: add deal automation columns (is_auto_created, probability_manual)
    try:
        from sqlalchemy import text as sa_text_deal, inspect as sa_inspect_deal
        with engine.connect() as conn:
            inspector_deal = sa_inspect_deal(engine)
            deal_cols = [c["name"] for c in inspector_deal.get_columns("deals")]
            for col_name, col_def in [
                ("is_auto_created", "BOOLEAN DEFAULT 0 NOT NULL"),
                ("probability_manual", "BOOLEAN DEFAULT 0 NOT NULL"),
            ]:
                if col_name not in deal_cols:
                    conn.execute(sa_text_deal(f"ALTER TABLE deals ADD COLUMN {col_name} {col_def}"))
                    conn.commit()
                    logger.info(f"Migration: added {col_name} column to deals")
    except Exception as e:
        logger.warning(f"Migration check for deal automation columns: {e}")

    # Migration: add auto-enrollment columns to campaigns
    try:
        from sqlalchemy import text as sa_text_enroll, inspect as sa_inspect_enroll
        with engine.connect() as conn:
            inspector_enroll = sa_inspect_enroll(engine)
            camp_cols = [c["name"] for c in inspector_enroll.get_columns("campaigns")]
            for col_name, col_def in [
                ("enrollment_rules_json", "TEXT NULL"),
                ("auto_enrolled_today", "INT DEFAULT 0 NOT NULL"),
            ]:
                if col_name not in camp_cols:
                    conn.execute(sa_text_enroll(f"ALTER TABLE campaigns ADD COLUMN {col_name} {col_def}"))
                    conn.commit()
                    logger.info(f"Migration: added {col_name} column to campaigns")
    except Exception as e:
        logger.warning(f"Migration check for enrollment columns: {e}")

    # Migration: add cost tracking columns to cost_entries
    try:
        from sqlalchemy import text as sa_text_cost, inspect as sa_inspect_cost
        with engine.connect() as conn:
            inspector_cost = sa_inspect_cost(engine)
            if "cost_entries" in inspector_cost.get_table_names():
                cost_cols = [c["name"] for c in inspector_cost.get_columns("cost_entries")]
                for col_name, col_def in [
                    ("is_archived", "BOOLEAN DEFAULT 0 NOT NULL"),
                    ("source_adapter", "VARCHAR(50) NULL"),
                    ("is_automated", "BOOLEAN DEFAULT 0 NOT NULL"),
                    ("api_calls_count", "INT NULL"),
                    ("results_count", "INT NULL"),
                    ("created_at", "DATETIME NULL"),
                ]:
                    if col_name not in cost_cols:
                        conn.execute(sa_text_cost(f"ALTER TABLE cost_entries ADD COLUMN {col_name} {col_def}"))
                        conn.commit()
                        logger.info(f"Migration: added {col_name} column to cost_entries")
                # Add index on source_adapter if not exists
                try:
                    conn.execute(sa_text_cost("CREATE INDEX idx_cost_source_adapter ON cost_entries(source_adapter)"))
                    conn.commit()
                    logger.info("Migration: added index idx_cost_source_adapter")
                except Exception:
                    pass  # Index already exists
    except Exception as e:
        logger.warning(f"Migration check for cost_entries columns: {e}")

    # Migration: add soft-delete columns to inbox_messages
    try:
        from sqlalchemy import text as sa_text_inbox_del, inspect as sa_inspect_inbox_del
        with engine.connect() as conn:
            inspector_inbox_del = sa_inspect_inbox_del(engine)
            if "inbox_messages" in inspector_inbox_del.get_table_names():
                inbox_cols = [c["name"] for c in inspector_inbox_del.get_columns("inbox_messages")]
                for col_name, col_def in [
                    ("is_deleted", "BOOLEAN DEFAULT 0 NOT NULL"),
                    ("deleted_at", "DATETIME NULL"),
                ]:
                    if col_name not in inbox_cols:
                        conn.execute(sa_text_inbox_del(f"ALTER TABLE inbox_messages ADD COLUMN {col_name} {col_def}"))
                        conn.commit()
                        logger.info(f"Migration: added {col_name} column to inbox_messages")
    except Exception as e:
        logger.warning(f"Migration check for inbox soft-delete columns: {e}")

    # Cleanup: mark orphaned pipeline runs as failed on startup
    # (runs stuck as 'running' from server crashes or restarts)
    try:
        from app.db.base import SessionLocal as _CleanupSession
        from app.db.models.job_run import JobRun, JobStatus
        from datetime import datetime, timedelta
        _cleanup_db = _CleanupSession()
        try:
            stale_cutoff = datetime.utcnow() - timedelta(hours=1)
            stale_runs = _cleanup_db.query(JobRun).filter(
                JobRun.status == JobStatus.RUNNING,
                JobRun.created_at < stale_cutoff,
            ).all()
            for run in stale_runs:
                run.status = JobStatus.FAILED
                run.error_message = "Orphaned run - process crashed or server restarted"
                run.ended_at = datetime.utcnow()
            if stale_runs:
                _cleanup_db.commit()
                logger.info(f"Cleanup: marked {len(stale_runs)} orphaned pipeline run(s) as failed")
        finally:
            _cleanup_db.close()
    except Exception as e:
        logger.warning(f"Cleanup check for orphaned runs: {e}")

    # Migration: Multi-tenancy — add tenant_id + verification columns to users
    try:
        from sqlalchemy import text as sa_text_mt, inspect as sa_inspect_mt
        with engine.connect() as conn:
            inspector_mt = sa_inspect_mt(engine)

            # 1. Ensure tenants table has new plan-limit columns
            if "tenants" in inspector_mt.get_table_names():
                tenant_cols = [c["name"] for c in inspector_mt.get_columns("tenants")]
                for col_name, col_def in [
                    ("max_users", "INT DEFAULT 3 NOT NULL"),
                    ("max_leads", "INT DEFAULT 0 NOT NULL"),
                ]:
                    if col_name not in tenant_cols:
                        try:
                            conn.execute(sa_text_mt(f"ALTER TABLE tenants ADD COLUMN {col_name} {col_def}"))
                            conn.commit()
                            logger.info(f"Migration: added {col_name} to tenants")
                        except Exception:
                            pass

            # 2. Add tenant_id + verification fields to users if missing
            user_cols = [c["name"] for c in inspector_mt.get_columns("users")]
            for col_name, col_def in [
                ("tenant_id", "INT NULL"),
                ("is_verified", "BOOLEAN DEFAULT 1 NOT NULL"),
                ("verification_token", "VARCHAR(512) NULL"),
                ("verification_sent_at", "DATETIME NULL"),
            ]:
                if col_name not in user_cols:
                    try:
                        conn.execute(sa_text_mt(f"ALTER TABLE users ADD COLUMN {col_name} {col_def}"))
                        conn.commit()
                        logger.info(f"Migration: added {col_name} to users")
                    except Exception:
                        pass

            # 3. Create Tenant #1 (primary tenant) if not exists
            try:
                result = conn.execute(sa_text_mt("SELECT tenant_id FROM tenants WHERE tenant_id = 1"))
                if result.fetchone() is None:
                    conn.execute(sa_text_mt(
                        "INSERT INTO tenants (tenant_id, name, slug, plan, is_active, max_users, max_mailboxes, max_contacts, max_campaigns, max_leads, created_at, updated_at, is_archived) "
                        "VALUES (1, 'Exzelon', 'exzelon', 'enterprise', 1, 999, 999, 999999, 999, 999999, NOW(), NOW(), 0)"
                    ))
                    conn.commit()
                    logger.info("Migration: created primary Tenant #1 (Exzelon)")
            except Exception as e3:
                logger.debug(f"Tenant #1 creation (may already exist): {e3}")

            # 4. Assign all existing users to Tenant #1 (except super_admin)
            try:
                conn.execute(sa_text_mt(
                    "UPDATE users SET tenant_id = 1 WHERE tenant_id IS NULL AND role != 'super_admin'"
                ))
                conn.commit()
                logger.info("Migration: assigned existing users to Tenant #1")
            except Exception as e4:
                logger.debug(f"User tenant assignment: {e4}")

            # 5. Mark all existing users as verified
            try:
                conn.execute(sa_text_mt(
                    "UPDATE users SET is_verified = 1 WHERE is_verified = 0 OR is_verified IS NULL"
                ))
                conn.commit()
                logger.info("Migration: marked existing users as verified")
            except Exception as e5:
                logger.debug(f"User verification backfill: {e5}")

    except Exception as e:
        logger.warning(f"Migration check for multi-tenancy: {e}")

    _seed_warmup_profiles()
    _seed_default_email_template()
    _seed_deal_stages()

    # Seed admin user
    try:
        from app.core.seed import seed_admin_user
        from app.db.base import SessionLocal as _SeedSessionLocal
        _seed_db = _SeedSessionLocal()
        try:
            seed_admin_user(_seed_db)
        finally:
            _seed_db.close()
    except Exception as e:
        logger.error("Failed to seed admin user", error=str(e))

    # Start warmup scheduler
    try:
        from app.services.warmup.scheduler import init_scheduler
        init_scheduler()
    except Exception as e:
        logger.error("Failed to start warmup scheduler", error=str(e))

    yield

    # Shutdown
    try:
        from app.services.warmup.scheduler import shutdown_scheduler
        shutdown_scheduler()
    except Exception:
        pass
    logger.info("Shutting down application")


app = FastAPI(
    title=settings.APP_NAME,
    description="Cold-Email Automation System for Research Analysts",
    version="2.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan
)

# Rate limiter
from app.api.endpoints.auth import limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# GZip compression for responses > 1KB
app.add_middleware(GZipMiddleware, minimum_size=1000)

# CORS
_cors_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()] if settings.CORS_ORIGINS else []
if not _cors_origins:
    logger.warning("CORS_ORIGINS not set. No cross-origin requests will be allowed. "
                    "Set CORS_ORIGINS in .env (e.g. DEV_CORS_ORIGINS=http://localhost:3000)")
    _cors_origins = ["http://localhost:3000"]  # Minimal safe default for dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)


# Tracking pixel endpoint
@app.get("/t/{tracking_id}/px.gif")
async def tracking_pixel(tracking_id: str, token: str = ""):
    # 1x1 transparent GIF (always returned regardless of token validity)
    gif = bytes([0x47,0x49,0x46,0x38,0x39,0x61,0x01,0x00,0x01,0x00,0x80,0x00,0x00,0xff,0xff,0xff,0x00,0x00,0x00,0x21,0xf9,0x04,0x00,0x00,0x00,0x00,0x00,0x2c,0x00,0x00,0x00,0x00,0x01,0x00,0x01,0x00,0x00,0x02,0x02,0x44,0x01,0x00,0x3b])
    if token:
        from app.core.tracking import validate_tracking_token
        if not validate_tracking_token(tracking_id, token):
            return Response(content=gif, media_type="image/gif")
    from app.db.base import SessionLocal
    db = SessionLocal()
    try:
        from app.services.warmup.tracking import record_open
        record_open(tracking_id, db)
    except Exception:
        pass
    finally:
        db.close()
    return Response(content=gif, media_type="image/gif")


# Tracking link redirect endpoint
@app.get("/t/{tracking_id}/l")
async def tracking_link(tracking_id: str, url: str = "", token: str = ""):
    from app.core.tracking import validate_tracking_token, sanitize_redirect_url
    from fastapi.responses import RedirectResponse

    if token and not validate_tracking_token(tracking_id, token):
        return JSONResponse(status_code=403, content={"error": "Invalid tracking token"})

    from app.db.base import SessionLocal
    db = SessionLocal()
    try:
        from app.services.warmup.tracking import record_click
        record_click(tracking_id, url, db)
    except Exception:
        pass
    finally:
        db.close()

    safe_url = sanitize_redirect_url(url)
    if safe_url:
        return RedirectResponse(url=safe_url)
    return JSONResponse(status_code=400, content={"error": "Invalid or missing URL"})


# Unsubscribe endpoint (public — clicked from email)
@app.get("/unsub/{tracking_id}")
async def unsubscribe(tracking_id: str, token: str = ""):
    from fastapi.responses import HTMLResponse
    from app.core.tracking import validate_tracking_token
    from app.db.base import SessionLocal
    from datetime import datetime

    if not token or not validate_tracking_token(tracking_id, token):
        return HTMLResponse(
            status_code=403,
            content=(
                '<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:40px auto;text-align:center;">'
                '<h2 style="color:#dc2626;">Invalid Unsubscribe Link</h2>'
                '<p>This link is invalid or has expired.</p>'
                '<p>To unsubscribe, reply to any of our emails with the word <strong>UNSUBSCRIBE</strong>.</p>'
                '</body></html>'
            )
        )

    db = SessionLocal()
    try:
        from app.db.models.outreach import OutreachEvent
        from app.db.models.contact import ContactDetails, OutreachStatus as ContactOutreachStatus
        from app.db.models.suppression import SuppressionList
        from app.db.models.audit_log import AuditLog

        event = db.query(OutreachEvent).filter(OutreachEvent.tracking_id == tracking_id).first()
        if not event:
            return HTMLResponse(
                status_code=404,
                content=(
                    '<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:40px auto;text-align:center;">'
                    '<h2 style="color:#dc2626;">Link Not Found</h2>'
                    '<p>This unsubscribe link is no longer valid.</p>'
                    '<p>To unsubscribe, reply to any of our emails with the word <strong>UNSUBSCRIBE</strong>.</p>'
                    '</body></html>'
                )
            )

        contact = db.query(ContactDetails).filter(ContactDetails.contact_id == event.contact_id).first()
        if contact:
            # Add to suppression list
            existing_sup = db.query(SuppressionList).filter(
                SuppressionList.email == contact.email.lower()
            ).first()
            if not existing_sup:
                db.add(SuppressionList(email=contact.email.lower(), reason="unsubscribe_link"))

            # Update contact status
            contact.outreach_status = ContactOutreachStatus.UNSUBSCRIBED
            contact.unsubscribed_at = datetime.utcnow()

            # Audit log
            db.add(AuditLog(
                entity_type="contact",
                entity_id=contact.contact_id,
                action="unsubscribe",
                changed_by="system",
                notes="Unsubscribed via email link",
            ))

        db.commit()
        logger.info("Contact unsubscribed via link", tracking_id=tracking_id, contact_id=event.contact_id)

        return HTMLResponse(
            content=(
                '<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:40px auto;text-align:center;">'
                '<h2 style="color:#16a34a;">You have been unsubscribed</h2>'
                '<p>You will no longer receive emails from us.</p>'
                '<p style="color:#666;font-size:14px;margin-top:20px;">If this was a mistake, please contact us directly.</p>'
                '</body></html>'
            )
        )
    except Exception as e:
        logger.error("Unsubscribe endpoint error", error=str(e), tracking_id=tracking_id)
        return HTMLResponse(
            status_code=500,
            content=(
                '<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:40px auto;text-align:center;">'
                '<h2 style="color:#dc2626;">Something went wrong</h2>'
                '<p>Please try again or reply to any of our emails with <strong>UNSUBSCRIBE</strong>.</p>'
                '</body></html>'
            )
        )
    finally:
        db.close()


@app.get("/")
async def root():
    return {"app": settings.APP_NAME, "version": "2.0.0", "docs": "/api/docs"}


@app.get("/health")
async def health_check():
    """Health check with DB connectivity test."""
    db_ok = False
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            db_ok = True
    except Exception:
        pass
    status = "healthy" if db_ok else "degraded"
    code = 200 if db_ok else 503
    return JSONResponse(
        status_code=code,
        content={"status": status, "env": settings.APP_ENV, "database": "connected" if db_ok else "unavailable"}
    )


@app.exception_handler(AppException)
async def app_exception_handler(request, exc: AppException):
    logger.warning("Application error", error_code=exc.error_code, detail=exc.detail, path=request.url.path)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "error_code": exc.error_code}
    )


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error("Unhandled exception", error=str(exc), path=request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.HOST, port=settings.PORT)
