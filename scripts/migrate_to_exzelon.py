"""
Data migration script: cold_email_ai_agent → exzelon_ra_agent

Reads from the source database (READ ONLY), creates exzelon_ra_agent database,
copies all data with the following transformations:
  - Drops: tenants, permissions, role_permissions tables
  - Strips: tenant_id column from all tables during copy
  - Converts: super_admin/tenant_admin users to admin role
  - Fixes: Settings PK from composite (key, tenant_id) to just key
  - Changes: role enum to ENUM('admin','operator','viewer')

Usage:
  python scripts/migrate_to_exzelon.py [--source-db cold_email_ai_agent] [--target-db exzelon_ra_agent]
"""
import argparse
import sys
import os

# Add backend to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

try:
    import pymysql
except ImportError:
    print("ERROR: pymysql is required. Install with: pip install pymysql")
    sys.exit(1)


# Tables to skip entirely (multi-tenant artifacts)
SKIP_TABLES = {"tenants", "permissions", "role_permissions"}

# Tables that have tenant_id columns to strip
TENANT_TABLES = {
    "users", "lead_details", "contact_details", "lead_contact_associations",
    "client_info", "sender_mailboxes", "outreach_events", "email_templates",
    "warmup_profiles", "job_runs", "audit_logs", "suppression_list",
    "email_validation_results", "warmup_emails", "warmup_daily_logs",
    "warmup_alerts", "dns_check_results", "blacklist_check_results",
    "settings",
}


def get_connection_params():
    """Get MySQL connection parameters from environment or defaults."""
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

    return {
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": int(os.environ.get("DB_PORT", 3306)),
        "user": os.environ.get("DB_USER", "root"),
        "password": os.environ.get("DB_PASSWORD", ""),
        "charset": "utf8mb4",
    }


def migrate(source_db: str, target_db: str, dry_run: bool = False):
    """Run the migration from source to target database."""
    params = get_connection_params()
    print(f"Connecting to MySQL at {params['host']}:{params['port']} as {params['user']}")

    conn = pymysql.connect(**params)
    cursor = conn.cursor()

    try:
        # Step 1: Create target database
        print(f"\n--- Step 1: Create target database '{target_db}' ---")
        if not dry_run:
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{target_db}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            conn.commit()
        print(f"  Database '{target_db}' created/verified")

        # Step 2: Get list of tables from source
        cursor.execute(f"USE `{source_db}`")
        cursor.execute("SHOW TABLES")
        all_tables = [row[0] for row in cursor.fetchall()]
        tables_to_copy = [t for t in all_tables if t not in SKIP_TABLES]
        print(f"\n--- Step 2: Tables in source: {len(all_tables)}, copying: {len(tables_to_copy)}, skipping: {SKIP_TABLES & set(all_tables)} ---")

        # Step 3: For each table, get DDL, modify, create in target, copy data
        for table in tables_to_copy:
            print(f"\n  Processing: {table}")

            # Get columns from source
            cursor.execute(f"DESCRIBE `{source_db}`.`{table}`")
            columns_info = cursor.fetchall()
            all_columns = [col[0] for col in columns_info]

            # Determine which columns to copy (strip tenant_id)
            copy_columns = [c for c in all_columns if c != "tenant_id"]

            # Get CREATE TABLE statement
            cursor.execute(f"SHOW CREATE TABLE `{source_db}`.`{table}`")
            create_stmt = cursor.fetchone()[1]

            # Modify DDL for target: remove tenant_id column and FK references
            modified_ddl = _strip_tenant_from_ddl(create_stmt, table, target_db)

            if not dry_run:
                # Drop table in target if exists, then create
                cursor.execute(f"DROP TABLE IF EXISTS `{target_db}`.`{table}`")
                cursor.execute(modified_ddl)
                conn.commit()

                # Special handling for settings table: deduplicate by key
                if table == "settings":
                    _copy_settings(cursor, conn, source_db, target_db, copy_columns)
                elif table == "users":
                    _copy_users(cursor, conn, source_db, target_db, copy_columns)
                else:
                    # Copy data
                    cols_str = ", ".join(f"`{c}`" for c in copy_columns)
                    cursor.execute(f"INSERT INTO `{target_db}`.`{table}` ({cols_str}) SELECT {cols_str} FROM `{source_db}`.`{table}`")
                    rows = cursor.rowcount
                    conn.commit()
                    print(f"    Copied {rows} rows")
            else:
                print(f"    [DRY RUN] Would copy columns: {copy_columns}")

        # Step 4: Fix role enum on users table
        print(f"\n--- Step 4: Fix role enum ---")
        if not dry_run:
            try:
                cursor.execute(
                    f"ALTER TABLE `{target_db}`.`users` MODIFY COLUMN `role` "
                    f"ENUM('admin','operator','viewer') NOT NULL DEFAULT 'viewer'"
                )
                conn.commit()
                print("  Role enum updated to: admin, operator, viewer")
            except Exception as e:
                print(f"  Warning: role enum update: {e}")

        # Step 5: Verify row counts
        print(f"\n--- Step 5: Verification ---")
        for table in tables_to_copy:
            cursor.execute(f"SELECT COUNT(*) FROM `{source_db}`.`{table}`")
            source_count = cursor.fetchone()[0]
            if not dry_run:
                cursor.execute(f"SELECT COUNT(*) FROM `{target_db}`.`{table}`")
                target_count = cursor.fetchone()[0]
                status = "OK" if source_count == target_count or table in ("settings", "users") else "MISMATCH"
                print(f"  {table}: source={source_count}, target={target_count} [{status}]")
            else:
                print(f"  {table}: source={source_count} [DRY RUN]")

        print(f"\nMigration {'dry run ' if dry_run else ''}complete!")

    finally:
        cursor.close()
        conn.close()


