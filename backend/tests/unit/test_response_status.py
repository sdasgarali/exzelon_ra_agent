"""Unit tests for the derived lead-level Response label."""
import pytest

from app.api.endpoints.leads import response_status_label

pytestmark = pytest.mark.unit


class TestResponseStatusLabel:
    """response_status_label(best_category, has_reply, has_outreach) mapping."""

    def test_interested(self):
        assert response_status_label("interested", True, True) == "Interested"

    def test_referral(self):
        assert response_status_label("referral", True, True) == "Referral"

    def test_question(self):
        assert response_status_label("question", True, True) == "Question"

    def test_not_interested(self):
        assert response_status_label("not_interested", True, True) == "Not-Interested"

    def test_do_not_contact(self):
        assert response_status_label("do_not_contact", True, True) == "Do-Not-Contact"

    def test_ooo(self):
        assert response_status_label("ooo", True, True) == "OOO"

    def test_other(self):
        assert response_status_label("other", True, True) == "Other"

    def test_replied_when_reply_but_no_usable_category(self):
        """A detected reply with no classifiable category rolls up to Replied."""
        assert response_status_label(None, True, True) == "Replied"

    def test_no_response_when_outreach_but_no_reply(self):
        assert response_status_label(None, False, True) == "No-Response"

    def test_not_contacted_when_no_outreach(self):
        assert response_status_label(None, False, False) == "Not-Contacted"

    def test_unknown_category_falls_through_to_reply_state(self):
        """A category outside the known set is treated as unclassified."""
        assert response_status_label("weird", True, True) == "Replied"
        assert response_status_label("weird", False, True) == "No-Response"

    def test_classified_category_wins_over_reply_flags(self):
        """A usable category always beats the generic fall-through labels."""
        assert response_status_label("interested", False, False) == "Interested"
