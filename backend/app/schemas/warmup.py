"""Pydantic schemas for warmup engine."""
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from pydantic import BaseModel


class WarmupPhaseConfig(BaseModel):
    """Configuration for a single warmup phase."""
    days: int = 7
    min_emails: int = 2
    max_emails: int = 5


class WarmupConfig(BaseModel):
    """Full warmup configuration."""
    phase_1: WarmupPhaseConfig = WarmupPhaseConfig(days=7, min_emails=2, max_emails=5)
    phase_2: WarmupPhaseConfig = WarmupPhaseConfig(days=7, min_emails=5, max_emails=15)
    phase_3: WarmupPhaseConfig = WarmupPhaseConfig(days=7, min_emails=15, max_emails=25)
    phase_4: WarmupPhaseConfig = WarmupPhaseConfig(days=9, min_emails=25, max_emails=35)
    bounce_rate_good: float = 2.0
    bounce_rate_bad: float = 5.0
    reply_rate_good: float = 10.0
    complaint_rate_bad: float = 0.1
    weight_bounce_rate: int = 35
    weight_reply_rate: int = 25
    weight_complaint_rate: int = 25
    weight_age: int = 15
    auto_pause_bounce_rate: float = 5.0
    auto_pause_complaint_rate: float = 0.3
    min_emails_for_scoring: int = 10
    active_health_threshold: int = 80
    active_min_days: int = 7
    total_days: int = 30
    daily_increment: float = 1.0


class WarmupConfigUpdate(BaseModel):
    """Schema for updating warmup configuration."""
    phase_1: Optional[WarmupPhaseConfig] = None
    phase_2: Optional[WarmupPhaseConfig] = None
    phase_3: Optional[WarmupPhaseConfig] = None
    phase_4: Optional[WarmupPhaseConfig] = None
    bounce_rate_good: Optional[float] = None
    bounce_rate_bad: Optional[float] = None
    reply_rate_good: Optional[float] = None
    complaint_rate_bad: Optional[float] = None
    weight_bounce_rate: Optional[int] = None
    weight_reply_rate: Optional[int] = None
    weight_complaint_rate: Optional[int] = None
    weight_age: Optional[int] = None
    auto_pause_bounce_rate: Optional[float] = None
    auto_pause_complaint_rate: Optional[float] = None
    min_emails_for_scoring: Optional[int] = None
    active_health_threshold: Optional[int] = None
    active_min_days: Optional[int] = None
    total_days: Optional[int] = None
    daily_increment: Optional[float] = None


class MailboxWarmupStatus(BaseModel):
    """Per-mailbox warmup detail."""
    mailbox_id: int
    email: str
    display_name: Optional[str] = None
    warmup_status: str
    is_active: bool
    warmup_day: int = 0
    warmup_phase: int = 0
    phase_name: str = ""
    health_score: float = 0.0
    daily_limit: int = 0
    emails_sent_today: int = 0
    total_emails_sent: int = 0
    bounce_rate: float = 0.0
    reply_rate: float = 0.0
    complaint_rate: float = 0.0
    warmup_started_at: Optional[datetime] = None
    warmup_completed_at: Optional[datetime] = None
    last_assessed_at: Optional[datetime] = None
    connection_status: str = "untested"
    dns_score: int = 0
    is_blacklisted: bool = False
    warmup_profile_id: Optional[int] = None

    class Config:
        from_attributes = True


class WarmupStatusResponse(BaseModel):
    """All mailboxes warmup status + aggregate stats."""
    mailboxes: List[MailboxWarmupStatus]
    total_mailboxes: int = 0
    warming_up_count: int = 0
    cold_ready_count: int = 0
    active_count: int = 0
    paused_count: int = 0
    recovering_count: int = 0
    avg_health_score: float = 0.0
    dns_issues_count: int = 0


class WarmupAssessmentResult(BaseModel):
    """Assessment output with status changes."""
    run_id: Optional[int] = None
    assessed: int = 0
    status_changes: int = 0
    auto_paused: int = 0
    promoted: int = 0
    errors: int = 0
    details: List[Dict[str, Any]] = []


class WarmupScheduleDay(BaseModel):
    """Single day in warmup schedule."""
    day: int
    phase: int
    phase_name: str
    recommended_emails: int


class WarmupScheduleResponse(BaseModel):
    """Day-by-day warmup schedule."""
    total_days: int
    phases: List[Dict[str, Any]]
    schedule: List[WarmupScheduleDay]


class MailboxHealthScore(BaseModel):
    """Health score breakdown for a mailbox."""
    mailbox_id: int
    email: str
    health_score: float
    bounce_score: float = 0.0
    reply_score: float = 0.0
    complaint_score: float = 0.0
    age_score: float = 0.0
    bounce_rate: float = 0.0
    reply_rate: float = 0.0
    complaint_rate: float = 0.0
    account_age_days: int = 0


class HealthScoresResponse(BaseModel):
    """Health scores for all mailboxes."""
    mailboxes: List[MailboxHealthScore]
    avg_health_score: float = 0.0


# === Enterprise Warmup Schemas ===

class WarmupEmailSchema(BaseModel):
    """Schema for a warmup email record."""
    id: int
    sender_mailbox_id: int
    receiver_mailbox_id: Optional[int] = None
    subject: Optional[str] = None
    status: str
    tracking_id: Optional[str] = None
    ai_generated: bool = False
    ai_provider: Optional[str] = None
    sent_at: Optional[datetime] = None
    opened_at: Optional[datetime] = None
    replied_at: Optional[datetime] = None
    class Config:
        from_attributes = True


