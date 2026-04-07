"""Tests for campaign status state machine."""
import pytest
from app.core.state_machine import (
    validate_campaign_transition,
    get_allowed_campaign_transitions,
    CAMPAIGN_STATUS_TRANSITIONS,
)
from app.db.models.campaign import CampaignStatus

pytestmark = pytest.mark.unit


class TestCampaignTransitions:
    """Test campaign status transition validation."""

    def test_draft_to_active(self):
        assert validate_campaign_transition(CampaignStatus.DRAFT, CampaignStatus.ACTIVE)

    def test_draft_to_archived(self):
        assert validate_campaign_transition(CampaignStatus.DRAFT, CampaignStatus.ARCHIVED)

    def test_draft_to_paused_invalid(self):
        assert not validate_campaign_transition(CampaignStatus.DRAFT, CampaignStatus.PAUSED)

    def test_draft_to_completed_invalid(self):
        assert not validate_campaign_transition(CampaignStatus.DRAFT, CampaignStatus.COMPLETED)

    def test_active_to_paused(self):
        assert validate_campaign_transition(CampaignStatus.ACTIVE, CampaignStatus.PAUSED)

    def test_active_to_completed(self):
        assert validate_campaign_transition(CampaignStatus.ACTIVE, CampaignStatus.COMPLETED)

    def test_active_to_archived(self):
        assert validate_campaign_transition(CampaignStatus.ACTIVE, CampaignStatus.ARCHIVED)

    def test_active_to_draft_invalid(self):
        assert not validate_campaign_transition(CampaignStatus.ACTIVE, CampaignStatus.DRAFT)

    def test_paused_to_active(self):
        assert validate_campaign_transition(CampaignStatus.PAUSED, CampaignStatus.ACTIVE)

    def test_paused_to_archived(self):
        assert validate_campaign_transition(CampaignStatus.PAUSED, CampaignStatus.ARCHIVED)

    def test_paused_to_completed(self):
        assert validate_campaign_transition(CampaignStatus.PAUSED, CampaignStatus.COMPLETED)

    def test_completed_to_archived(self):
        assert validate_campaign_transition(CampaignStatus.COMPLETED, CampaignStatus.ARCHIVED)

    def test_completed_to_active_invalid(self):
        assert not validate_campaign_transition(CampaignStatus.COMPLETED, CampaignStatus.ACTIVE)

    def test_completed_to_paused_invalid(self):
        assert not validate_campaign_transition(CampaignStatus.COMPLETED, CampaignStatus.PAUSED)

    def test_archived_is_terminal(self):
        """Archived is terminal — no transitions out."""
        assert not validate_campaign_transition(CampaignStatus.ARCHIVED, CampaignStatus.ACTIVE)
        assert not validate_campaign_transition(CampaignStatus.ARCHIVED, CampaignStatus.DRAFT)
        assert not validate_campaign_transition(CampaignStatus.ARCHIVED, CampaignStatus.PAUSED)

    def test_same_status_always_ok(self):
        """No-op transitions are always allowed."""
        for status in CampaignStatus:
            assert validate_campaign_transition(status, status)

    def test_get_allowed_from_draft(self):
        allowed = get_allowed_campaign_transitions(CampaignStatus.DRAFT)
        assert "active" in allowed
        assert "archived" in allowed
        assert "paused" not in allowed

    def test_get_allowed_from_archived(self):
        allowed = get_allowed_campaign_transitions(CampaignStatus.ARCHIVED)
        assert allowed == []

    def test_all_statuses_covered(self):
        """Every CampaignStatus should have an entry in the transition table."""
        for status in CampaignStatus:
            assert status in CAMPAIGN_STATUS_TRANSITIONS
