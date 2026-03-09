"""Unit tests for deal pipeline automation service."""
import pytest
from datetime import datetime, timedelta

from app.db.models.deal import Deal, DealStage, DealActivity
from app.db.models.contact import ContactDetails
from app.db.models.client import ClientInfo
from app.db.models.settings import Settings
from app.services.deal_automation import (
    _get_deal_setting,
    _score_to_probability,
    _build_activity_description,
    auto_create_deal_from_interested_reply,
    auto_log_email_activity,
    auto_advance_stage,
    update_deal_probability_from_score,
    detect_stale_deals,
    calculate_pipeline_forecast,
)


# ─── Fixtures ─────────────────────────────────────────────────────


def _seed_stages(db):
    """Seed the 7 default deal stages."""
    stages = [
        DealStage(name="New Lead", stage_order=1, color="#3b82f6"),
        DealStage(name="Contacted", stage_order=2, color="#8b5cf6"),
        DealStage(name="Qualified", stage_order=3, color="#06b6d4"),
        DealStage(name="Proposal", stage_order=4, color="#f59e0b"),
        DealStage(name="Negotiation", stage_order=5, color="#ef4444"),
        DealStage(name="Won", stage_order=6, color="#22c55e", is_won=True),
        DealStage(name="Lost", stage_order=7, color="#6b7280", is_lost=True),
    ]
    for s in stages:
        db.add(s)
    db.flush()
    return {s.name: s for s in stages}


def _create_contact(db, first_name="Jane", last_name="Doe", email="jane@example.com",
                     client_name="Acme Inc", lead_score=None):
    """Create a test contact."""
    c = ContactDetails(
        first_name=first_name,
        last_name=last_name,
        email=email,
        client_name=client_name,
    )
    if lead_score is not None:
        c.lead_score = lead_score
    db.add(c)
    db.flush()
    return c


def _create_client(db, name="Acme Inc"):
    """Create a test client."""
    cl = ClientInfo(client_name=name)
    db.add(cl)
    db.flush()
    return cl


def _set_setting(db, key, value):
    """Set a setting."""
    existing = db.query(Settings).filter(Settings.key == key).first()
    if existing:
        existing.value_json = str(value)
    else:
        db.add(Settings(key=key, value_json=str(value)))
    db.flush()


# ─── _get_deal_setting ────────────────────────────────────────────


@pytest.mark.unit
class TestGetDealSetting:
    def test_returns_default_when_not_found(self, db_session):
        result = _get_deal_setting(db_session, "nonexistent_key", "fallback")
        assert result == "fallback"

    def test_returns_true_for_truthy_strings(self, db_session):
        for val in ("true", "True", "1", "yes"):
            _set_setting(db_session, "test_bool", val)
            assert _get_deal_setting(db_session, "test_bool") is True

    def test_returns_false_for_falsy_strings(self, db_session):
        for val in ("false", "False", "0", "no"):
            _set_setting(db_session, "test_bool", val)
            assert _get_deal_setting(db_session, "test_bool") is False

    def test_returns_int_for_numeric_strings(self, db_session):
        _set_setting(db_session, "test_int", "42")
        assert _get_deal_setting(db_session, "test_int") == 42

    def test_returns_string_for_non_numeric(self, db_session):
        _set_setting(db_session, "test_str", "hello")
        assert _get_deal_setting(db_session, "test_str") == "hello"


# ─── _score_to_probability ────────────────────────────────────────


@pytest.mark.unit
class TestScoreToProbability:
    @pytest.mark.parametrize("score,expected", [
        (0, 10), (5, 10), (20, 10),
        (21, 20), (40, 20),
        (41, 40), (60, 40),
        (61, 60), (80, 60),
        (81, 80), (100, 80),
    ])
    def test_score_mapping(self, score, expected):
        assert _score_to_probability(score) == expected


# ─── _build_activity_description ──────────────────────────────────


