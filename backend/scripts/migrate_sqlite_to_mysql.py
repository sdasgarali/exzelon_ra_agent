"""
SQLite -> MySQL migration script.

Copies all schema and data from the SQLite database to a MySQL database.
Uses SQLAlchemy models to create schema, then bulk-inserts data table by table
in FK-safe topological order.

Usage:
    cd backend && python -m scripts.migrate_sqlite_to_mysql
"""
import sys
import enum
from pathlib import Path
from datetime import datetime

# Add backend to path so app modules resolve
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker

# Import all models so Base.metadata is fully populated
from app.db.base import Base
from app.db.models import (  # noqa: F401
    User, LeadDetails, ClientInfo, ContactDetails, LeadContactAssociation,
    EmailValidationResult, OutreachEvent, SuppressionList, JobRun, Settings,
    SenderMailbox, WarmupEmail, WarmupDailyLog, WarmupAlert, WarmupProfile,
    DNSCheckResult, BlacklistCheckResult, EmailTemplate,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SQLITE_PATH = backend_dir / "data" / "ra_agent.db"
MYSQL_USER = "root"
MYSQL_PASSWORD = "AdminRootDBAli"
MYSQL_HOST = "localhost"
MYSQL_PORT = 3306
MYSQL_DB = "cold_email_ai_agent"

SQLITE_URL = f"sqlite:///{SQLITE_PATH}"
MYSQL_URL = (
    f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}"
    f"@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}?charset=utf8mb4"
)

# Tables in FK-safe topological order (parents before children)
TIER_0 = [
    "lead_details",
    "client_info",
    "users",
    "settings",
    "warmup_profiles",
    "sender_mailboxes",
    "email_templates",
    "email_validation_results",
    "suppression_list",
    "job_runs",
]
TIER_1 = [
    "contact_details",
    "warmup_emails",
    "warmup_daily_logs",
    "warmup_alerts",
    "dns_check_results",
    "blacklist_check_results",
    "outreach_events",
]
TIER_2 = [
    "lead_contact_associations",
]
MIGRATION_ORDER = TIER_0 + TIER_1 + TIER_2

# Tables with auto-increment integer PKs
AUTO_INCREMENT_PKS = {
    "lead_details": "lead_id",
    "client_info": "client_id",
    "users": "user_id",
    "sender_mailboxes": "mailbox_id",
    "email_templates": "template_id",
    "email_validation_results": "validation_id",
    "suppression_list": "suppression_id",
    "job_runs": "run_id",
    "contact_details": "contact_id",
    "warmup_emails": "id",
    "warmup_daily_logs": "id",
    "warmup_alerts": "id",
    "warmup_profiles": "id",
    "dns_check_results": "id",
    "blacklist_check_results": "id",
    "outreach_events": "event_id",
    "lead_contact_associations": "id",
}


def convert_value(val):
    """Convert Python enum instances and other types for MySQL insertion."""
    if val is None:
        return None
    if isinstance(val, enum.Enum):
        return val.value
    if isinstance(val, bool):
        return int(val)
    return val