def _strip_tenant_from_ddl(ddl: str, table: str, target_db: str) -> str:
    """Remove tenant_id column and related constraints from CREATE TABLE DDL."""
    lines = ddl.split("\n")
    filtered = []
    for line in lines:
        line_lower = line.strip().lower()
        # Skip tenant_id column
        if "`tenant_id`" in line.lower():
            continue
        # Skip FK constraint referencing tenants table
        if "references `tenants`" in line_lower or "foreign key" in line_lower and "tenant_id" in line_lower:
            continue
        # Skip indexes on tenant_id
        if "tenant_id" in line_lower and ("index" in line_lower or "key" in line_lower):
            continue
        filtered.append(line)

    # Fix CREATE TABLE to use target database
    result = "\n".join(filtered)
    result = result.replace(f"CREATE TABLE `{table}`", f"CREATE TABLE `{target_db}`.`{table}`")

    # Fix trailing commas before closing paren
    result = result.replace(",\n)", "\n)")

    return result


def _copy_settings(cursor, conn, source_db, target_db, copy_columns):
    """Copy settings with deduplication (keep first row per key)."""
    cols_str = ", ".join(f"`{c}`" for c in copy_columns)
    # Use GROUP BY to deduplicate by key
    cursor.execute(
        f"INSERT INTO `{target_db}`.`settings` ({cols_str}) "
        f"SELECT {cols_str} FROM `{source_db}`.`settings` "
        f"GROUP BY `key`"
    )
    rows = cursor.rowcount
    conn.commit()
    print(f"    Copied {rows} settings rows (deduplicated by key)")


def _copy_users(cursor, conn, source_db, target_db, copy_columns):
    """Copy users with role conversion: super_admin/tenant_admin → admin."""
    cols_str = ", ".join(f"`{c}`" for c in copy_columns)

    # Build SELECT with role conversion
    select_cols = []
    for c in copy_columns:
        if c == "role":
            select_cols.append(
                "CASE "
                "WHEN `role` IN ('super_admin', 'tenant_admin') THEN 'admin' "
                "ELSE `role` "
                "END"
            )
        else:
            select_cols.append(f"`{c}`")

    select_str = ", ".join(select_cols)
    cursor.execute(f"INSERT INTO `{target_db}`.`users` ({cols_str}) SELECT {select_str} FROM `{source_db}`.`users`")
    rows = cursor.rowcount
    conn.commit()

    # Count conversions
    cursor.execute(f"SELECT COUNT(*) FROM `{source_db}`.`users` WHERE `role` IN ('super_admin', 'tenant_admin')")
    converted = cursor.fetchone()[0]
    print(f"    Copied {rows} users ({converted} super_admin/tenant_admin converted to admin)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate cold_email_ai_agent to exzelon_ra_agent")
    parser.add_argument("--source-db", default="cold_email_ai_agent", help="Source database name")
    parser.add_argument("--target-db", default="exzelon_ra_agent", help="Target database name")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes")
    args = parser.parse_args()

    migrate(args.source_db, args.target_db, args.dry_run)
