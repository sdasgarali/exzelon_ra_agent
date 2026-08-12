"""Unit tests for the derived lead Mailing-Status label."""
from datetime import datetime

import pytest

from app.api.endpoints.leads import mailing_status_label

pytestmark = pytest.mark.unit


class TestMailingStatusLabel:
    """mailing_status_label(campaign_status, downloaded_at) mapping."""

    def test_campaign_active(self):
        assert mailing_status_label("active", None) == "Campaign-Active"

    def test_campaign_paused(self):
        assert mailing_status_label("paused", None) == "Campaign-Paused"

    def test_campaign_draft(self):
        assert mailing_status_label("draft", None) == "Campaign-Draft"

    def test_campaign_completed_maps_to_closed(self):
        assert mailing_status_label("completed", None) == "Campaign-Closed"

    def test_campaign_status_wins_over_download(self):
        """An enrolled lead reflects the campaign even if also downloaded."""
        assert mailing_status_label("active", datetime.utcnow()) == "Campaign-Active"

    def test_downloaded_but_no_campaign_is_mailed_offline(self):
        assert mailing_status_label(None, datetime.utcnow()) == "Mailed-Offline"

    def test_no_campaign_no_download_is_not_mailed(self):
        assert mailing_status_label(None, None) == "Not-Mailed"

    def test_unknown_campaign_status_falls_through_to_download(self):
        """A status outside the known set is treated as un-enrolled."""
        assert mailing_status_label("archived", datetime.utcnow()) == "Mailed-Offline"
        assert mailing_status_label("archived", None) == "Not-Mailed"
