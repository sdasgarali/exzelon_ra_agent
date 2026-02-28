"""Database migration for enterprise warmup engine tables and columns."""
import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(backend_path))

from sqlalchemy import text, inspect
from app.db.base import engine


def run_migration():
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()

    if "sender_mailboxes" not in existing_tables:
        print("sender_mailboxes table does not exist yet - will be created with all columns on startup")
        return

    # Add new columns to sender_mailboxes
    new_columns = [
        ("warmup_profile_id", "INTEGER"),
        ("connection_status", "VARCHAR(20) DEFAULT 'untested'"),
        ("last_connection_test_at", "DATETIME"),
        ("warmup_emails_sent", "INTEGER DEFAULT 0"),
        ("warmup_emails_received", "INTEGER DEFAULT 0"),
        ("warmup_opens", "INTEGER DEFAULT 0"),
        ("warmup_replies", "INTEGER DEFAULT 0"),
        ("last_dns_check_at", "DATETIME"),
        ("last_blacklist_check_at", "DATETIME"),
        ("dns_score", "INTEGER DEFAULT 0"),
        ("is_blacklisted", "BOOLEAN DEFAULT 0"),
        ("auto_recovery_started_at", "DATETIME"),
    ]

    existing_cols = {c["name"] for c in inspector.get_columns("sender_mailboxes")}

    added = 0
    with engine.connect() as conn:
        for col_name, col_type in new_columns:
            if col_name not in existing_cols:
                try:
                    conn.execute(text(
                        f"ALTER TABLE sender_mailboxes ADD COLUMN {col_name} {col_type}"
                    ))
                    conn.commit()
                    print(f"Added column sender_mailboxes.{col_name}")
                    added += 1
                except Exception as e:
                    print(f"Skipping {col_name}: {e}")

        if added > 0:
            conn.execute(text(
                "UPDATE sender_mailboxes SET connection_status = 'untested' WHERE connection_status IS NULL"
            ))
            conn.commit()

    print(f"Migration complete - {added} columns added")


if __name__ == "__main__":
    run_migration()
