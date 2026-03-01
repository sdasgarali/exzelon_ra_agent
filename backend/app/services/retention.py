"""Data retention service - purges old archived records."""
from datetime import datetime, timedelta
import structlog
from app.db.base import SessionLocal
from app.db.models.lead import LeadDetails
from app.db.models.contact import ContactDetails
from app.core.config import settings
from app.core.tenant_context import set_current_tenant_id, get_current_tenant_id
from app.db.query_helpers import tenant_query

logger = structlog.get_logger()


def purge_archived_records():
    """Purge archived records older than DATA_RETENTION_DAYS.

    This runs as a scheduled job. Only removes records that have been
    archived (soft-deleted) for longer than the retention period.
    Iterates over all active tenants for tenant-scoped purging.
    """
    db = SessionLocal()
    try:
        from app.db.models.tenant import Tenant
        cutoff = datetime.utcnow() - timedelta(days=settings.DATA_RETENTION_DAYS)

        tenants = db.query(Tenant).filter(Tenant.is_active == True).all()
        for tenant in tenants:
            set_current_tenant_id(tenant.tenant_id)
            try:
                # Purge old archived leads
                leads_deleted = tenant_query(db, LeadDetails).filter(
                    LeadDetails.is_archived == True,
                    LeadDetails.updated_at < cutoff
                ).delete(synchronize_session=False)

                # Purge old archived contacts
                contacts_deleted = tenant_query(db, ContactDetails).filter(
                    ContactDetails.is_archived == True,
                    ContactDetails.updated_at < cutoff
                ).delete(synchronize_session=False)

                db.commit()

                if leads_deleted or contacts_deleted:
                    logger.info(
                        "Purged archived records",
                        tenant_id=tenant.tenant_id,
                        leads=leads_deleted,
                        contacts=contacts_deleted,
                        retention_days=settings.DATA_RETENTION_DAYS
                    )
            except Exception as e:
                db.rollback()
                logger.error("Failed to purge archived records for tenant", tenant_id=tenant.tenant_id, error=str(e))
    except Exception as e:
        db.rollback()
        logger.error("Failed to purge archived records", error=str(e))
    finally:
        db.close()
