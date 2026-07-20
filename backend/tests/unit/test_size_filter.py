"""Unit tests for the numeric company-size filter helpers."""
import pytest

from app.db.query_helpers import (
    SIZE_OPERATORS, NUMERIC_OPERATORS, effective_size_expr, size_operator_clause,
    effective_salary_bounds, salary_operator_clause,
)
from app.db.models.client import ClientInfo
from app.db.models.lead import LeadDetails

pytestmark = pytest.mark.unit


def test_supported_operators():
    assert SIZE_OPERATORS == {"eq", "ne", "lt", "lte", "gt", "gte", "between"}


def test_invalid_operator_or_values_return_none():
    expr = effective_size_expr(ClientInfo.company_size, ClientInfo.employee_count)
    assert size_operator_clause(expr, "bogus", 5) is None
    assert size_operator_clause(expr, None, 5) is None
    assert size_operator_clause(expr, "eq", None) is None
    # between requires an upper bound
    assert size_operator_clause(expr, "between", 5, None) is None


def test_valid_operators_return_a_clause():
    expr = effective_size_expr(LeadDetails.company_size)
    for op in ("eq", "ne", "lt", "lte", "gt", "gte"):
        assert size_operator_clause(expr, op, 10) is not None
    assert size_operator_clause(expr, "between", 5, 10) is not None


def test_effective_size_expr_accepts_optional_employee_count():
    # Both forms build without error (lead has no employee_count column).
    assert effective_size_expr(LeadDetails.company_size) is not None
    assert effective_size_expr(ClientInfo.company_size, ClientInfo.employee_count) is not None


def test_salary_operators_alias_matches():
    assert NUMERIC_OPERATORS == SIZE_OPERATORS


def test_salary_operator_clause_validation():
    lo, hi = effective_salary_bounds(LeadDetails.salary_min, LeadDetails.salary_max)
    assert salary_operator_clause(lo, hi, "bogus", 5) is None
    assert salary_operator_clause(lo, hi, "gt", None) is None
    assert salary_operator_clause(lo, hi, "between", 5, None) is None


def test_salary_operator_clause_valid():
    lo, hi = effective_salary_bounds(LeadDetails.salary_min, LeadDetails.salary_max)
    for op in ("eq", "ne", "lt", "lte", "gt", "gte"):
        assert salary_operator_clause(lo, hi, op, 50000) is not None
    assert salary_operator_clause(lo, hi, "between", 40000, 90000) is not None