@pytest.mark.unit
class TestBuildActivityDescription:
    def test_email_sent_with_subject(self):
        desc = _build_activity_description("email_sent", {"subject": "Hello"})
        assert 'Email sent: "Hello"' == desc

    def test_email_sent_no_details(self):
        assert _build_activity_description("email_sent") == "Email sent"

    def test_reply_received(self):
        desc = _build_activity_description("email_received", {"subject": "Re: Hi"})
        assert "Reply received" in desc

    def test_unknown_type(self):
        desc = _build_activity_description("custom_event")
        assert "Activity: custom_event" == desc


# ─── auto_create_deal_from_interested_reply ───────────────────────


@pytest.mark.unit
class TestAutoCreateDeal:
    def test_creates_deal_for_new_contact(self, db_session):
        stages = _seed_stages(db_session)
        client = _create_client(db_session, "Acme Inc")
        contact = _create_contact(db_session, client_name="Acme Inc")
        db_session.commit()

        result = auto_create_deal_from_interested_reply(contact.contact_id, db_session)

        assert result is not None
        assert result["action"] == "created"
        assert "Jane Doe" in result["name"]

        deal = db_session.query(Deal).filter(Deal.contact_id == contact.contact_id).first()
        assert deal is not None
        assert deal.is_auto_created is True
        assert deal.stage_id == stages["New Lead"].stage_id
        assert deal.client_id == client.client_id

    def test_skips_if_deal_exists(self, db_session):
        stages = _seed_stages(db_session)
        contact = _create_contact(db_session)
        deal = Deal(name="Existing", stage_id=stages["New Lead"].stage_id,
                    contact_id=contact.contact_id, value=0, probability=20)
        db_session.add(deal)
        db_session.commit()

        result = auto_create_deal_from_interested_reply(contact.contact_id, db_session)
        assert result["action"] == "existing"

    def test_returns_none_when_disabled(self, db_session):
        _seed_stages(db_session)
        contact = _create_contact(db_session)
        _set_setting(db_session, "deal_auto_create_on_interested", "false")
        db_session.commit()

        result = auto_create_deal_from_interested_reply(contact.contact_id, db_session)
        assert result is None

    def test_returns_none_for_missing_contact(self, db_session):
        _seed_stages(db_session)
        db_session.commit()
        result = auto_create_deal_from_interested_reply(99999, db_session)
        assert result is None

    def test_returns_none_when_no_new_lead_stage(self, db_session):
        # Don't seed any stages
        contact = _create_contact(db_session)
        db_session.commit()
        result = auto_create_deal_from_interested_reply(contact.contact_id, db_session)
        assert result is None


# ─── auto_log_email_activity ──────────────────────────────────────


@pytest.mark.unit
class TestAutoLogEmailActivity:
    def test_logs_activity_on_open_deal(self, db_session):
        stages = _seed_stages(db_session)
        contact = _create_contact(db_session)
        deal = Deal(name="Test Deal", stage_id=stages["Contacted"].stage_id,
                    contact_id=contact.contact_id, value=0, probability=20)
        db_session.add(deal)
        db_session.commit()

        count = auto_log_email_activity(contact.contact_id, "email_sent", db_session,
                                         {"subject": "Hi there"})
        assert count == 1
        db_session.flush()

        activity = db_session.query(DealActivity).filter(
            DealActivity.deal_id == deal.deal_id
        ).first()
        assert activity is not None
        assert activity.activity_type == "email_sent"
        assert "Hi there" in activity.description

    def test_skips_won_lost_deals(self, db_session):
        stages = _seed_stages(db_session)
        contact = _create_contact(db_session)
        deal = Deal(name="Won Deal", stage_id=stages["Won"].stage_id,
                    contact_id=contact.contact_id, value=0, probability=100)
        db_session.add(deal)
        db_session.commit()

        count = auto_log_email_activity(contact.contact_id, "email_sent", db_session)
        assert count == 0

    def test_returns_zero_when_no_deals(self, db_session):
        _seed_stages(db_session)
        contact = _create_contact(db_session)
        db_session.commit()

        count = auto_log_email_activity(contact.contact_id, "email_sent", db_session)
        assert count == 0

    def test_disabled_by_setting(self, db_session):
        stages = _seed_stages(db_session)
        contact = _create_contact(db_session)
        deal = Deal(name="Test", stage_id=stages["Contacted"].stage_id,
                    contact_id=contact.contact_id, value=0, probability=20)
        db_session.add(deal)
        _set_setting(db_session, "deal_auto_log_activities", "false")
        db_session.commit()

        count = auto_log_email_activity(contact.contact_id, "email_sent", db_session)
        assert count == 0