def migrate():
    print("=" * 60)
    print("SQLite -> MySQL Migration")
    print("=" * 60)

    # --- Verify SQLite source ---
    if not SQLITE_PATH.exists():
        print(f"ERROR: SQLite database not found at {SQLITE_PATH}")
        sys.exit(1)
    print(f"Source: {SQLITE_PATH}")
    print(f"Target: mysql+pymysql://root:***@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}")
    print()

    # --- Create MySQL database if it does not exist ---
    root_url = (
        f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}"
        f"@{MYSQL_HOST}:{MYSQL_PORT}/?charset=utf8mb4"
    )
    root_engine = create_engine(root_url)
    with root_engine.connect() as conn:
        conn.execute(text(
            f"CREATE DATABASE IF NOT EXISTS `{MYSQL_DB}` "
            f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        ))
        conn.commit()
    root_engine.dispose()
    db_name_str = MYSQL_DB
    print(f"Database {db_name_str!r} ensured.")

    # --- Connect to both databases ---
    sqlite_engine = create_engine(SQLITE_URL)
    mysql_engine = create_engine(MYSQL_URL)

    sqlite_session = sessionmaker(bind=sqlite_engine)()

    # --- Drop all existing tables in MySQL and recreate ---
    print("Dropping existing MySQL tables...")
    with mysql_engine.connect() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        conn.commit()
    Base.metadata.drop_all(mysql_engine)
    print("Creating MySQL schema from SQLAlchemy models...")
    Base.metadata.create_all(mysql_engine)
    print(f"Created {len(Base.metadata.tables)} tables.")
    print()

    # --- Copy data table by table ---
    with mysql_engine.connect() as mysql_conn:
        mysql_conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        mysql_conn.commit()

        sqlite_inspector = inspect(sqlite_engine)
        sqlite_tables = sqlite_inspector.get_table_names()

        total_rows = 0
        results = {}

        for table_name in MIGRATION_ORDER:
            if table_name not in sqlite_tables:
                print(f"  SKIP  {table_name} (not in SQLite)")
                results[table_name] = ("SKIP", 0)
                continue

            if table_name not in Base.metadata.tables:
                print(f"  SKIP  {table_name} (not in SQLAlchemy metadata)")
                results[table_name] = ("SKIP", 0)
                continue

            sa_table = Base.metadata.tables[table_name]

            # Read all rows from SQLite
            sqlite_rows = sqlite_session.execute(
                text(f"SELECT * FROM {table_name}")
            ).fetchall()

            if not sqlite_rows:
                print(f"  OK    {table_name}: 0 rows (empty)")
                results[table_name] = ("OK", 0)
                continue

            # Get column names from SQLite result
            col_names = list(sqlite_rows[0]._mapping.keys())

            # Get MySQL column names to handle schema mismatches
            mysql_insp = inspect(mysql_engine)
            mysql_cols = {c["name"] for c in mysql_insp.get_columns(table_name)}

            # Only use columns that exist in BOTH SQLite and MySQL
            common_cols = [c for c in col_names if c in mysql_cols]

            # Build dicts for insertion
            row_dicts = []
            for row in sqlite_rows:
                row_map = row._mapping
                d = {}
                for col in common_cols:
                    d[col] = convert_value(row_map[col])
                row_dicts.append(d)

            # Batch insert (chunks of 500)
            batch_size = 500
            for i in range(0, len(row_dicts), batch_size):
                batch = row_dicts[i:i + batch_size]
                mysql_conn.execute(sa_table.insert(), batch)
                mysql_conn.commit()

            count = len(row_dicts)
            total_rows += count
            print(f"  OK    {table_name}: {count} rows")
            results[table_name] = ("OK", count)

        # --- Re-enable FK checks ---
        mysql_conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
        mysql_conn.commit()

        # --- Reset AUTO_INCREMENT counters ---
        print()
        print("Resetting AUTO_INCREMENT counters...")
        for table_name, pk_col in AUTO_INCREMENT_PKS.items():
            if results.get(table_name, ("SKIP", 0))[1] > 0:
                result = mysql_conn.execute(
                    text(f"SELECT MAX(`{pk_col}`) FROM `{table_name}`")
                ).scalar()
                if result is not None:
                    next_val = result + 1
                    mysql_conn.execute(
                        text(f"ALTER TABLE `{table_name}` AUTO_INCREMENT = {next_val}")
                    )
                    mysql_conn.commit()

    # --- Verification ---
    print()
    print("=" * 60)
    print("VERIFICATION -- Row count comparison")
    print("=" * 60)
    header = f"{'Table':<33} {'SQLite':>8} {'MySQL':>8} {'Match':>6}"
    print(f"  {header}")
    print("  " + "-" * 57)

    all_match = True
    for table_name in MIGRATION_ORDER:
        if table_name not in sqlite_tables:
            continue

        sqlite_count = sqlite_session.execute(
            text(f"SELECT COUNT(*) FROM {table_name}")
        ).scalar()

        try:
            with mysql_engine.connect() as vconn:
                mysql_count = vconn.execute(
                    text(f"SELECT COUNT(*) FROM `{table_name}`")
                ).scalar()
        except Exception:
            mysql_count = "ERR"

        match = sqlite_count == mysql_count
        if not match:
            all_match = False
        symbol = "OK" if match else "FAIL"
        print(f"  {table_name:<33} {sqlite_count:>8} {str(mysql_count):>8} {symbol:>6}")

    print("  " + "-" * 57)
    print(f"  Total rows migrated: {total_rows}")
    if all_match:
        print("  ALL TABLES MATCH -- Migration successful!")
    else:
        print("  WARNING: Some tables have mismatched counts!")

    # --- Cleanup ---
    sqlite_session.close()
    sqlite_engine.dispose()
    mysql_engine.dispose()

    print()
    print("Done. Update .env to DB_TYPE=mysql to use the new database.")


if __name__ == "__main__":
    migrate()
