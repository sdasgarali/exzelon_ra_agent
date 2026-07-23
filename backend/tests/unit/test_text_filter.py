"""Unit tests for the Excel-style text-filter → SQL predicate helper."""
import re

import pytest
from sqlalchemy import Column, Integer, String, create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

from app.utils.text_filter import text_filter_condition

pytestmark = pytest.mark.unit

Base = declarative_base()


class Row(Base):
    __tablename__ = "rows"
    id = Column(Integer, primary_key=True)
    name = Column(String)


@pytest.fixture()
def session():
    engine = create_engine("sqlite://")

    # SQLite has no native REGEXP (MySQL does) — register a shim for the word op.
    @event.listens_for(engine, "connect")
    def _regexp(dbapi_conn, _rec):
        dbapi_conn.create_function(
            "regexp", 2,
            lambda pattern, value: value is not None and re.search(pattern, value) is not None,
        )

    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    s.add_all([
        Row(id=1, name="Dental Insurance"),
        Row(id=2, name="Auto Insurance"),
        Row(id=3, name="ComEd (Electricity)"),
        Row(id=4, name="Health Insurance"),
        Row(id=5, name=None),
    ])
    s.commit()
    yield s
    s.close()


def _names(session, clause):
    return sorted(r.name or "∅" for r in session.query(Row).filter(clause).all())


def test_none_when_empty():
    assert text_filter_condition(Row.name, None, None) is None
    assert text_filter_condition(Row.name, "contains", "") is None
    assert text_filter_condition(Row.name, "contains", "   ") is None
    assert text_filter_condition(Row.name, "bogus_op", "x") is None


def test_contains_case_insensitive(session):
    assert _names(session, text_filter_condition(Row.name, "contains", "insurance")) == [
        "Auto Insurance", "Dental Insurance", "Health Insurance"]


def test_equals_and_not_equals(session):
    assert _names(session, text_filter_condition(Row.name, "equals", "auto insurance")) == ["Auto Insurance"]
    # not_equals is NULL-safe (the NULL row is included)
    assert _names(session, text_filter_condition(Row.name, "not_equals", "Auto Insurance")) == [
        "ComEd (Electricity)", "Dental Insurance", "Health Insurance", "∅"]


def test_begins_and_ends(session):
    assert _names(session, text_filter_condition(Row.name, "begins", "Dental")) == ["Dental Insurance"]
    assert _names(session, text_filter_condition(Row.name, "ends", "Insurance")) == [
        "Auto Insurance", "Dental Insurance", "Health Insurance"]


def test_not_begins_and_not_ends_are_null_safe(session):
    # not_begins "Dental" → everything except the one starting with "Dental" (incl. NULL)
    assert _names(session, text_filter_condition(Row.name, "not_begins", "Dental")) == [
        "Auto Insurance", "ComEd (Electricity)", "Health Insurance", "∅"]
    # not_ends "Insurance" → only the non-Insurance rows (incl. NULL)
    assert _names(session, text_filter_condition(Row.name, "not_ends", "Insurance")) == [
        "ComEd (Electricity)", "∅"]


def test_not_contains_is_null_safe(session):
    assert _names(session, text_filter_condition(Row.name, "not_contains", "Insurance")) == [
        "ComEd (Electricity)", "∅"]


def test_like_metacharacters_are_literal(session):
    session.add(Row(id=6, name="50% off"))
    session.commit()
    # '%' must match literally, not as a wildcard
    assert _names(session, text_filter_condition(Row.name, "contains", "50%")) == ["50% off"]


def test_word_matches_standalone_token_not_substring(session):
    session.add_all([
        Row(id=10, name="IT"),
        Row(id=11, name="IT Services"),
        Row(id=12, name="Global IT Support"),
        Row(id=13, name="Litigation"),      # contains "it" but not as a word
        Row(id=14, name="Digital Security"),  # substring "it" inside words
    ])
    session.commit()
    # Whole-word "IT" matches the standalone tokens only, not Litigation / Digital.
    assert _names(session, text_filter_condition(Row.name, "word", "IT")) == [
        "Global IT Support", "IT", "IT Services"]


def test_word_is_case_insensitive(session):
    session.add(Row(id=20, name="Enterprise it services"))
    session.commit()
    assert "Enterprise it services" in _names(session, text_filter_condition(Row.name, "word", "IT"))


def test_word_escapes_regex_metacharacters(session):
    session.add_all([Row(id=30, name="R&D Lead"), Row(id=31, name="RxD")])
    session.commit()
    # "R&D" must be treated literally, not as a regex.
    assert _names(session, text_filter_condition(Row.name, "word", "R&D")) == ["R&D Lead"]


def test_custom_filter_and_or(session):
    # OR: begins "Dental" OR begins "Auto"
    c_or = text_filter_condition(Row.name, "begins", "Dental", "begins", "Auto", "or")
    assert _names(session, c_or) == ["Auto Insurance", "Dental Insurance"]
    # AND: contains "Insurance" AND not_contains "Auto"
    c_and = text_filter_condition(Row.name, "contains", "Insurance", "not_contains", "Auto", "and")
    assert _names(session, c_and) == ["Dental Insurance", "Health Insurance"]


def test_partial_custom_filter_uses_the_valid_part(session):
    # second condition empty → behaves as a single condition
    c = text_filter_condition(Row.name, "contains", "Insurance", "contains", "", "and")
    assert _names(session, c) == ["Auto Insurance", "Dental Insurance", "Health Insurance"]
