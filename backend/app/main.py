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
from app.middleware.security_headers import SecurityHeadersMiddleware

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
    """Seed the default Exzelon outreach and follow-up email templates if none exist."""
    from app.db.base import SessionLocal
    from app.db.models.email_template import EmailTemplate, TemplateStatus, TemplateCategory
    db = SessionLocal()
    try:
        existing = db.query(EmailTemplate).filter(
            EmailTemplate.is_default == True,
            EmailTemplate.category == TemplateCategory.OUTREACH,
        ).first()
        if existing:
            # Backfill category on existing default if it's missing/null
            if not existing.category or existing.category != TemplateCategory.OUTREACH:
                existing.category = TemplateCategory.OUTREACH
                db.commit()
            _seed_default_followup_template(db)
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
            tenant_id=1,
            name="Exzelon Default Outreach",
            subject=default_subject,
            body_html=default_body_html,
            body_text=default_body_text,
            status=TemplateStatus.ACTIVE,
            is_default=True,
            category=TemplateCategory.OUTREACH,
            description="Default Exzelon Consulting outreach template with free candidate preview offer.",
        )
        db.add(template)
        db.commit()
        logger.info("Seeded default email template")

        # Seed the follow-up template after outreach
        _seed_default_followup_template(db)

    except Exception as e:
        logger.error("Failed to seed default email template", error=str(e))
    finally:
        db.close()


def _seed_default_followup_template(db):
    """Seed the default Exzelon follow-up email template if none exists."""
    from app.db.models.email_template import EmailTemplate, TemplateStatus, TemplateCategory
    try:
        existing_followup = db.query(EmailTemplate).filter(
            EmailTemplate.is_default == True,
            EmailTemplate.category == TemplateCategory.FOLLOWUP,
        ).first()
        if existing_followup:
            return

        followup_subject = "Following up — {{job_title}} at {{company_name}}"

        followup_body_html = (
            '<div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; color: #333;">\n'
            '  <p>Hi {{contact_first_name}},</p>\n'
            '  \n'
            '  <p>I wanted to follow up on my previous email about the <strong>{{job_title}}</strong> opening at <strong>{{company_name}}</strong>.</p>\n'
            '  \n'
            '  <p>I understand you\'re busy, so I\'ll keep this brief — we have several pre-screened candidates ready for your review. No commitment needed to see their profiles.</p>\n'
            '  \n'
            '  <p>Would a quick 10-minute call work this week? Happy to work around your schedule.</p>\n'
            '  \n'
            '  <p>Best regards,</p>\n'
            '  \n'
            '  {{signature}}\n'
            '  \n'
            '  <div style="margin-top: 20px; text-align: left;">\n'
            '    <img src="{{logo_url}}" alt="Exzelon Consulting Inc." style="max-width: 150px; height: auto;" />\n'
            '  </div>\n'
            '  \n'
            '  <hr style="border: none; border-top: 1px solid #eee; margin-top: 20px;" />\n'
            '  <p style="font-size: 11px; color: #999;">{{unsubscribe_link}}</p>\n'
            '</div>'
        )

        followup_body_text = (
            "Hi {{contact_first_name}},\n"
            "\n"
            "I wanted to follow up on my previous email about the {{job_title}} opening at {{company_name}}.\n"
            "\n"
            "I understand you're busy, so I'll keep this brief -- we have several pre-screened candidates ready for your review. No commitment needed to see their profiles.\n"
            "\n"
            "Would a quick 10-minute call work this week? Happy to work around your schedule.\n"
            "\n"
            "Best regards,\n"
            "{{sender_first_name}}\n"
            "\n"
            "{{unsubscribe_link}}"
        )

        template = EmailTemplate(
            tenant_id=1,
            name="Exzelon Default Follow-up",
            subject=followup_subject,
            body_html=followup_body_html,
            body_text=followup_body_text,
            status=TemplateStatus.ACTIVE,
            is_default=True,
            category=TemplateCategory.FOLLOWUP,
            description="Default Exzelon Consulting follow-up template for second touch.",
        )
        db.add(template)
        db.commit()
        logger.info("Seeded default follow-up email template")
    except Exception as e:
        logger.error("Failed to seed default follow-up template", error=str(e))


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
                tenant_id=1,
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


