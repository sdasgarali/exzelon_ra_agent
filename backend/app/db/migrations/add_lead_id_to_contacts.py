"""
Database migration to add lead_id column to contact_details table.
This creates a direct relationship between contacts and leads.

Run this script to migrate the database:
    python -m app.db.migrations.add_lead_id_to_contacts
"""
import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(backend_path))

from sqlalchemy import text, inspect
from app.db.base import SessionLocal, engine


def migrate():
    """Add lead_id column to contact_details table."""
    db = SessionLocal()

    try:
        # Check if column already exists (works on both SQLite and MySQL)
        inspector = inspect(engine)
        existing_cols = {c["name"] for c in inspector.get_columns("contact_details")}
        
        if "lead_id" in existing_cols:
            print("Column 'lead_id' already exists in contact_details table.")
            return

        print("Adding 'lead_id' column to contact_details table...")

        # Add the column (SQLite syntax)
        alter_query = text("""
            ALTER TABLE contact_details ADD COLUMN lead_id INTEGER REFERENCES lead_details(lead_id)
        """)
        db.execute(alter_query)
        db.commit()

        # Create index
        index_query = text("""
            CREATE INDEX IF NOT EXISTS idx_contact_lead ON contact_details(lead_id)
        """)
        db.execute(index_query)
        db.commit()

        print("Migration complete: lead_id column added successfully.")

        # Try to link existing contacts to leads based on client_name
        print("Attempting to link existing contacts to leads based on client_name...")

        link_query = text("""
            UPDATE contact_details
            SET lead_id = (
                SELECT lead_id FROM lead_details
                WHERE lead_details.client_name = contact_details.client_name
                ORDER BY lead_details.created_at DESC
                LIMIT 1
            )
            WHERE lead_id IS NULL
        """)
        result = db.execute(link_query)
        db.commit()

        print(f"Linked {result.rowcount} contacts to leads based on client_name.")

    except Exception as e:
        print(f"Migration error: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    migrate()
