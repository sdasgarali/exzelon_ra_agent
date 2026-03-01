"""Database models package."""
from app.db.models.tenant import Tenant
from app.db.models.permission import Permission, RolePermission
from app.db.models.user import User
from app.db.models.lead import LeadDetails
from app.db.models.client import ClientInfo
from app.db.models.contact import ContactDetails
from app.db.models.lead_contact import LeadContactAssociation
from app.db.models.email_validation import EmailValidationResult
from app.db.models.outreach import OutreachEvent
from app.db.models.suppression import SuppressionList
from app.db.models.job_run import JobRun
from app.db.models.settings import Settings
from app.db.models.sender_mailbox import SenderMailbox, WarmupStatus, EmailProvider
from app.db.models.warmup_email import WarmupEmail, WarmupEmailStatus
from app.db.models.warmup_daily_log import WarmupDailyLog
from app.db.models.warmup_alert import WarmupAlert, AlertType, AlertSeverity
from app.db.models.warmup_profile import WarmupProfile
from app.db.models.dns_check_result import DNSCheckResult
from app.db.models.blacklist_check_result import BlacklistCheckResult
from app.db.models.email_template import EmailTemplate, TemplateStatus

__all__ = [
    "Tenant",
    "Permission",
    "RolePermission",
    "User",
    "LeadDetails",
    "ClientInfo",
    "ContactDetails",
    "LeadContactAssociation",
    "EmailValidationResult",
    "OutreachEvent",
    "SuppressionList",
    "JobRun",
    "Settings",
    "SenderMailbox",
    "WarmupStatus",
    "EmailProvider",
    "WarmupEmail",
    "WarmupEmailStatus",
    "WarmupDailyLog",
    "WarmupAlert",
    "AlertType",
    "AlertSeverity",
    "WarmupProfile",
    "DNSCheckResult",
    "BlacklistCheckResult",
    "EmailTemplate",
    "TemplateStatus",
]
