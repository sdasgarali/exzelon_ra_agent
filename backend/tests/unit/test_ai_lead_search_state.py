"""State detection in the natural-language lead search parser (services/ai_lead_search.py)."""
import pytest

from app.services.ai_lead_search import parse_natural_query

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("query,expected", [
    # The reported bug: the word "in" was read as Indiana.
    ("hospitals in Texas hiring nurses", "TX"),
    ("hospitals in texas hiring nurses", "TX"),
    ("nurses in TX", "TX"),
    ("nurses in tx", "TX"),
    ("NURSES IN TX", "TX"),
    ("HOSPITALS IN TEXAS", "TX"),
    ("warehouse jobs in Austin, TX", "TX"),
    ("manufacturing in Ohio", "OH"),
    ("plants in Indiana", "IN"),
    ("nurses IN", "IN"),
    ("nurses in IN", "IN"),
    ("clinics in or near Portland, OR", "OR"),
    ("jobs in Pennsylvania or Ohio", "PA"),
    ("clinics in pa", "PA"),
    ("clinics located in me", "ME"),
    ("hiring in West Virginia", "WV"),
    ("plants in Arkansas", "AR"),
    ("leads from Kansas", "KS"),
    ("plants in New York and Ohio", "NY"),
    ("healthcare companies hiring HR managers in CA", "CA"),
])
def test_state_detected(query, expected):
    assert parse_natural_query(query).get("state") == expected


@pytest.mark.parametrize("query", [
    "hospitals hiring nurses",
    "hospitals in the area hiring nurses",
    "companies hiring in or around downtown",  # 'or' is a conjunction here, not Oregon
    "ok show me recent leads",               # 'ok' / 'me' are words, not states
    "hi, find me plant managers",
    "leads in or out of network",
    "oh, find plant managers in the midwest",
])
def test_common_words_are_not_states(query):
    assert "state" not in parse_natural_query(query)


def test_full_name_preferred_over_ambiguous_code():
    # "me" is preceded by nothing location-like; Maine must not win over Texas.
    assert parse_natural_query("show me hospitals in Texas")["state"] == "TX"


def test_city_still_extracted_and_state_not_taken_as_city():
    f = parse_natural_query("warehouse jobs in Austin, TX")
    assert f["state"] == "TX" and f["city"] == "Austin"
    assert "city" not in parse_natural_query("hospitals in Texas hiring nurses")


def test_city_needs_whole_word_in():
    # "Plain" ends in "in" - must not produce city="Dallas"-style false positives from mid-word "in".
    f = parse_natural_query("Main Street Dallas")
    assert "city" not in f


def test_other_filters_unchanged():
    f = parse_natural_query("tech companies in Texas hiring HR managers 80k+")
    assert f["state"] == "TX"
    assert f["salary_min"] == 80000
    assert f["job_title"] == "hr manager"
    assert "Technology" in f["industries"]