# ─── auto_advance_stage ──────────────────────────────────────────


@pytest.mark.unit
class TestAutoAdvanceStage:
    def test_advance_new_lead_to_contacted_on_email_sent(self, db_session):
        stages = _seed_stages(db_session)
        contact = _create_contact(db_session)
        deal = Deal(name="Test", stage_id=stages["New Lead"].stage_id,
                    contact_id=contact.contact_id, value=0, probability=20)
        db_session.add(deal)
        db_session.commit()

        result = auto_advance_stage(deal.deal_id, "email_sent", db_session)
        assert result is not None
        assert result["from"] == "New Lead"
        assert result["to"] == "Contacted"

    def test_advance_contacted_to_qualified_on_reply(self, db_session):
        stages = _seed_stages(db_session)
        contact = _create_contact(db_session)
        deal = Deal(name="Test", stage_id=stages["Contacted"].stage_id,
                    contact_id=contact.contact_id, value=0, probability=20)
        db_session.add(deal)
        db_session.commit()

        result = auto_advance_stage(deal.deal_id, "reply_received", db_session)
        assert result is not None
        assert result["from"] == "Contacted"
        assert result["to"] == "Qualified"

    def test_no_advance_from_proposal(self, db_session):
        stages = _seed_stages(db_session)
        contact = _create_contact(db_session)
        deal = Deal(name="Test", stage_id=stages["Proposal"].stage_id,
                    contact_id=contact.contact_id, value=0, probability=50)
        db_session.add(deal)
        db_session.commit()

        result = auto_advance_stage(deal.deal_id, "email_sent", db_session)
        assert result is None

    def test_no_advance_won_deal(self, db_session):
        stages = _seed_stages(db_session)
        contact = _create_contact(db_session)
        deal = Deal(name="Test", stage_id=stages["Won"].stage_id,
                    contact_id=contact.contact_id, value=1000, probability=100)
        db_session.add(deal)
        db_session.commit()

        result = auto_advance_stage(deal.deal_id, "reply_received", db_session)
        assert result is None

    def test_disabled_by_setting(self, db_session):
        stages = _seed_stages(db_session)
        contact = _create_contact(db_session)
        deal = Deal(name="Test", stage_id=stages["New Lead"].stage_id,
                    contact_id=contact.contact_id, value=0, probability=20)
        db_session.add(deal)
        _set_setting(db_session, "deal_auto_advance_stages", "false")
        db_session.commit()

        result = auto_advance_stage(deal.deal_id, "email_sent", db_session)
        assert result is None

    def test_nonexistent_deal(self, db_session):
        _seed_stages(db_session)
        db_session.commit()
        result = auto_advance_stage(99999, "email_sent", db_session)
        assert result is None


# ─── update_deal_probability_from_score ───────────────────────────


@pytest.mark.unit
class TestUpdateDealProbability:
    def test_updates_probability(self, db_session):
        stages = _seed_stages(db_session)
        contact = _create_contact(db_session, lead_score=75)
        deal = Deal(name="Test", stage_id=stages["Contacted"].stage_id,
                    contact_id=contact.contact_id, value=0, probability=20,
                    probability_manual=False)
        db_session.add(deal)
        db_session.commit()

        count = update_deal_probability_from_score(contact.contact_id, db_session)
        assert count == 1
        db_session.flush()
        assert deal.probability == 60  # score 75 → 60%

    def test_skips_manual_probability(self, db_session):
        stages = _seed_stages(db_session)
        contact = _create_contact(db_session, lead_score=90)
        deal = Deal(name="Test", stage_id=stages["Contacted"].stage_id,
                    contact_id=contact.contact_id, value=0, probability=50,
                    probability_manual=True)
        db_session.add(deal)
        db_session.commit()

        count = update_deal_probability_from_score(contact.contact_id, db_session)
        assert count == 0
        db_session.refresh(deal)
        assert deal.probability == 50  # unchanged

    def test_returns_zero_when_disabled(self, db_session):
        _set_setting(db_session, "deal_score_to_probability", "false")
        db_session.commit()
        count = update_deal_probability_from_score(1, db_session)
        assert count == 0

    def test_returns_zero_for_missing_contact(self, db_session):
        db_session.commit()
        count = update_deal_probability_from_score(99999, db_session)
        assert count == 0


