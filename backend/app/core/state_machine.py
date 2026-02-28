"""Lead status state machine — defines allowed transitions."""
from app.db.models.lead import LeadStatus

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
