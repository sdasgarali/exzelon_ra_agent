"""Excel-style text filter → SQLAlchemy predicate.

Powers the "Text Filters" operator menu (Equals / Does Not Equal / Begins With /
Ends With / Contains / Does Not Contain / Custom Filter) on the leads, clients,
contacts and campaign filters. The frontend sends ``<field>_op`` + ``<field>_val``
(and optionally ``<field>_op2`` / ``<field>_val2`` / ``<field>_conj`` for a Custom
Filter with two conditions). This module turns those into a SQL clause so the
filter works even when the typed text is not one of the known checklist values.

All matching is case-insensitive (``ilike``) and LIKE metacharacters in the user's
input are escaped so ``%`` / ``_`` are treated literally.
"""
from typing import Optional

from sqlalchemy import and_, or_, func

# Operator tokens shared with the frontend.
TEXT_FILTER_OPS = {"equals", "not_equals", "begins", "ends", "contains", "not_contains"}


def _escape_like(value: str) -> str:
    """Escape LIKE metacharacters so user input matches literally (\\ is the escape char)."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _one_condition(column, op: Optional[str], value: Optional[str]):
    """Build a single SQLAlchemy clause for one (op, value), or None if not applicable.

    NULL-safe: the negative operators (not_equals / not_contains) also match rows
    where the column is NULL, which is what a user expects from "does not contain X".
    """
    if not op or value is None:
        return None
    v = value.strip()
    if v == "" or op not in TEXT_FILTER_OPS:
        return None
    like = _escape_like(v)
    esc = {"escape": "\\"}
    if op == "equals":
        # Case-insensitive exact match (no wildcards).
        return func.lower(column) == v.lower()
    if op == "not_equals":
        return or_(column.is_(None), func.lower(column) != v.lower())
    if op == "begins":
        return column.ilike(f"{like}%", **esc)
    if op == "ends":
        return column.ilike(f"%{like}", **esc)
    if op == "contains":
        return column.ilike(f"%{like}%", **esc)
    if op == "not_contains":
        return or_(column.is_(None), ~column.ilike(f"%{like}%", **esc))
    return None


def text_filter_condition(
    column,
    op: Optional[str],
    val: Optional[str],
    op2: Optional[str] = None,
    val2: Optional[str] = None,
    conj: Optional[str] = "and",
):
    """Return a SQLAlchemy clause for a text filter on ``column``, or None if empty.

    Supports a single condition, or two conditions (Custom Filter) combined with
    ``conj`` = "and" | "or". Unusable parts are ignored, so a partially-filled
    Custom Filter still works.
    """
    c1 = _one_condition(column, op, val)
    c2 = _one_condition(column, op2, val2)
    conds = [c for c in (c1, c2) if c is not None]
    if not conds:
        return None
    if len(conds) == 1:
        return conds[0]
    return or_(*conds) if (conj or "and").lower() == "or" else and_(*conds)


def text_filter_from_params(params, field: str, column):
    """Read ``<field>_op`` / ``_val`` (+ ``_op2`` / ``_val2`` / ``_conj``) from a
    query-params mapping (e.g. ``request.query_params``) and build the clause.

    Returns None when no usable condition is present. Keeps endpoint signatures
    clean — no need to declare five Query params per filterable field.
    """
    return text_filter_condition(
        column,
        params.get(f"{field}_op"), params.get(f"{field}_val"),
        params.get(f"{field}_op2"), params.get(f"{field}_val2"),
        params.get(f"{field}_conj", "and"),
    )
