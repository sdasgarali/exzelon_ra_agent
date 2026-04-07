"""Status state machines — defines allowed transitions for leads and campaigns."""
from app.db.models.lead import LeadStatus
from app.db.models.campaign import CampaignStatus

# Allowed transitions: from_status -> set of allowed to_statuses
LEAD_STATUS_TRANSITIONS: dict[LeadStatus, set[LeadStatus]] = {
    LeadStatus.NEW: {
        LeadStatus.OPEN,
        LeadStatus.ENRICHED,
        LeadStatus.SKIPPED,
        LeadStatus.CLOSED_TEST,
    },
    LeadStatus.OPEN: {
        LeadStatus.HUNTING,
        LeadStatus.ENRICHED,
        LeadStatus.SKIPPED,
        LeadStatus.CLOSED_HIRED,
        LeadStatus.CLOSED_NOT_HIRED,
        LeadStatus.CLOSED_TEST,
    },
    LeadStatus.ENRICHED: {
        LeadStatus.OPEN,
        LeadStatus.HUNTING,
        LeadStatus.VALIDATED,
        LeadStatus.SKIPPED,
        LeadStatus.CLOSED_HIRED,
        LeadStatus.CLOSED_NOT_HIRED,
        LeadStatus.CLOSED_TEST,
    },
    LeadStatus.VALIDATED: {
        LeadStatus.HUNTING,
        LeadStatus.SENT,
        LeadStatus.SKIPPED,
        LeadStatus.CLOSED_HIRED,
        LeadStatus.CLOSED_NOT_HIRED,
        LeadStatus.CLOSED_TEST,
    },
    LeadStatus.HUNTING: {
        LeadStatus.SENT,
        LeadStatus.CLOSED_HIRED,
        LeadStatus.CLOSED_NOT_HIRED,
        LeadStatus.CLOSED_TEST,
    },
    LeadStatus.SENT: {
        LeadStatus.HUNTING,
        LeadStatus.CLOSED_HIRED,
        LeadStatus.CLOSED_NOT_HIRED,
        LeadStatus.CLOSED_TEST,
    },
    LeadStatus.SKIPPED: {
        LeadStatus.OPEN,
        LeadStatus.NEW,
        LeadStatus.CLOSED_TEST,
    },
    # Closed statuses can transition to each other or reopen
    LeadStatus.CLOSED_HIRED: {
        LeadStatus.OPEN,
        LeadStatus.CLOSED_NOT_HIRED,
        LeadStatus.CLOSED_TEST,
    },
    LeadStatus.CLOSED_NOT_HIRED: {
        LeadStatus.OPEN,
        LeadStatus.CLOSED_HIRED,
        LeadStatus.CLOSED_TEST,
    },
    LeadStatus.CLOSED_TEST: {
        LeadStatus.OPEN,
        LeadStatus.NEW,
    },
}


def validate_transition(from_status: LeadStatus, to_status: LeadStatus) -> bool:
    """Check if a status transition is allowed."""
    if from_status == to_status:
        return True  # No-op transitions are always OK
    allowed = LEAD_STATUS_TRANSITIONS.get(from_status, set())
    return to_status in allowed


def get_allowed_transitions(from_status: LeadStatus) -> list[str]:
    """Return list of allowed next statuses for a given status."""
    allowed = LEAD_STATUS_TRANSITIONS.get(from_status, set())
    return sorted([s.value for s in allowed])


# ── Campaign Status State Machine ──────────────────────────────────

CAMPAIGN_STATUS_TRANSITIONS: dict[CampaignStatus, set[CampaignStatus]] = {
    CampaignStatus.DRAFT: {
        CampaignStatus.ACTIVE,
        CampaignStatus.ARCHIVED,
    },
    CampaignStatus.ACTIVE: {
        CampaignStatus.PAUSED,
        CampaignStatus.COMPLETED,
        CampaignStatus.ARCHIVED,
    },
    CampaignStatus.PAUSED: {
        CampaignStatus.ACTIVE,
        CampaignStatus.ARCHIVED,
        CampaignStatus.COMPLETED,
    },
    CampaignStatus.COMPLETED: {
        CampaignStatus.ARCHIVED,
    },
    CampaignStatus.ARCHIVED: set(),  # Terminal state — no transitions out
}


def validate_campaign_transition(
    from_status: CampaignStatus, to_status: CampaignStatus
) -> bool:
    """Check if a campaign status transition is allowed."""
    if from_status == to_status:
        return True
    allowed = CAMPAIGN_STATUS_TRANSITIONS.get(from_status, set())
    return to_status in allowed


def get_allowed_campaign_transitions(from_status: CampaignStatus) -> list[str]:
    """Return list of allowed next campaign statuses."""
    allowed = CAMPAIGN_STATUS_TRANSITIONS.get(from_status, set())
    return sorted([s.value for s in allowed])