def _seed_outreach_roles():
    """Seed default outreach roles (RA, BDM, Recruiter) for every tenant that lacks them."""
    from app.db.base import SessionLocal
    from app.db.models.outreach_role import OutreachRole
    from app.db.models.tenant import Tenant
    from app.db.models.sender_mailbox import SenderMailbox
    db = SessionLocal()
    try:
        tenants = db.query(Tenant.tenant_id).all()
        if not tenants:
            tenants = [(1,)]  # Fallback single-tenant

        default_roles = [
            {"role_name": "RA", "description": "Recruiting Associate — handles sourcing outreach"},
            {"role_name": "BDM", "description": "Business Development Manager — handles client outreach"},
            {"role_name": "Recruiter", "description": "Recruiter — handles candidate outreach"},
        ]

        seeded = 0
        for (tid,) in tenants:
            existing_names = {
                r.role_name for r in
                db.query(OutreachRole.role_name).filter(
                    OutreachRole.tenant_id == tid,
                    OutreachRole.is_archived == False,
                ).all()
            }
            for role_def in default_roles:
                if role_def["role_name"] not in existing_names:
                    db.add(OutreachRole(
                        tenant_id=tid,
                        role_name=role_def["role_name"],
                        description=role_def["description"],
                        is_system=True,
                    ))
                    seeded += 1

        if seeded > 0:
            db.commit()

            # Backfill: assign RA role to mailboxes without a role
            for (tid,) in tenants:
                ra_role = db.query(OutreachRole).filter(
                    OutreachRole.tenant_id == tid,
                    OutreachRole.role_name == "RA",
                    OutreachRole.is_archived == False,
                ).first()
                if ra_role:
                    db.query(SenderMailbox).filter(
                        SenderMailbox.tenant_id == tid,
                        SenderMailbox.outreach_role_id == None,
                    ).update({SenderMailbox.outreach_role_id: ra_role.role_id}, synchronize_session=False)
            db.commit()
            logger.info(f"Seeded {seeded} outreach roles and backfilled mailboxes")
    except Exception as e:
        logger.error("Failed to seed outreach roles", error=str(e))
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting application", app_name=settings.APP_NAME, env=settings.APP_ENV)

    # Use MySQL advisory lock to serialize migrations across workers
    _migration_lock_conn = None
    _got_lock = False
    if settings.DB_TYPE == "mysql":
        try:
            from sqlalchemy import text as _lock_text
            _migration_lock_conn = engine.connect()
            result = _migration_lock_conn.execute(_lock_text("SELECT GET_LOCK('exzelon_migration', 30)"))
            _got_lock = result.scalar() == 1
            if _got_lock:
                logger.info("Acquired migration lock")
            else:
                logger.info("Migration lock held by another worker, waiting...")
                # Try once more with longer timeout
                result = _migration_lock_conn.execute(_lock_text("SELECT GET_LOCK('exzelon_migration', 60)"))
                _got_lock = result.scalar() == 1
        except Exception as lock_err:
            logger.warning(f"Advisory lock not available: {lock_err}")

    try:
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        # With multiple workers, race conditions can cause "table already exists" errors
        if "already exists" in str(e) or "1684" in str(e) or "being modified" in str(e):
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

    # ── Migration: outreach_role_id on sender_mailboxes ──
    # MUST run before any ORM query that touches sender_mailboxes
    try:
        from sqlalchemy import text as sa_text_or
        if settings.DB_TYPE == "mysql":
            with engine.connect() as conn:
                from sqlalchemy import inspect as sa_inspect_or
                inspector = sa_inspect_or(engine)
                cols = [c["name"] for c in inspector.get_columns("sender_mailboxes")]
                if "outreach_role_id" not in cols:
                    conn.execute(sa_text_or(
                        "ALTER TABLE sender_mailboxes ADD COLUMN outreach_role_id INTEGER NULL"
                    ))
                    conn.execute(sa_text_or(
                        "CREATE INDEX ix_sender_mailboxes_outreach_role_id "
                        "ON sender_mailboxes (outreach_role_id)"
                    ))
                    conn.commit()
                    logger.info("Migration: added outreach_role_id column to sender_mailboxes")
    except Exception as e:
        logger.warning(f"Migration check for outreach_role_id: {e}")

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

    # Migration: add industry and company_size columns to lead_details
    try:
        from sqlalchemy import text as sa_text_ind, inspect as sa_inspect_ind
        with engine.connect() as conn:
            inspector_ind = sa_inspect_ind(engine)
            lead_cols = [c["name"] for c in inspector_ind.get_columns("lead_details")]
            for col_name, col_def in [
                ("industry", "VARCHAR(255) NULL"),
                ("company_size", "VARCHAR(100) NULL"),
            ]:
                if col_name not in lead_cols:
                    try:
                        conn.execute(sa_text_ind(f"ALTER TABLE lead_details ADD COLUMN {col_name} {col_def}"))
                        conn.commit()
                        logger.info(f"Migration: added {col_name} column to lead_details")
                    except Exception:
                        pass
    except Exception as e:
        logger.warning(f"Migration check for industry/company_size: {e}")

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

    # NOTE: Password encryption migration moved below Phase 4 multi-tenancy
    # (ORM queries require tenant_id column to exist first)

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

    # NOTE: Orphaned runs cleanup moved below Phase 4 multi-tenancy
    # (ORM queries require tenant_id column to exist first)

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
                    # Drop stale primary_color column if it exists (NOT NULL blocks inserts)
                    try:
                        tenant_cols = [c["name"] for c in sa_inspect_mt(engine).get_columns("tenants")]
                        if "primary_color" in tenant_cols:
                            conn.execute(sa_text_mt("ALTER TABLE tenants DROP COLUMN primary_color"))
                            conn.commit()
                            logger.info("Migration: dropped stale primary_color column from tenants")
                    except Exception:
                        pass
                    conn.execute(sa_text_mt(
                        "INSERT INTO tenants (tenant_id, name, slug, plan, is_active, max_users, max_mailboxes, max_contacts, max_campaigns, max_leads, created_at, updated_at, is_archived) "
                        "VALUES (1, 'Exzelon', 'exzelon', 'enterprise', 1, 999, 999, 999999, 999, 999999, NOW(), NOW(), 0)"
                    ))
                    conn.commit()
                    logger.info("Migration: created primary Tenant #1 (Exzelon)")
            except Exception as e3:
                logger.warning(f"Tenant #1 creation FAILED: {e3}")

            # 3b. Create admin user for Tenant #1 if not exists
            try:
                result = conn.execute(sa_text_mt("SELECT user_id FROM users WHERE email = 'admin@exzelon.com'"))
                if result.fetchone() is None:
                    from app.core.security import get_password_hash
                    import os as _os_seed
                    _seed_pw = _os_seed.environ.get("SEED_EXZELON_PASSWORD", "ExzelonAdmin#2026")
                    hashed = get_password_hash(_seed_pw)
                    conn.execute(sa_text_mt(
                        "INSERT INTO users (email, password_hash, full_name, role, is_active, tenant_id, is_verified) "
                        "VALUES ('admin@exzelon.com', :pw, 'Exzelon Admin', 'admin', 1, 1, 1)"
                    ), {"pw": hashed})
                    conn.commit()
                    logger.info("Migration: created admin@exzelon.com for Tenant #1")
            except Exception as e_admin:
                logger.debug(f"Exzelon admin creation: {e_admin}")

            # 3c. Copy global settings to tenant_settings for Tenant #1 if empty
            try:
                ts_count = conn.execute(sa_text_mt(
                    "SELECT COUNT(*) FROM tenant_settings WHERE tenant_id = 1"
                )).scalar()
                if ts_count == 0:
                    conn.execute(sa_text_mt(
                        "INSERT INTO tenant_settings (tenant_id, `key`, value_json, updated_by, updated_at, created_at, is_archived) "
                        "SELECT 1, s.`key`, s.value_json, 'system-migration', NOW(), NOW(), 0 "
                        "FROM settings s WHERE s.is_archived = 0"
                    ))
                    conn.commit()
                    logger.info("Migration: copied global settings to tenant_settings for Tenant #1")
            except Exception as e_ts:
                logger.debug(f"Tenant settings copy: {e_ts}")

            # 3d. Create Neuraforz tenant if not exists
            try:
                result = conn.execute(sa_text_mt("SELECT tenant_id FROM tenants WHERE slug = 'neuraforz'"))
                if result.fetchone() is None:
                    conn.execute(sa_text_mt(
                        "INSERT INTO tenants (name, slug, plan, is_active, max_users, max_mailboxes, max_contacts, max_campaigns, max_leads, created_at, updated_at, is_archived) "
                        "VALUES ('Neuraforz', 'neuraforz', 'enterprise', 1, 999, 999, 999999, 999, 999999, NOW(), NOW(), 0)"
                    ))
                    conn.commit()
                    logger.info("Migration: created Neuraforz tenant")
            except Exception as e_nf:
                logger.debug(f"Neuraforz tenant creation: {e_nf}")

            # 3e. Create admin user for Neuraforz
            try:
                result = conn.execute(sa_text_mt("SELECT user_id FROM users WHERE email = 'admin@neuraforz.com'"))
                if result.fetchone() is None:
                    nf_tid = conn.execute(sa_text_mt("SELECT tenant_id FROM tenants WHERE slug = 'neuraforz'")).scalar()
                    if nf_tid:
                        from app.core.security import get_password_hash as _nf_hash
                        import os as _os_nf
                        _nf_pw = _os_nf.environ.get("SEED_NEURAFORZ_PASSWORD", "Admin@nz")
                        hashed_nf = _nf_hash(_nf_pw)
                        conn.execute(sa_text_mt(
                            "INSERT INTO users (email, password_hash, full_name, role, is_active, tenant_id, is_verified, created_at, updated_at, is_archived) "
                            "VALUES ('admin@neuraforz.com', :pw, 'Neuraforz Admin', 'admin', 1, :tid, 1, NOW(), NOW(), 0)"
                        ), {"pw": hashed_nf, "tid": nf_tid})
                        conn.commit()
                        logger.info("Migration: created admin@neuraforz.com")
            except Exception as e_nf_admin:
                logger.debug(f"Neuraforz admin creation: {e_nf_admin}")

            # 3f. Copy global settings to tenant_settings for Neuraforz
            try:
                nf_tid2 = conn.execute(sa_text_mt("SELECT tenant_id FROM tenants WHERE slug = 'neuraforz'")).scalar()
                if nf_tid2:
                    ts_count_nf = conn.execute(sa_text_mt(
                        "SELECT COUNT(*) FROM tenant_settings WHERE tenant_id = :tid"
                    ), {"tid": nf_tid2}).scalar()
                    if ts_count_nf == 0:
                        conn.execute(sa_text_mt(
                            "INSERT INTO tenant_settings (tenant_id, `key`, value_json, updated_by, updated_at, created_at, is_archived) "
                            "SELECT :tid, s.`key`, s.value_json, 'system-migration', NOW(), NOW(), 0 "
                            "FROM settings s WHERE s.is_archived = 0"
                        ), {"tid": nf_tid2})
                        conn.commit()
                        logger.info("Migration: copied global settings to tenant_settings for Neuraforz")
            except Exception as e_nf_ts:
                logger.debug(f"Neuraforz tenant settings copy: {e_nf_ts}")

            # 3g. Create Medeoan tenant if not exists
            try:
                result = conn.execute(sa_text_mt("SELECT tenant_id FROM tenants WHERE slug = 'medeoan'"))
                if result.fetchone() is None:
                    conn.execute(sa_text_mt(
                        "INSERT INTO tenants (name, slug, plan, is_active, max_users, max_mailboxes, max_contacts, max_campaigns, max_leads, created_at, updated_at, is_archived) "
                        "VALUES ('Medeoan', 'medeoan', 'enterprise', 1, 999, 999, 999999, 999, 999999, NOW(), NOW(), 0)"
                    ))
                    conn.commit()
                    logger.info("Migration: created Medeoan tenant")
            except Exception as e_md:
                logger.debug(f"Medeoan tenant creation: {e_md}")

            # 3h. Create admin user for Medeoan
            try:
                result = conn.execute(sa_text_mt("SELECT user_id FROM users WHERE email = 'admin@medeoan.com'"))
                if result.fetchone() is None:
                    md_tid = conn.execute(sa_text_mt("SELECT tenant_id FROM tenants WHERE slug = 'medeoan'")).scalar()
                    if md_tid:
                        from app.core.security import get_password_hash as _md_hash
                        import os as _os_md
                        _md_pw = _os_md.environ.get("SEED_MEDEOAN_PASSWORD", "Admin@mn")
                        hashed_md = _md_hash(_md_pw)
                        conn.execute(sa_text_mt(
                            "INSERT INTO users (email, password_hash, full_name, role, is_active, tenant_id, is_verified, created_at, updated_at, is_archived) "
                            "VALUES ('admin@medeoan.com', :pw, 'Medeoan Admin', 'admin', 1, :tid, 1, NOW(), NOW(), 0)"
                        ), {"pw": hashed_md, "tid": md_tid})
                        conn.commit()
                        logger.info("Migration: created admin@medeoan.com")
            except Exception as e_md_admin:
                logger.debug(f"Medeoan admin creation: {e_md_admin}")

            # 3i. Copy global settings to tenant_settings for Medeoan
            try:
                md_tid2 = conn.execute(sa_text_mt("SELECT tenant_id FROM tenants WHERE slug = 'medeoan'")).scalar()
                if md_tid2:
                    ts_count_md = conn.execute(sa_text_mt(
                        "SELECT COUNT(*) FROM tenant_settings WHERE tenant_id = :tid"
                    ), {"tid": md_tid2}).scalar()
                    if ts_count_md == 0:
                        conn.execute(sa_text_mt(
                            "INSERT INTO tenant_settings (tenant_id, `key`, value_json, updated_by, updated_at, created_at, is_archived) "
                            "SELECT :tid, s.`key`, s.value_json, 'system-migration', NOW(), NOW(), 0 "
                            "FROM settings s WHERE s.is_archived = 0"
                        ), {"tid": md_tid2})
                        conn.commit()
                        logger.info("Migration: copied global settings to tenant_settings for Medeoan")
            except Exception as e_md_ts:
                logger.debug(f"Medeoan tenant settings copy: {e_md_ts}")

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

    # Migration: Phase 2 multi-tenancy — add tenant_id to core data tables
    try:
        from sqlalchemy import text as sa_text_mt2, inspect as sa_inspect_mt2
        with engine.connect() as conn:
            inspector_mt2 = sa_inspect_mt2(engine)
            # Tables that need tenant_id
            mt2_tables = ["lead_details", "contact_details", "client_info", "sender_mailboxes"]
            for tbl in mt2_tables:
                if tbl not in inspector_mt2.get_table_names():
                    continue
                cols = [c["name"] for c in inspector_mt2.get_columns(tbl)]
                if "tenant_id" not in cols:
                    try:
                        conn.execute(sa_text_mt2(f"ALTER TABLE {tbl} ADD COLUMN tenant_id INT NULL"))
                        conn.commit()
                        logger.info(f"Migration: added tenant_id column to {tbl}")
                    except Exception as e_add:
                        logger.debug(f"tenant_id add to {tbl} (may already exist): {e_add}")

                    # Backfill: set all existing rows to Tenant #1
                    try:
                        conn.execute(sa_text_mt2(f"UPDATE {tbl} SET tenant_id = 1 WHERE tenant_id IS NULL"))
                        conn.commit()
                        logger.info(f"Migration: backfilled tenant_id=1 for {tbl}")
                    except Exception as e_bf:
                        logger.debug(f"tenant_id backfill for {tbl}: {e_bf}")

                    # Make NOT NULL (MySQL only — SQLite doesn't support MODIFY)
                    if settings.DB_TYPE == "mysql":
                        try:
                            conn.execute(sa_text_mt2(f"ALTER TABLE {tbl} MODIFY COLUMN tenant_id INT NOT NULL"))
                            conn.commit()
                            logger.info(f"Migration: made tenant_id NOT NULL on {tbl}")
                        except Exception as e_nn:
                            logger.debug(f"tenant_id NOT NULL for {tbl}: {e_nn}")

                    # Add index
                    idx_name = f"idx_{tbl}_tenant"
                    try:
                        conn.execute(sa_text_mt2(f"CREATE INDEX {idx_name} ON {tbl}(tenant_id)"))
                        conn.commit()
                        logger.info(f"Migration: added index {idx_name}")
                    except Exception:
                        pass  # Index already exists

            # Drop unique constraint on client_info.client_name (now per-tenant)
            if settings.DB_TYPE == "mysql":
                for idx_name in ("client_name", "ix_client_info_client_name"):
                    try:
                        conn.execute(sa_text_mt2(f"ALTER TABLE client_info DROP INDEX {idx_name}"))
                        conn.commit()
                        logger.info(f"Migration: dropped index {idx_name} on client_info")
                    except Exception:
                        pass  # Already dropped or doesn't exist
                # Add composite unique (tenant_id, client_name)
                try:
                    conn.execute(sa_text_mt2(
                        "CREATE UNIQUE INDEX idx_client_tenant_name ON client_info(tenant_id, client_name)"
                    ))
                    conn.commit()
                    logger.info("Migration: added composite unique index on client_info(tenant_id, client_name)")
                except Exception:
                    pass

    except Exception as e:
        logger.warning(f"Migration check for Phase 2 multi-tenancy: {e}")

    # Migration: Phase 3 multi-tenancy — add tenant_id to campaign/communication tables
    try:
        from sqlalchemy import text as sa_text_mt3, inspect as sa_inspect_mt3
        with engine.connect() as conn:
            inspector_mt3 = sa_inspect_mt3(engine)
            phase3_tables = ["campaigns", "outreach_events", "inbox_messages", "email_templates"]
            for tbl in phase3_tables:
                if tbl not in inspector_mt3.get_table_names():
                    continue
                cols = [c["name"] for c in inspector_mt3.get_columns(tbl)]
                if "tenant_id" not in cols:
                    logger.info(f"Migration: adding tenant_id to {tbl}")
                    conn.execute(sa_text_mt3(f"ALTER TABLE {tbl} ADD COLUMN tenant_id INT NULL"))
                    conn.execute(sa_text_mt3(f"UPDATE {tbl} SET tenant_id = 1 WHERE tenant_id IS NULL"))
                    try:
                        conn.execute(sa_text_mt3(f"ALTER TABLE {tbl} MODIFY COLUMN tenant_id INT NOT NULL"))
                    except Exception:
                        pass  # SQLite doesn't support MODIFY
                    try:
                        conn.execute(sa_text_mt3(f"CREATE INDEX idx_{tbl}_tenant ON {tbl}(tenant_id)"))
                    except Exception:
                        pass  # Index may already exist
                    conn.commit()
                    logger.info(f"Migration: tenant_id added to {tbl}")
    except Exception as e:
        logger.warning(f"Migration check for Phase 3 multi-tenancy: {e}")

    # Migration: create tenant_settings table for per-tenant setting overrides
    try:
        from sqlalchemy import text as sa_text_ts, inspect as sa_inspect_ts
        with engine.connect() as conn:
            inspector_ts = sa_inspect_ts(engine)
            if "tenant_settings" not in inspector_ts.get_table_names():
                conn.execute(sa_text_ts(
                    "CREATE TABLE tenant_settings ("
                    "  id INT AUTO_INCREMENT PRIMARY KEY,"
                    "  tenant_id INT NOT NULL,"
                    "  `key` VARCHAR(100) NOT NULL,"
                    "  value_json TEXT,"
                    "  updated_by VARCHAR(255),"
                    "  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,"
                    "  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,"
                    "  is_archived BOOLEAN NOT NULL DEFAULT 0,"
                    "  UNIQUE KEY uq_tenant_settings_tid_key (tenant_id, `key`),"
                    "  INDEX idx_tenant_settings_tid_key (tenant_id, `key`),"
                    "  CONSTRAINT fk_tenant_settings_tenant FOREIGN KEY (tenant_id)"
                    "    REFERENCES tenants(tenant_id) ON DELETE CASCADE"
                    ")"
                ))
                conn.commit()
                logger.info("Migration: created tenant_settings table")
    except Exception as e:
        logger.warning(f"Migration check for tenant_settings table: {e}")

    # Migration: Phase 4 multi-tenancy — add tenant_id to remaining tables
    try:
        from sqlalchemy import text as sa_text_mt4, inspect as sa_inspect_mt4
        with engine.connect() as conn:
            phase4_tables = [
                "deal_stages", "deals", "webhooks", "api_keys",
                "saved_searches", "icp_profiles", "crm_sync_logs",
                "cost_entries", "tracking_domains", "suppression_list",
                "automation_events", "audit_logs", "job_runs",
            ]
            for tbl in phase4_tables:
                cols = [c["name"] for c in sa_inspect_mt4(engine).get_columns(tbl)]
                if "tenant_id" not in cols:
                    conn.execute(sa_text_mt4(f"ALTER TABLE {tbl} ADD COLUMN tenant_id INT NULL"))
                    conn.execute(sa_text_mt4(f"UPDATE {tbl} SET tenant_id = 1 WHERE tenant_id IS NULL"))
                    conn.execute(sa_text_mt4(f"ALTER TABLE {tbl} MODIFY COLUMN tenant_id INT NOT NULL"))
                    conn.execute(sa_text_mt4(f"CREATE INDEX idx_{tbl}_tenant ON {tbl}(tenant_id)"))
                    conn.commit()
                    logger.info(f"Migration: tenant_id added to {tbl}")
    except Exception as e:
        logger.warning(f"Migration check for Phase 4 multi-tenancy: {e}")

    # Migration: encrypt existing plaintext mailbox passwords
    # (must run AFTER Phase 2 multi-tenancy which adds tenant_id to sender_mailboxes)
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

    # Cleanup: mark orphaned pipeline runs as failed on startup
    # (must run AFTER Phase 4 multi-tenancy which adds tenant_id to job_runs)
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

    # Migration: add billing columns to tenants
    try:
        from sqlalchemy import text as sa_text_billing, inspect as sa_inspect_billing
        with engine.connect() as conn:
            inspector_billing = sa_inspect_billing(engine)
            if "tenants" in inspector_billing.get_table_names():
                tenant_cols = [c["name"] for c in inspector_billing.get_columns("tenants")]
                for col_name, col_def in [
                    ("monthly_price_cents", "INT DEFAULT 0 NOT NULL"),
                    ("billing_email", "VARCHAR(255) NULL"),
                    ("billing_address_json", "TEXT NULL"),
                    ("stripe_customer_id", "VARCHAR(100) NULL"),
                    ("tax_rate_percent", "DECIMAL(5,2) DEFAULT 0 NOT NULL"),
                ]:
                    if col_name not in tenant_cols:
                        try:
                            conn.execute(sa_text_billing(f"ALTER TABLE tenants ADD COLUMN {col_name} {col_def}"))
                            conn.commit()
                            logger.info(f"Migration: added {col_name} to tenants")
                        except Exception:
                            pass
                # Add index on stripe_customer_id
                try:
                    conn.execute(sa_text_billing("CREATE INDEX idx_tenants_stripe_customer ON tenants(stripe_customer_id)"))
                    conn.commit()
                    logger.info("Migration: added index idx_tenants_stripe_customer")
                except Exception:
                    pass
    except Exception as e:
        logger.warning(f"Migration check for tenant billing columns: {e}")

    # Migration: add login lockout columns to users
    try:
        from sqlalchemy import text as sa_text_lockout, inspect as sa_inspect_lockout
        with engine.connect() as conn:
            inspector_lockout = sa_inspect_lockout(engine)
            user_cols = [c["name"] for c in inspector_lockout.get_columns("users")]
            for col_name, col_def in [
                ("failed_login_count", "INT DEFAULT 0 NOT NULL"),
                ("locked_until", "DATETIME NULL"),
            ]:
                if col_name not in user_cols:
                    try:
                        conn.execute(sa_text_lockout(f"ALTER TABLE users ADD COLUMN {col_name} {col_def}"))
                        conn.commit()
                        logger.info(f"Migration: added {col_name} to users")
                    except Exception:
                        pass
    except Exception as e:
        logger.warning(f"Migration check for login lockout columns: {e}")

    # Migration: add data_type column to lead_details (test vs prod)
    try:
        from sqlalchemy import text as sa_text_dt, inspect as sa_inspect_dt
        with engine.connect() as conn:
            inspector_dt = sa_inspect_dt(engine)
            lead_cols_dt = [c["name"] for c in inspector_dt.get_columns("lead_details")]
            if "data_type" not in lead_cols_dt:
                try:
                    conn.execute(sa_text_dt(
                        "ALTER TABLE lead_details ADD COLUMN data_type VARCHAR(10) DEFAULT 'prod' NOT NULL"
                    ))
                    conn.commit()
                    logger.info("Migration: added data_type column to lead_details")
                except Exception:
                    pass
    except Exception as e:
        logger.warning(f"Migration check for data_type column: {e}")

    # Migration: add onboarding_dismissed_at column to users
    try:
        from sqlalchemy import text as sa_text_onboard, inspect as sa_inspect_onboard
        with engine.connect() as conn:
            inspector_onboard = sa_inspect_onboard(engine)
            user_cols_onboard = [c["name"] for c in inspector_onboard.get_columns("users")]
            if "onboarding_dismissed_at" not in user_cols_onboard:
                try:
                    conn.execute(sa_text_onboard("ALTER TABLE users ADD COLUMN onboarding_dismissed_at DATETIME NULL"))
                    conn.commit()
                    logger.info("Migration: added onboarding_dismissed_at to users")
                except Exception:
                    pass
    except Exception as e:
        logger.warning(f"Migration check for onboarding_dismissed_at: {e}")

    # ── Migration: Phase 5 — Roadmap features (campaigns, users, leads, mailboxes, tenants) ──
    try:
        from sqlalchemy import text as sa_text_p5, inspect as sa_inspect_p5
        with engine.connect() as conn:
            inspector_p5 = sa_inspect_p5(engine)

            # Campaign model additions
            camp_cols = [c["name"] for c in inspector_p5.get_columns("campaigns")]
            camp_additions = {
                "slow_ramp_enabled": "TINYINT(1) NOT NULL DEFAULT 0",
                "slow_ramp_increment": "INT NOT NULL DEFAULT 2",
                "slow_ramp_current_day": "INT NOT NULL DEFAULT 0",
                "bounce_threshold": "INT NOT NULL DEFAULT 10",
                "spam_threshold": "INT NOT NULL DEFAULT 5",
                "auto_pause_reason": "VARCHAR(255) NULL",
                "auto_reply_enabled": "TINYINT(1) NOT NULL DEFAULT 0",
                "auto_reply_delay_minutes": "INT NOT NULL DEFAULT 5",
                "max_auto_replies_per_thread": "INT NOT NULL DEFAULT 3",
                "assignment_mode": "VARCHAR(20) NOT NULL DEFAULT 'manual'",
            }
            for col_name, col_def in camp_additions.items():
                if col_name not in camp_cols:
                    try:
                        conn.execute(sa_text_p5(f"ALTER TABLE campaigns ADD COLUMN {col_name} {col_def}"))
                        conn.commit()
                        logger.info(f"Migration: added {col_name} to campaigns")
                    except Exception:
                        pass

            # StepType enum update (add sms, linkedin, call)
            try:
                conn.execute(sa_text_p5(
                    "ALTER TABLE sequence_steps MODIFY COLUMN step_type "
                    "ENUM('email','wait','condition','sms','linkedin','call') NOT NULL"
                ))
                conn.commit()
                logger.info("Migration: extended step_type enum")
            except Exception:
                pass

            # User model: calendar_link
            user_cols_p5 = [c["name"] for c in inspector_p5.get_columns("users")]
            if "calendar_link" not in user_cols_p5:
                try:
                    conn.execute(sa_text_p5("ALTER TABLE users ADD COLUMN calendar_link VARCHAR(500) NULL"))
                    conn.commit()
                    logger.info("Migration: added calendar_link to users")
                except Exception:
                    pass

            # Lead model: assigned_to
            lead_cols_p5 = [c["name"] for c in inspector_p5.get_columns("lead_details")]
            if "assigned_to" not in lead_cols_p5:
                try:
                    conn.execute(sa_text_p5("ALTER TABLE lead_details ADD COLUMN assigned_to INT NULL"))
                    conn.commit()
                    logger.info("Migration: added assigned_to to lead_details")
                except Exception:
                    pass

            # SenderMailbox: dedicated_ip
            mb_cols_p5 = [c["name"] for c in inspector_p5.get_columns("sender_mailboxes")]
            if "dedicated_ip" not in mb_cols_p5:
                try:
                    conn.execute(sa_text_p5("ALTER TABLE sender_mailboxes ADD COLUMN dedicated_ip VARCHAR(45) NULL"))
                    conn.commit()
                    logger.info("Migration: added dedicated_ip to sender_mailboxes")
                except Exception:
                    pass

            # Tenant model: white-label / agency fields
            tenant_cols_p5 = [c["name"] for c in inspector_p5.get_columns("tenants")]
            tenant_additions = {
                "brand_name": "VARCHAR(255) NULL",
                "brand_logo_url": "VARCHAR(500) NULL",
                "brand_primary_color": "VARCHAR(7) NULL",
                "brand_secondary_color": "VARCHAR(7) NULL",
                "custom_domain": "VARCHAR(255) NULL",
                "agency_mode": "TINYINT(1) NOT NULL DEFAULT 0",
            }
            for col_name, col_def in tenant_additions.items():
                if col_name not in tenant_cols_p5:
                    try:
                        conn.execute(sa_text_p5(f"ALTER TABLE tenants ADD COLUMN {col_name} {col_def}"))
                        conn.commit()
                        logger.info(f"Migration: added {col_name} to tenants")
                    except Exception:
                        pass

    except Exception as e:
        logger.warning(f"Migration check for Phase 5 roadmap: {e}")

    # Migration: add preview_mode column to campaigns
    try:
        from sqlalchemy import text as sa_text_preview, inspect as sa_inspect_preview
        with engine.connect() as conn:
            inspector_prev = sa_inspect_preview(engine)
            camp_cols = [c["name"] for c in inspector_prev.get_columns("campaigns")]
            if "preview_mode" not in camp_cols:
                conn.execute(sa_text_preview(
                    "ALTER TABLE campaigns ADD COLUMN preview_mode TINYINT(1) NOT NULL DEFAULT 0"
                ))
                conn.commit()
                logger.info("Migration: added preview_mode column to campaigns")
    except Exception as e:
        logger.warning(f"Migration check for preview_mode: {e}")

    # Migration: add website + industry columns to tenants
    try:
        from sqlalchemy import text as sa_text_tenant_profile, inspect as sa_inspect_tenant_profile
        with engine.connect() as conn:
            inspector_tp = sa_inspect_tenant_profile(engine)
            tenant_cols_tp = [c["name"] for c in inspector_tp.get_columns("tenants")]
            for col_name, col_def in [("website", "VARCHAR(500) NULL"), ("industry", "VARCHAR(100) NULL")]:
                if col_name not in tenant_cols_tp:
                    try:
                        conn.execute(sa_text_tenant_profile(f"ALTER TABLE tenants ADD COLUMN {col_name} {col_def}"))
                        conn.commit()
                        logger.info(f"Migration: added {col_name} to tenants")
                    except Exception:
                        pass
    except Exception as e:
        logger.warning(f"Migration check for tenant website/industry: {e}")

    # Migration: cleanup orphaned campaign_contacts for archived campaigns
    # and reset lead_status to 'enriched' for leads no longer in any active campaign
    try:
        from sqlalchemy import text as sa_text_orphan
        with engine.connect() as conn:
            # Find leads linked to archived campaigns via leftover campaign_contacts
            orphan_rows = conn.execute(sa_text_orphan(
                "SELECT DISTINCT cc.lead_id FROM campaign_contacts cc "
                "JOIN campaigns c ON cc.campaign_id = c.campaign_id "
                "WHERE c.is_archived = 1 AND cc.lead_id IS NOT NULL"
            )).fetchall()
            orphan_lead_ids = [r[0] for r in orphan_rows]
            if orphan_lead_ids:
                # Delete the orphaned campaign_contact records
                conn.execute(sa_text_orphan(
                    "DELETE cc FROM campaign_contacts cc "
                    "JOIN campaigns c ON cc.campaign_id = c.campaign_id "
                    "WHERE c.is_archived = 1"
                ))
                # Find which of those leads are still in a non-archived campaign
                placeholders = ",".join(str(lid) for lid in orphan_lead_ids)
                still_enrolled_rows = conn.execute(sa_text_orphan(
                    f"SELECT DISTINCT cc.lead_id FROM campaign_contacts cc "
                    f"JOIN campaigns c ON cc.campaign_id = c.campaign_id "
                    f"WHERE cc.lead_id IN ({placeholders}) AND c.is_archived = 0"
                )).fetchall()
                still_enrolled = {r[0] for r in still_enrolled_rows}
                reset_ids = [lid for lid in orphan_lead_ids if lid not in still_enrolled]
                if reset_ids:
                    reset_placeholders = ",".join(str(lid) for lid in reset_ids)
                    conn.execute(sa_text_orphan(
                        f"UPDATE lead_details SET lead_status = 'enriched' "
                        f"WHERE lead_id IN ({reset_placeholders})"
                    ))
                    logger.info(f"Migration: reset {len(reset_ids)} leads to enriched (orphaned from archived campaigns)")
                conn.commit()
                logger.info(f"Migration: cleaned up campaign_contacts for {len(orphan_lead_ids)} leads in archived campaigns")
    except Exception as e:
        logger.warning(f"Migration check for orphaned campaign_contacts: {e}")

    # Migration: add composite indexes for hot-path queries
    try:
        from sqlalchemy import text as sa_text_idx
        if settings.DB_TYPE == "mysql":
            with engine.connect() as conn:
                composite_indexes = [
                    ("idx_oe_campaign_status", "outreach_events", "(campaign_id, status)"),
                    ("idx_cc_campaign_status_send", "campaign_contacts", "(campaign_id, status, next_send_at)"),
                    ("idx_cd_tenant_client", "contact_details", "(tenant_id, client_name(191))"),
                    ("idx_ld_tenant_status", "lead_details", "(tenant_id, lead_status)"),
                    ("idx_im_tenant_thread", "inbox_messages", "(tenant_id, thread_id)"),
                    ("idx_oe_contact_sent", "outreach_events", "(contact_id, sent_at)"),
                    ("idx_inv_status_due", "invoices", "(status, due_date)"),
                ]
                for idx_name, table, cols in composite_indexes:
                    try:
                        conn.execute(sa_text_idx(
                            f"CREATE INDEX {idx_name} ON {table} {cols}"
                        ))
                        conn.commit()
                        logger.info(f"Migration: added composite index {idx_name}")
                    except Exception:
                        pass  # Index already exists
    except Exception as e:
        logger.warning(f"Migration check for composite indexes: {e}")

    # Migration: add category column to email_templates
    try:
        with engine.connect() as conn:
            from sqlalchemy import text as sa_text_tmpl_cat
            cols = [r[0].lower() for r in conn.execute(sa_text_tmpl_cat("SHOW COLUMNS FROM email_templates")).fetchall()]
            if "category" not in cols:
                conn.execute(sa_text_tmpl_cat(
                    "ALTER TABLE email_templates ADD COLUMN category VARCHAR(20) NOT NULL DEFAULT 'outreach'"
                ))
                conn.commit()
                logger.info("Migration: added category column to email_templates")
            # Add composite index for per-category active lookup
            try:
                conn.execute(sa_text_tmpl_cat(
                    "CREATE INDEX idx_template_tenant_category_status ON email_templates (tenant_id, category, status)"
                ))
                conn.commit()
                logger.info("Migration: added idx_template_tenant_category_status index")
            except Exception:
                pass  # Index already exists
    except Exception as e:
        logger.warning(f"Migration check for email_templates category: {e}")

    # Migration: add scheduled_send_at, sending_speed, health_score to campaigns
    try:
        from sqlalchemy import text as sa_text_camp_new, inspect as sa_inspect_camp_new
        with engine.connect() as conn:
            inspector_cn = sa_inspect_camp_new(engine)
            camp_cols_new = [c["name"] for c in inspector_cn.get_columns("campaigns")]
            if "scheduled_send_at" not in camp_cols_new:
                conn.execute(sa_text_camp_new(
                    "ALTER TABLE campaigns ADD COLUMN scheduled_send_at DATETIME NULL"
                ))
                conn.commit()
                logger.info("Migration: added scheduled_send_at column to campaigns")
            if "sending_speed" not in camp_cols_new:
                conn.execute(sa_text_camp_new(
                    "ALTER TABLE campaigns ADD COLUMN sending_speed VARCHAR(20) NOT NULL DEFAULT 'normal'"
                ))
                conn.commit()
                logger.info("Migration: added sending_speed column to campaigns")
            if "health_score" not in camp_cols_new:
                conn.execute(sa_text_camp_new(
                    "ALTER TABLE campaigns ADD COLUMN health_score INT NULL"
                ))
                conn.commit()
                logger.info("Migration: added health_score column to campaigns")
    except Exception as e:
        logger.warning(f"Migration check for campaign new columns: {e}")

    # Migration: Template library enhancement — add industry, goal, is_system columns
    try:
        from sqlalchemy import text as sa_text_tmpl_lib, inspect as sa_inspect_tmpl_lib
        with engine.connect() as conn:
            inspector_tmpl = sa_inspect_tmpl_lib(engine)
            tmpl_cols = [c["name"] for c in inspector_tmpl.get_columns("email_templates")]
            for col, coldef in [("industry", "VARCHAR(50) NULL"), ("goal", "VARCHAR(50) NULL"), ("is_system", "TINYINT(1) DEFAULT 0")]:
                if col not in tmpl_cols:
                    try:
                        conn.execute(sa_text_tmpl_lib(f"ALTER TABLE email_templates ADD COLUMN {col} {coldef}"))
                        conn.commit()
                        logger.info(f"Migration: added {col} to email_templates")
                    except Exception:
                        pass
    except Exception as e:
        logger.warning(f"Migration check for template library columns: {e}")

    # Migration: add opened_at, clicked_at to outreach_events
    try:
        from sqlalchemy import text as sa_text_oe_track, inspect as sa_inspect_oe_track
        with engine.connect() as conn:
            inspector_oe = sa_inspect_oe_track(engine)
            oe_cols = [c["name"] for c in inspector_oe.get_columns("outreach_events")]
            if "opened_at" not in oe_cols:
                conn.execute(sa_text_oe_track(
                    "ALTER TABLE outreach_events ADD COLUMN opened_at DATETIME NULL"
                ))
                conn.commit()
                logger.info("Migration: added opened_at column to outreach_events")
            if "clicked_at" not in oe_cols:
                conn.execute(sa_text_oe_track(
                    "ALTER TABLE outreach_events ADD COLUMN clicked_at DATETIME NULL"
                ))
                conn.commit()
                logger.info("Migration: added clicked_at column to outreach_events")
    except Exception as e:
        logger.warning(f"Migration check for outreach_events tracking columns: {e}")

    # Migration: add timezone column to client_info + backfill from location_state
    try:
        from sqlalchemy import text as sa_text_tz, inspect as sa_inspect_tz
        with engine.connect() as conn:
            inspector_tz = sa_inspect_tz(engine)
            ci_cols = [c["name"] for c in inspector_tz.get_columns("client_info")]
            if "timezone" not in ci_cols:
                conn.execute(sa_text_tz(
                    "ALTER TABLE client_info ADD COLUMN timezone VARCHAR(50) NULL"
                ))
                conn.commit()
                logger.info("Migration: added timezone column to client_info")
            # Backfill timezone from location_state for existing clients
            result = conn.execute(sa_text_tz(
                "UPDATE client_info SET timezone = CASE location_state "
                "WHEN 'AL' THEN 'America/Chicago' WHEN 'AK' THEN 'America/Anchorage' "
                "WHEN 'AZ' THEN 'America/Phoenix' WHEN 'AR' THEN 'America/Chicago' "
                "WHEN 'CA' THEN 'America/Los_Angeles' WHEN 'CO' THEN 'America/Denver' "
                "WHEN 'CT' THEN 'America/New_York' WHEN 'DE' THEN 'America/New_York' "
                "WHEN 'FL' THEN 'America/New_York' WHEN 'GA' THEN 'America/New_York' "
                "WHEN 'HI' THEN 'Pacific/Honolulu' WHEN 'ID' THEN 'America/Boise' "
                "WHEN 'IL' THEN 'America/Chicago' WHEN 'IN' THEN 'America/Indiana/Indianapolis' "
                "WHEN 'IA' THEN 'America/Chicago' WHEN 'KS' THEN 'America/Chicago' "
                "WHEN 'KY' THEN 'America/New_York' WHEN 'LA' THEN 'America/Chicago' "
                "WHEN 'ME' THEN 'America/New_York' WHEN 'MD' THEN 'America/New_York' "
                "WHEN 'MA' THEN 'America/New_York' WHEN 'MI' THEN 'America/Detroit' "
                "WHEN 'MN' THEN 'America/Chicago' WHEN 'MS' THEN 'America/Chicago' "
                "WHEN 'MO' THEN 'America/Chicago' WHEN 'MT' THEN 'America/Denver' "
                "WHEN 'NE' THEN 'America/Chicago' WHEN 'NV' THEN 'America/Los_Angeles' "
                "WHEN 'NH' THEN 'America/New_York' WHEN 'NJ' THEN 'America/New_York' "
                "WHEN 'NM' THEN 'America/Denver' WHEN 'NY' THEN 'America/New_York' "
                "WHEN 'NC' THEN 'America/New_York' WHEN 'ND' THEN 'America/Chicago' "
                "WHEN 'OH' THEN 'America/New_York' WHEN 'OK' THEN 'America/Chicago' "
                "WHEN 'OR' THEN 'America/Los_Angeles' WHEN 'PA' THEN 'America/New_York' "
                "WHEN 'RI' THEN 'America/New_York' WHEN 'SC' THEN 'America/New_York' "
                "WHEN 'SD' THEN 'America/Chicago' WHEN 'TN' THEN 'America/Chicago' "
                "WHEN 'TX' THEN 'America/Chicago' WHEN 'UT' THEN 'America/Denver' "
                "WHEN 'VT' THEN 'America/New_York' WHEN 'VA' THEN 'America/New_York' "
                "WHEN 'WA' THEN 'America/Los_Angeles' WHEN 'WV' THEN 'America/New_York' "
                "WHEN 'WI' THEN 'America/Chicago' WHEN 'WY' THEN 'America/Denver' "
                "WHEN 'DC' THEN 'America/New_York' "
                "END WHERE timezone IS NULL AND location_state IS NOT NULL"
            ))
            conn.commit()
            logger.info(f"Migration: backfilled timezone for client_info rows")
            # Also backfill contact_details timezone from location_state
            conn.execute(sa_text_tz(
                "UPDATE contact_details SET timezone = CASE location_state "
                "WHEN 'AL' THEN 'America/Chicago' WHEN 'AK' THEN 'America/Anchorage' "
                "WHEN 'AZ' THEN 'America/Phoenix' WHEN 'AR' THEN 'America/Chicago' "
                "WHEN 'CA' THEN 'America/Los_Angeles' WHEN 'CO' THEN 'America/Denver' "
                "WHEN 'CT' THEN 'America/New_York' WHEN 'DE' THEN 'America/New_York' "
                "WHEN 'FL' THEN 'America/New_York' WHEN 'GA' THEN 'America/New_York' "
                "WHEN 'HI' THEN 'Pacific/Honolulu' WHEN 'ID' THEN 'America/Boise' "
                "WHEN 'IL' THEN 'America/Chicago' WHEN 'IN' THEN 'America/Indiana/Indianapolis' "
                "WHEN 'IA' THEN 'America/Chicago' WHEN 'KS' THEN 'America/Chicago' "
                "WHEN 'KY' THEN 'America/New_York' WHEN 'LA' THEN 'America/Chicago' "
                "WHEN 'ME' THEN 'America/New_York' WHEN 'MD' THEN 'America/New_York' "
                "WHEN 'MA' THEN 'America/New_York' WHEN 'MI' THEN 'America/Detroit' "
                "WHEN 'MN' THEN 'America/Chicago' WHEN 'MS' THEN 'America/Chicago' "
                "WHEN 'MO' THEN 'America/Chicago' WHEN 'MT' THEN 'America/Denver' "
                "WHEN 'NE' THEN 'America/Chicago' WHEN 'NV' THEN 'America/Los_Angeles' "
                "WHEN 'NH' THEN 'America/New_York' WHEN 'NJ' THEN 'America/New_York' "
                "WHEN 'NM' THEN 'America/Denver' WHEN 'NY' THEN 'America/New_York' "
                "WHEN 'NC' THEN 'America/New_York' WHEN 'ND' THEN 'America/Chicago' "
                "WHEN 'OH' THEN 'America/New_York' WHEN 'OK' THEN 'America/Chicago' "
                "WHEN 'OR' THEN 'America/Los_Angeles' WHEN 'PA' THEN 'America/New_York' "
                "WHEN 'RI' THEN 'America/New_York' WHEN 'SC' THEN 'America/New_York' "
                "WHEN 'SD' THEN 'America/Chicago' WHEN 'TN' THEN 'America/Chicago' "
                "WHEN 'TX' THEN 'America/Chicago' WHEN 'UT' THEN 'America/Denver' "
                "WHEN 'VT' THEN 'America/New_York' WHEN 'VA' THEN 'America/New_York' "
                "WHEN 'WA' THEN 'America/Los_Angeles' WHEN 'WV' THEN 'America/New_York' "
                "WHEN 'WI' THEN 'America/Chicago' WHEN 'WY' THEN 'America/Denver' "
                "WHEN 'DC' THEN 'America/New_York' "
                "END WHERE timezone IS NULL AND location_state IS NOT NULL"
            ))
            conn.commit()
            logger.info(f"Migration: backfilled timezone for contact_details rows")
    except Exception as e:
        logger.warning(f"Migration check for timezone columns: {e}")

    # Migration: add data_type to client_info
    try:
        from sqlalchemy import text as sa_text_cdt
        with engine.connect() as conn:
            ci_cols = [r[0].lower() for r in conn.execute(sa_text_cdt("SHOW COLUMNS FROM client_info")).fetchall()]
            if "data_type" not in ci_cols:
                conn.execute(sa_text_cdt("ALTER TABLE client_info ADD COLUMN data_type VARCHAR(20) DEFAULT 'enriched' NOT NULL"))
                conn.commit()
                logger.info("Migration: added data_type column to client_info")
    except Exception as e:
        logger.warning(f"Migration check for client_info.data_type: {e}")

    _seed_warmup_profiles()
    _seed_default_email_template()
    _seed_deal_stages()
    _seed_outreach_roles()

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

    # Seed demo data for Neuraforz and Medeoan tenants (if they have no data yet)
    try:
        from app.services.demo_seeder import seed_demo_data
        from app.db.base import SessionLocal as _DemoSeedSession
        from sqlalchemy import text as _demo_text
        _demo_db = _DemoSeedSession()
        try:
            for _slug in ("neuraforz", "medeoan"):
                _tid = _demo_db.execute(_demo_text(
                    "SELECT tenant_id FROM tenants WHERE slug = :s"
                ), {"s": _slug}).scalar()
                if _tid:
                    _result = seed_demo_data(_tid, _demo_db)
                    if any(v > 0 for v in _result.values()):
                        logger.info(f"Demo data seeded for {_slug}", **_result)
        finally:
            _demo_db.close()
    except Exception as e:
        logger.warning(f"Demo data seeding: {e}")

    # ── Migration: Change contact_details.lead_id FK from CASCADE to SET NULL ──
    # Contacts must survive lead deletion to preserve the database
    try:
        from sqlalchemy import text as sa_text_fk
        with engine.connect() as conn:
            # Check if the FK still uses CASCADE by inspecting information_schema
            fk_info = conn.execute(sa_text_fk(
                "SELECT DELETE_RULE FROM information_schema.REFERENTIAL_CONSTRAINTS "
                "WHERE CONSTRAINT_SCHEMA = DATABASE() "
                "AND TABLE_NAME = 'contact_details' "
                "AND REFERENCED_TABLE_NAME = 'lead_details' "
                "LIMIT 1"
            )).scalar()
            if fk_info and fk_info.upper() == 'CASCADE':
                # Find the constraint name
                fk_name = conn.execute(sa_text_fk(
                    "SELECT CONSTRAINT_NAME FROM information_schema.REFERENTIAL_CONSTRAINTS "
                    "WHERE CONSTRAINT_SCHEMA = DATABASE() "
                    "AND TABLE_NAME = 'contact_details' "
                    "AND REFERENCED_TABLE_NAME = 'lead_details' "
                    "LIMIT 1"
                )).scalar()
                if fk_name:
                    conn.execute(sa_text_fk(f"ALTER TABLE contact_details DROP FOREIGN KEY {fk_name}"))
                    conn.execute(sa_text_fk(
                        "ALTER TABLE contact_details ADD CONSTRAINT fk_contact_lead "
                        "FOREIGN KEY (lead_id) REFERENCES lead_details(lead_id) ON DELETE SET NULL"
                    ))
                    conn.commit()
                    logger.info("Migrated contact_details.lead_id FK from CASCADE to SET NULL")
    except Exception as e:
        logger.debug(f"FK migration check (may already be done): {e}")

    # --- Migration: Add employment_type column to lead_details ---
    try:
        with engine.connect() as conn:
            from sqlalchemy import text as sa_text_emptype
            cols = [r[0].lower() for r in conn.execute(sa_text_emptype("SHOW COLUMNS FROM lead_details")).fetchall()]
            if "employment_type" not in cols:
                conn.execute(sa_text_emptype(
                    "ALTER TABLE lead_details ADD COLUMN employment_type VARCHAR(50) NULL"
                ))
                conn.commit()
                logger.info("Migration: Added employment_type column to lead_details")
    except Exception as e:
        logger.debug(f"employment_type migration check: {e}")

    # --- Migration: Add data_type column to contact_details ---
    try:
        with engine.connect() as conn:
            from sqlalchemy import text as sa_text_datatype
            contact_cols = [r[0].lower() for r in conn.execute(sa_text_datatype("SHOW COLUMNS FROM contact_details")).fetchall()]
            if "data_type" not in contact_cols:
                conn.execute(sa_text_datatype(
                    "ALTER TABLE contact_details ADD COLUMN data_type VARCHAR(20) DEFAULT 'enriched' NOT NULL"
                ))
                conn.commit()
                logger.info("Migration: Added data_type column to contact_details")
    except Exception as e:
        logger.debug(f"data_type migration check: {e}")

    # --- Migration: Backfill campaign_schedules from legacy campaign columns ---
    try:
        with engine.connect() as conn:
            from sqlalchemy import text as sa_text_cs
            # Check if table exists and is empty
            try:
                count_row = conn.execute(sa_text_cs("SELECT COUNT(*) FROM campaign_schedules")).fetchone()
                cs_count = count_row[0] if count_row else 0
            except Exception:
                cs_count = -1  # Table doesn't exist yet (create_all will handle it)

            if cs_count == 0:
                # Backfill: create one schedule row per non-archived campaign
                campaigns_rows = conn.execute(sa_text_cs(
                    "SELECT campaign_id, tenant_id, timezone, send_window_start, send_window_end, "
                    "send_days_json, created_at FROM campaigns WHERE is_archived = 0"
                )).fetchall()
                for row in campaigns_rows:
                    cid, tid, tz, sw_start, sw_end, days_json, created_at = row
                    start_date = created_at.strftime("%Y-%m-%d") if created_at else "2024-01-01"
                    conn.execute(sa_text_cs(
                        "INSERT INTO campaign_schedules "
                        "(campaign_id, tenant_id, start_date, end_date, send_window_start, "
                        "send_window_end, send_days_json, timezone, schedule_order, label, "
                        "created_at, updated_at, is_archived) "
                        "VALUES (:cid, :tid, :sd, NULL, :sws, :swe, :dj, :tz, 1, 'Default', "
                        "NOW(), NOW(), 0)"
                    ), {
                        "cid": cid, "tid": tid, "sd": start_date,
                        "sws": sw_start or "09:00", "swe": sw_end or "17:00",
                        "dj": days_json or '["mon","tue","wed","thu","fri"]',
                        "tz": tz or "UTC",
                    })
                conn.commit()
                if campaigns_rows:
                    logger.info(f"Migration: Backfilled {len(campaigns_rows)} campaign_schedules rows")
    except Exception as e:
        logger.debug(f"campaign_schedules backfill check: {e}")

    # --- Add linkedin_url column to contact_details ---
    try:
        with engine.connect() as conn:
            from sqlalchemy import text as _li_text
            cols = [r[0] for r in conn.execute(_li_text("SHOW COLUMNS FROM contact_details")).fetchall()]
            if "linkedin_url" not in cols:
                conn.execute(_li_text("ALTER TABLE contact_details ADD COLUMN linkedin_url VARCHAR(500) NULL AFTER phone"))
                conn.commit()
                logger.info("Migration: Added linkedin_url column to contact_details")
    except Exception as e:
        logger.debug(f"linkedin_url migration check: {e}")

    # Release MySQL advisory lock after migrations complete
    if _migration_lock_conn and _got_lock:
        try:
            from sqlalchemy import text as _unlock_text
            _migration_lock_conn.execute(_unlock_text("SELECT RELEASE_LOCK('exzelon_migration')"))
            _migration_lock_conn.close()
            logger.info("Released migration lock")
        except Exception as unlock_err:
            logger.warning(f"Failed to release migration lock: {unlock_err}")
    elif _migration_lock_conn:
        try:
            _migration_lock_conn.close()
        except Exception:
            pass

    # Start warmup scheduler — only ONE worker should run it.
    # Use a file lock so that in multi-worker deployments (e.g. 4 uvicorn workers),
    # only the first worker to acquire the lock starts the scheduler.
    _scheduler_lock_fd = None
    import sys
    if sys.platform != "win32":
        import fcntl
        try:
            _lock_path = "/tmp/exzelon-scheduler.lock"
            _scheduler_lock_fd = open(_lock_path, "w")
            fcntl.flock(_scheduler_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            # Lock acquired — this worker owns the scheduler
            from app.services.warmup.scheduler import init_scheduler
            init_scheduler()
            logger.info("Scheduler started (lock acquired)", lock_path=_lock_path)
        except OSError:
            # Another worker already holds the lock — skip scheduler
            if _scheduler_lock_fd:
                _scheduler_lock_fd.close()
                _scheduler_lock_fd = None
            logger.info("Scheduler skipped (another worker owns the lock)")
        except Exception as e:
            logger.error("Failed to start warmup scheduler", error=str(e))
    else:
        # Windows dev: single worker, always start scheduler
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
    # Release scheduler lock if we hold it
    if _scheduler_lock_fd:
        try:
            import fcntl as _fcntl
            _fcntl.flock(_scheduler_lock_fd, _fcntl.LOCK_UN)
            _scheduler_lock_fd.close()
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
from app.core.rate_limiter import limiter
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
    allow_headers=["Authorization", "Content-Type", "X-Tenant-ID"],
    expose_headers=["Content-Disposition"],
)

# Security headers (runs after CORS so CORS headers are already set)
app.add_middleware(SecurityHeadersMiddleware)

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
                db.add(SuppressionList(tenant_id=getattr(contact, 'tenant_id', None) or 1, email=contact.email.lower(), reason="unsubscribe_link"))

            # Update contact status
            contact.outreach_status = ContactOutreachStatus.UNSUBSCRIBED
            contact.unsubscribed_at = datetime.utcnow()

            # Audit log
            db.add(AuditLog(
                tenant_id=getattr(contact, 'tenant_id', None) or 1,
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
