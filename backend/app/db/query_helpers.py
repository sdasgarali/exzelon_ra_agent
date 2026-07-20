"""Database query helper utilities."""
from typing import Optional
from sqlalchemy import Integer, cast, func
from sqlalchemy.orm import Session, Query


# Supported numeric comparison operators for company-size filtering.
SIZE_OPERATORS = {"eq", "ne", "lt", "lte", "gt", "gte", "between"}


def effective_size_expr(size_col, emp_col=None):
    """SQL expression for a company's effective numeric employee count.

    Company size is stored two ways: an authoritative integer ``employee_count``
    (only on ClientInfo, sparsely populated) and a free-form ``company_size``
    string band that may be an exact number ("120"), a range ("51-200"), a
    label ("5000+"), or blank. Numeric operators need a single number, so we
    prefer ``employee_count`` and fall back to parsing the band:

        COALESCE(employee_count, NULLIF(CAST(NULLIF(company_size,'') AS INT), 0))

    CAST parses the leading integer, so a range "51-200" resolves to its lower
    bound (51) and non-numeric / blank values resolve to NULL (unknown). This
    renders portably on MySQL (CAST ... AS SIGNED INTEGER) and SQLite.

    Args:
        size_col: the ``company_size`` string column.
        emp_col: optional authoritative integer ``employee_count`` column.

    Returns:
        A SQLAlchemy expression yielding an integer or NULL (unknown).
    """
    parsed = func.nullif(cast(func.nullif(size_col, ""), Integer), 0)
    if emp_col is not None:
        return func.coalesce(emp_col, parsed)
    return parsed


def size_operator_clause(expr, op: Optional[str], v1, v2=None):
    """Build a boolean clause applying a numeric operator to a size expression.

    Unknown (NULL) rows never satisfy any comparison — callers add them back
    explicitly via an ``expr IS NULL`` OR-clause when "include unknown" is set.

    Args:
        expr: the size expression (see :func:`effective_size_expr`).
        op: one of :data:`SIZE_OPERATORS`.
        v1: primary comparison value (required).
        v2: upper bound, required only for ``between``.

    Returns:
        A SQLAlchemy clause, or None if the operator/values are invalid.
    """
    if op not in SIZE_OPERATORS or v1 is None:
        return None
    if op == "eq":
        return expr == v1
    if op == "ne":
        # Exclude unknowns from "not equal": NULL != v is NULL (not True).
        return expr.isnot(None) & (expr != v1)
    if op == "lt":
        return expr < v1
    if op == "lte":
        return expr <= v1
    if op == "gt":
        return expr > v1
    if op == "gte":
        return expr >= v1
    if op == "between":
        if v2 is None:
            return None
        lo, hi = (v1, v2) if v1 <= v2 else (v2, v1)
        return expr.between(lo, hi)
    return None


def tenant_filter(query: Query, model, tenant_id: Optional[int]) -> Query:
    """Apply tenant filtering to a query.

    Args:
        query: SQLAlchemy query to filter
        model: SQLAlchemy model class (must have tenant_id column)
        tenant_id: Tenant ID to filter by. None = super admin (no filter).

    Returns:
        Filtered query object
    """
    if tenant_id is not None:
        query = query.filter(model.tenant_id == tenant_id)
    return query


def active_query(db: Session, model, show_archived: bool = False) -> Query:
    """Create a query filtered by archive status.

    Args:
        db: Database session
        model: SQLAlchemy model class (must have is_archived column)
        show_archived: If True, show only archived records.
                       If False, show only non-archived records.

    Returns:
        Filtered query object
    """
    query = db.query(model)
    if show_archived:
        query = query.filter(model.is_archived == True)
    else:
        query = query.filter(model.is_archived == False)
    return query


def paginate(query: Query, page: int = 1, page_size: int = 50) -> dict:
    """Apply pagination to a query and return results with metadata.

    Args:
        query: SQLAlchemy query to paginate
        page: Page number (1-indexed)
        page_size: Number of items per page

    Returns:
        Dict with items, total, page, page_size, pages
    """
    total = query.count()
    offset = (page - 1) * page_size
    items = query.offset(offset).limit(page_size).all()
    pages = (total + page_size - 1) // page_size

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": pages,
    }
