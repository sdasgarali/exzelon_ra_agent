"""Data retention service - purges old archived records."""
from datetime import datetime, timedelta
import structlog
from app.db.base import SessionLocal
from app.db.models.lead import LeadDetails
from app.db.models.contact import ContactDetails
from app.core.config import settings

logger = structlog.get_logger()


def purge_archived_records():
    """Purge archived records older than data_retention_days setting.

    This runs as a scheduled job. Only removes records that have been
    archived (soft-deleted) for longer than the retention period.
    Reads from DB settings table, falls back to config.py DATA_RETENTION_DAYS.
    """
    db = SessionLocal()
    try:
        from app.core.settings_resolver import get_tenant_setting
        _rd = get_tenant_setting(db, "data_retention_days", default=None)
        retention_days = int(_rd) if _rd is not None else settings.DATA_RETENTION_DAYS
        cutoff = datetime.utcnow() - timedelta(days=retention_days)

        # Purge old archived leads
        leads_deleted = db.query(LeadDetails).filter(
            LeadDetails.is_archived == True,
            LeadDetails.updated_at < cutoff
        ).delete(synchronize_session=False)

        # Purge old archived contacts
        contacts_deleted = db.query(ContactDetails).filter(
            ContactDetails.is_archived == True,
            ContactDetails.updated_at < cutoff
        ).delete(synchronize_session=False)

        db.commit()

        if leads_deleted or contacts_deleted:
            logger.info(
                "Purged archived records",
                leads=leads_deleted,
                contacts=contacts_deleted,
                retention_days=retention_days,
            )
    except Exception as e:
        db.rollback()
        logger.error("Failed to purge archived records", error=str(e))
    finally:
        db.close()