# ─── detect_stale_deals ──────────────────────────────────────────


@pytest.mark.unit
class TestDetectStaleDeals:
    def test_finds_stale_deals(self, db_session):
        stages = _seed_stages(db_session)
        contact = _create_contact(db_session)

        # Create a deal with old created_at
        deal = Deal(name="Old Deal", stage_id=stages["Contacted"].stage_id,
                    contact_id=contact.contact_id, value=5000, probability=30)
        db_session.add(deal)
        db_session.flush()
        # Backdate
        deal.created_at = datetime.utcnow() - timedelta(days=20)
        db_session.commit()

        stale = detect_stale_deals(db_session, days_threshold=7)
        assert len(stale) == 1
        assert stale[0]["deal_id"] == deal.deal_id
        assert stale[0]["days_idle"] >= 19

    def test_excludes_won_lost(self, db_session):
        stages = _seed_stages(db_session)
        contact = _create_contact(db_session)

        deal = Deal(name="Won Deal", stage_id=stages["Won"].stage_id,
                    contact_id=contact.contact_id, value=5000, probability=100)
        db_session.add(deal)
        db_session.flush()
        deal.created_at = datetime.utcnow() - timedelta(days=20)
        db_session.commit()

        stale = detect_stale_deals(db_session, days_threshold=7)
        assert len(stale) == 0

    def test_fresh_deal_not_stale(self, db_session):
        stages = _seed_stages(db_session)
        contact = _create_contact(db_session)

        deal = Deal(name="Fresh Deal", stage_id=stages["Contacted"].stage_id,
                    contact_id=contact.contact_id, value=1000, probability=30)
        db_session.add(deal)
        db_session.commit()

        stale = detect_stale_deals(db_session, days_threshold=7)
        assert len(stale) == 0


# ─── calculate_pipeline_forecast ──────────────────────────────────


@pytest.mark.unit
class TestCalculatePipelineForecast:
    def test_weighted_value(self, db_session):
        stages = _seed_stages(db_session)
        contact = _create_contact(db_session)

        # Deal: $10,000 at 50% → weighted = $5,000
        db_session.add(Deal(name="A", stage_id=stages["Contacted"].stage_id,
                            contact_id=contact.contact_id, value=10000, probability=50))
        # Deal: $20,000 at 25% → weighted = $5,000
        db_session.add(Deal(name="B", stage_id=stages["Proposal"].stage_id,
                            contact_id=contact.contact_id, value=20000, probability=25))
        db_session.commit()

        forecast = calculate_pipeline_forecast(db_session)
        assert forecast["weighted_value"] == 10000.0
        assert forecast["total_pipeline_value"] == 30000.0
        assert forecast["active_deals"] == 2

    def test_excludes_won_lost(self, db_session):
        stages = _seed_stages(db_session)
        contact = _create_contact(db_session)

        db_session.add(Deal(name="Active", stage_id=stages["Contacted"].stage_id,
                            contact_id=contact.contact_id, value=5000, probability=40))
        db_session.add(Deal(name="Won", stage_id=stages["Won"].stage_id,
                            contact_id=contact.contact_id, value=10000, probability=100))
        db_session.commit()

        forecast = calculate_pipeline_forecast(db_session)
        assert forecast["active_deals"] == 1
        assert forecast["total_pipeline_value"] == 5000.0

    def test_empty_pipeline(self, db_session):
        _seed_stages(db_session)
        db_session.commit()

        forecast = calculate_pipeline_forecast(db_session)
        assert forecast["active_deals"] == 0
        assert forecast["weighted_value"] == 0
        assert forecast["total_pipeline_value"] == 0
