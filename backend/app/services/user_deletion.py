"""Release every row that points at a user, so the user row itself can be deleted.

Nineteen foreign keys reference `users.user_id`, all `NO ACTION`, so a plain
`DELETE FROM users` failed with MySQL 1451 for anyone who had ever logged in
(`login_history`) — which is every real user. The constraints are read from the live
schema, not the models: production carries legacy constraints the models don't
declare, and a missed one is the same 500 again.

What happens to each reference:

* **Personal rows** (the user's own API keys and saved searches) are deleted with them.
  An API key outliving its owner would be a live credential nobody can manage.
* **Nullable** columns (who logged in, who owns a deal, who approved a draft…) are set
  to NULL. The history row survives; the audit log records who was deleted.
* **Required** columns on shared workspace data (e.g. an ICP profile's author) are
  re-pointed at the admin doing the delete, so the workspace keeps its data.
"""
import structlog
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

logger = structlog.get_logger()

#: Rows that belong to the user alone and go when they go.
PERSONAL_TABLES = frozenset({"api_keys", "saved_searches"})


def _references_to_users(db: Session) -> list[tuple[str, str, bool]]:
    """(table, column, nullable) for every FK column pointing at users.user_id."""
    insp = inspect(db.get_bind())
    refs = []
    for table in insp.get_table_names():
        if table == "users":
            continue
        fks = [fk for fk in insp.get_foreign_keys(table) if fk.get("referred_table") == "users"]
        if not fks:
            continue
        nullable = {c["name"]: c.get("nullable", True) for c in insp.get_columns(table)}
        for fk in fks:
            for col in fk.get("constrained_columns") or []:
                refs.append((table, col, nullable.get(col, True)))
    return refs


def release_user_references(db: Session, user_id: int, reassign_to: int) -> dict[str, int]:
    """Detach `user_id` from every referencing row. Does not commit.

    Returns rows affected per ``table.column`` (non-zero only), for the audit note.
    """
    q = db.get_bind().dialect.identifier_preparer.quote
    affected: dict[str, int] = {}
    for table, col, nullable in _references_to_users(db):
        t, c = q(table), q(col)
        if table in PERSONAL_TABLES:
            sql = f"DELETE FROM {t} WHERE {c} = :uid"
            params = {"uid": user_id}
        elif nullable:
            sql = f"UPDATE {t} SET {c} = NULL WHERE {c} = :uid"
            params = {"uid": user_id}
        else:
            sql = f"UPDATE {t} SET {c} = :to WHERE {c} = :uid"
            params = {"uid": user_id, "to": reassign_to}
        n = db.execute(text(sql), params).rowcount or 0
        if n:
            affected[f"{table}.{col}"] = n
    logger.info("user_references_released", user_id=user_id, reassigned_to=reassign_to,
                affected=affected)
    return affected
