"""Unit tests for lead status state machine."""
import pytest
from app.db.models.lead import LeadStatus
from app.core.state_machine import validate_transition, get_allowed_transitions

pytestmark = pytest.mark.unit


class TestValidateTransition:
    """Test status transition validation."""

    def test_same_status_always_valid(self):
        for s in LeadStatus:
            assert validate_transition(s, s) is True

    def test_new_to_open(self):
        assert validate_transition(LeadStatus.NEW, LeadStatus.OPEN) is True

    def test_new_to_enriched(self):
        assert validate_transition(LeadStatus.NEW, LeadStatus.ENRICHED) is True

    def test_new_to_skipped(self):
        assert validate_transition(LeadStatus.NEW, LeadStatus.SKIPPED) is True

    def test_new_to_sent_invalid(self):
        assert validate_transition(LeadStatus.NEW, LeadStatus.SENT) is False

    def test_new_to_hunting_invalid(self):
        assert validate_transition(LeadStatus.NEW, LeadStatus.HUNTING) is False

    def test_open_to_hunting(self):
        assert validate_transition(LeadStatus.OPEN, LeadStatus.HUNTING) is True

    def test_open_to_closed_hired(self):
        assert validate_transition(LeadStatus.OPEN, LeadStatus.CLOSED_HIRED) is True

    def test_enriched_to_validated(self):
        assert validate_transition(LeadStatus.ENRICHED, LeadStatus.VALIDATED) is True

    def test_validated_to_sent(self):
        assert validate_transition(LeadStatus.VALIDATED, LeadStatus.SENT) is True

    def test_sent_to_closed_hired(self):
        assert validate_transition(LeadStatus.SENT, LeadStatus.CLOSED_HIRED) is True

    def test_closed_hired_to_open(self):
        """Closed leads can be reopened."""
        assert validate_transition(LeadStatus.CLOSED_HIRED, LeadStatus.OPEN) is True

    def test_closed_hired_to_new_invalid(self):
        assert validate_transition(LeadStatus.CLOSED_HIRED, LeadStatus.NEW) is False

    def test_skipped_to_open(self):
        """Skipped leads can be reopened."""
        assert validate_transition(LeadStatus.SKIPPED, LeadStatus.OPEN) is True

    def test_skipped_to_sent_invalid(self):
        assert validate_transition(LeadStatus.SKIPPED, LeadStatus.SENT) is False

    def test_closed_test_to_open(self):
        assert validate_transition(LeadStatus.CLOSED_TEST, LeadStatus.OPEN) is True


class TestGetAllowedTransitions:
    """Test getting allowed transitions."""

    def test_new_transitions(self):
        allowed = get_allowed_transitions(LeadStatus.NEW)
        assert "open" in allowed
        assert "enriched" in allowed
        assert "skipped" in allowed
        assert "sent" not in allowed

    def test_open_transitions(self):
        allowed = get_allowed_transitions(LeadStatus.OPEN)
        assert "hunting" in allowed
        assert "closed_hired" in allowed
        assert "new" not in allowed

    def test_returns_sorted_list(self):
        allowed = get_allowed_transitions(LeadStatus.NEW)
        assert allowed == sorted(allowed)