class WarmupEmailDetailSchema(WarmupEmailSchema):
    """Full warmup email detail including body content."""
    body_html: Optional[str] = None
    body_text: Optional[str] = None
    sender_email: Optional[str] = None
    receiver_email: Optional[str] = None


class WarmupEmailListResponse(BaseModel):
    """Paginated warmup email list."""
    items: List[WarmupEmailSchema]
    total: int = 0
    page: int = 1
    limit: int = 50


class WarmupDailyLogSchema(BaseModel):
    """Schema for a daily log entry."""
    id: int
    mailbox_id: int
    log_date: date
    emails_sent: int = 0
    emails_received: int = 0
    opens: int = 0
    replies: int = 0
    bounces: int = 0
    health_score: float = 0.0
    warmup_day: int = 0
    phase: int = 0
    daily_limit: int = 0
    bounce_rate: float = 0.0
    reply_rate: float = 0.0
    class Config:
        from_attributes = True


class WarmupAnalyticsResponse(BaseModel):
    """Time-series analytics data."""
    mailbox_id: Optional[int] = None
    days: int = 30
    daily_logs: List[WarmupDailyLogSchema] = []
    summary: Dict[str, Any] = {}


class WarmupAlertSchema(BaseModel):
    """Schema for a warmup alert."""
    id: int
    mailbox_id: Optional[int] = None
    alert_type: str
    severity: str
    title: str
    message: Optional[str] = None
    details_json: Optional[str] = None
    is_read: bool = False
    created_at: Optional[datetime] = None
    class Config:
        from_attributes = True


class WarmupAlertListResponse(BaseModel):
    """Alert list response."""
    items: List[WarmupAlertSchema]
    total: int = 0
    unread_count: int = 0


class WarmupProfileSchema(BaseModel):
    """Schema for a warmup profile."""
    id: int
    name: str
    description: Optional[str] = None
    is_default: bool = False
    is_system: bool = False
    config_json: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    class Config:
        from_attributes = True


class WarmupProfileCreate(BaseModel):
    """Create a custom warmup profile."""
    name: str
    description: Optional[str] = None
    config_json: str


class WarmupProfileUpdate(BaseModel):
    """Update a warmup profile."""
    name: Optional[str] = None
    description: Optional[str] = None
    config_json: Optional[str] = None
    is_default: Optional[bool] = None


class WarmupProfileListResponse(BaseModel):
    """Profile list response."""
    items: List[WarmupProfileSchema]
    total: int = 0


class DNSCheckResultSchema(BaseModel):
    """Schema for DNS check result."""
    id: int
    mailbox_id: int
    domain: str
    checked_at: Optional[datetime] = None
    spf_record: Optional[str] = None
    spf_valid: bool = False
    dkim_selector: Optional[str] = None
    dkim_valid: bool = False
    dmarc_record: Optional[str] = None
    dmarc_valid: bool = False
    dmarc_policy: Optional[str] = None
    mx_records_json: Optional[str] = None
    overall_score: int = 0
    class Config:
        from_attributes = True


class DNSHealthResponse(BaseModel):
    """DNS health check response."""
    mailbox_id: int
    domain: str
    results: Optional[DNSCheckResultSchema] = None
    score: int = 0


class BlacklistCheckResultSchema(BaseModel):
    """Schema for blacklist check result."""
    id: int
    mailbox_id: int
    domain: str
    ip_address: Optional[str] = None
    checked_at: Optional[datetime] = None
    results_json: Optional[str] = None
    total_checked: int = 0
    total_listed: int = 0
    is_clean: bool = True
    class Config:
        from_attributes = True


class BlacklistCheckResponse(BaseModel):
    """Blacklist check response."""
    mailbox_id: int
    domain: str
    results: Optional[BlacklistCheckResultSchema] = None
    is_clean: bool = True


class WarmupDashboardStats(BaseModel):
    """Dashboard aggregate statistics."""
    total_warming: int = 0
    total_cold_ready: int = 0
    total_active: int = 0
    total_paused: int = 0
    total_recovering: int = 0
    avg_health_score: float = 0.0
    dns_issues: int = 0
    blacklisted: int = 0
    total_warmup_emails_sent: int = 0
    total_warmup_emails_received: int = 0


class SmartScheduleConfig(BaseModel):
    """Smart scheduling configuration."""
    send_window_start: str = "09:00"
    send_window_end: str = "17:00"
    timezone: str = "US/Eastern"
    skip_weekends: bool = True
    min_gap_minutes: int = 15
    max_gap_minutes: int = 60
    send_speed: str = "normal"


class InboxPlacementResult(BaseModel):
    """Inbox placement test result."""
    mailbox_id: int
    seed_email: str
    provider: str
    placement: str = "unknown"
    tested_at: Optional[datetime] = None


class WarmupReportExport(BaseModel):
    """Report export parameters."""
    format: str = "csv"
    mailbox_ids: Optional[List[int]] = None
    days: int = 30


class PeerWarmupConfig(BaseModel):
    """Peer warmup configuration."""
    enabled: bool = True
    reply_rate: int = 30
    min_delay_minutes: int = 5
    max_delay_minutes: int = 30
    max_emails_per_pair: int = 3

