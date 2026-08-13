"""Database seed data for testing."""
import json
from datetime import date, timedelta
from app.db.base import SessionLocal, engine, Base
from app.db.models.user import User, UserRole
from app.db.models.lead import LeadDetails, LeadStatus
from app.db.models.client import ClientInfo, ClientStatus, ClientCategory
from app.db.models.contact import ContactDetails, PriorityLevel
from app.db.models.settings import Settings
from app.db.models.sender_mailbox import SenderMailbox, WarmupStatus, EmailProvider
from app.core.security import get_password_hash


def create_tables():
    """Create all database tables."""
    Base.metadata.create_all(bind=engine)
    print("Database tables created.")


def seed_users(db):
    """Seed test users."""
    users = [
        {
            "email": "admin@exzelon.com",
            "password": "Admin@123",
            "full_name": "Admin User",
            "role": UserRole.ADMIN
        },
        {
            "email": "bdm@exzelon.com",
            "password": "Bdm@123",
            "full_name": "BDM User",
            "role": UserRole.BDM
        },
        {
            "email": "recruiter@exzelon.com",
            "password": "Recruiter@123",
            "full_name": "Recruiter User",
            "role": UserRole.RECRUITER
        },
        {
            "email": "testclient@example.com",
            "password": "TestClient@123",
            "full_name": "Test Client User",
            "role": UserRole.BDM
        }
    ]

    for user_data in users:
        existing = db.query(User).filter(User.email == user_data["email"]).first()
        if not existing:
            user = User(
                email=user_data["email"],
                password_hash=get_password_hash(user_data["password"]),
                full_name=user_data["full_name"],
                role=user_data["role"],
                is_active=True
            )
            db.add(user)
            print(f"Created user: {user_data['email']}")
        else:
            print(f"User already exists: {user_data['email']}")

    db.commit()


def seed_clients(db):
    """Seed test clients."""
    clients = [
        {"client_name": "Acme Healthcare Corp", "industry": "Healthcare", "company_size": "51-200", "category": ClientCategory.REGULAR},
        {"client_name": "MediCare Solutions Inc", "industry": "Healthcare", "company_size": "1-50", "category": ClientCategory.OCCASIONAL},
        {"client_name": "TechManufacturing LLC", "industry": "Manufacturing", "company_size": "201-500", "category": ClientCategory.PROSPECT},
        {"client_name": "Industrial Logistics Corp", "industry": "Logistics", "company_size": "51-200", "category": ClientCategory.REGULAR},
        {"client_name": "Retail Giants Co", "industry": "Retail", "company_size": "501-1000", "category": ClientCategory.OCCASIONAL},
        {"client_name": "AutoParts Manufacturing", "industry": "Automotive", "company_size": "51-200", "category": ClientCategory.PROSPECT},
        {"client_name": "Construction Builders Inc", "industry": "Construction", "company_size": "1-50", "category": ClientCategory.REGULAR},
        {"client_name": "Energy Solutions Ltd", "industry": "Energy", "company_size": "201-500", "category": ClientCategory.OCCASIONAL},
        {"client_name": "Food Processing Corp", "industry": "Food & Beverage", "company_size": "51-200", "category": ClientCategory.PROSPECT},
        {"client_name": "Hospitality Group LLC", "industry": "Hospitality", "company_size": "1-50", "category": ClientCategory.DORMANT},
    ]

    for client_data in clients:
        existing = db.query(ClientInfo).filter(ClientInfo.client_name == client_data["client_name"]).first()
        if not existing:
            client = ClientInfo(
                client_name=client_data["client_name"],
                status=ClientStatus.ACTIVE,
                start_date=date.today() - timedelta(days=90),
                client_category=client_data["category"],
                industry=client_data["industry"],
                company_size=client_data["company_size"],
                location_state="CA",
                service_count=3
            )
            db.add(client)
            print(f"Created client: {client_data['client_name']}")

    db.commit()


def seed_leads(db):
    """Seed test leads."""
    leads = [
        {"client_name": "Acme Healthcare Corp", "job_title": "Warehouse Manager", "state": "CA", "source": "linkedin", "salary_min": 55000, "salary_max": 75000},
        {"client_name": "Acme Healthcare Corp", "job_title": "HR Coordinator", "state": "CA", "source": "indeed", "salary_min": 45000, "salary_max": 60000},
        {"client_name": "MediCare Solutions Inc", "job_title": "Operations Manager", "state": "TX", "source": "glassdoor", "salary_min": 65000, "salary_max": 85000},
        {"client_name": "TechManufacturing LLC", "job_title": "Production Supervisor", "state": "OH", "source": "linkedin", "salary_min": 50000, "salary_max": 70000},
        {"client_name": "Industrial Logistics Corp", "job_title": "Logistics Coordinator", "state": "FL", "source": "indeed", "salary_min": 42000, "salary_max": 55000},
        {"client_name": "Retail Giants Co", "job_title": "Store Manager", "state": "NY", "source": "linkedin", "salary_min": 55000, "salary_max": 75000},
        {"client_name": "AutoParts Manufacturing", "job_title": "Quality Assurance Lead", "state": "MI", "source": "glassdoor", "salary_min": 60000, "salary_max": 80000},
        {"client_name": "Construction Builders Inc", "job_title": "Project Manager", "state": "TX", "source": "indeed", "salary_min": 70000, "salary_max": 95000},
        {"client_name": "Energy Solutions Ltd", "job_title": "Maintenance Technician", "state": "PA", "source": "linkedin", "salary_min": 45000, "salary_max": 60000},
        {"client_name": "Food Processing Corp", "job_title": "Plant Manager", "state": "GA", "source": "indeed", "salary_min": 75000, "salary_max": 100000},
    ]

    for i, lead_data in enumerate(leads):
        existing = db.query(LeadDetails).filter(
            LeadDetails.client_name == lead_data["client_name"],
            LeadDetails.job_title == lead_data["job_title"]
        ).first()
        if not existing:
            lead = LeadDetails(
                client_name=lead_data["client_name"],
                job_title=lead_data["job_title"],
                state=lead_data["state"],
                posting_date=date.today() - timedelta(days=i % 7),
                job_link=f"https://jobs.example.com/{1000 + i}",
                salary_min=lead_data["salary_min"],
                salary_max=lead_data["salary_max"],
                source=lead_data["source"],
                lead_status=LeadStatus.NEW,
                ra_name="Test RA"
            )
            db.add(lead)
            print(f"Created lead: {lead_data['client_name']} - {lead_data['job_title']}")

    db.commit()


def seed_contacts(db):
    """Seed test contacts."""
    contacts = [
        {"client_name": "Acme Healthcare Corp", "first_name": "John", "last_name": "Smith", "title": "HR Manager", "email": "john.smith@acmehealthcare.com", "state": "CA", "priority": PriorityLevel.P3_HR_MANAGER},
        {"client_name": "Acme Healthcare Corp", "first_name": "Jane", "last_name": "Doe", "title": "Recruiter", "email": "jane.doe@acmehealthcare.com", "state": "CA", "priority": PriorityLevel.P2_HR_TA_RECRUITER},
        {"client_name": "MediCare Solutions Inc", "first_name": "Michael", "last_name": "Johnson", "title": "Operations Director", "email": "michael.johnson@medicare.com", "state": "TX", "priority": PriorityLevel.P4_OPS_LEADER},
        {"client_name": "TechManufacturing LLC", "first_name": "Sarah", "last_name": "Williams", "title": "HR Director", "email": "sarah.williams@techmanufacturing.com", "state": "OH", "priority": PriorityLevel.P3_HR_MANAGER},
        {"client_name": "Industrial Logistics Corp", "first_name": "David", "last_name": "Brown", "title": "Talent Acquisition Specialist", "email": "david.brown@industriallogistics.com", "state": "FL", "priority": PriorityLevel.P1_JOB_POSTER},
        {"client_name": "Retail Giants Co", "first_name": "Emily", "last_name": "Garcia", "title": "HRBP", "email": "emily.garcia@retailgiants.com", "state": "NY", "priority": PriorityLevel.P3_HR_MANAGER},
        {"client_name": "AutoParts Manufacturing", "first_name": "Robert", "last_name": "Miller", "title": "Plant Manager", "email": "robert.miller@autoparts.com", "state": "MI", "priority": PriorityLevel.P4_OPS_LEADER},
        {"client_name": "Construction Builders Inc", "first_name": "Lisa", "last_name": "Davis", "title": "HR Coordinator", "email": "lisa.davis@constructionbuilders.com", "state": "TX", "priority": PriorityLevel.P2_HR_TA_RECRUITER},
        {"client_name": "Energy Solutions Ltd", "first_name": "James", "last_name": "Wilson", "title": "Department Manager", "email": "james.wilson@energysolutions.com", "state": "PA", "priority": PriorityLevel.P5_FUNCTIONAL_MANAGER},
        {"client_name": "Food Processing Corp", "first_name": "Maria", "last_name": "Martinez", "title": "VP of HR", "email": "maria.martinez@foodprocessing.com", "state": "GA", "priority": PriorityLevel.P3_HR_MANAGER},
    ]

    for contact_data in contacts:
        existing = db.query(ContactDetails).filter(ContactDetails.email == contact_data["email"]).first()
        if not existing:
            contact = ContactDetails(
                client_name=contact_data["client_name"],
                first_name=contact_data["first_name"],
                last_name=contact_data["last_name"],
                title=contact_data["title"],
                email=contact_data["email"],
                location_state=contact_data["state"],
                phone=f"+1-555-{100 + len(contacts)}-{1000 + len(contacts)}",
                source="mock",
                priority_level=contact_data["priority"],
                validation_status="valid"  # Pre-validated for testing
            )
            db.add(contact)
            print(f"Created contact: {contact_data['first_name']} {contact_data['last_name']}")

    db.commit()


def seed_settings(db):
    """Seed default settings."""
    settings = [
        {"key": "data_storage", "value": "database", "type": "string", "description": "Storage mode"},
        {"key": "daily_send_limit", "value": 30, "type": "integer", "description": "Max emails per day"},
        {"key": "cooldown_days", "value": 10, "type": "integer", "description": "Days between emails"},
        {"key": "max_contacts_per_company_job", "value": 4, "type": "integer", "description": "Max contacts per job"},
        {"key": "min_salary_threshold", "value": 40000, "type": "integer", "description": "Minimum salary"},
        {"key": "contact_provider", "value": "mock", "type": "string", "description": "Contact discovery provider"},
        {"key": "email_validation_provider", "value": "mock", "type": "string", "description": "Email validation provider"},
        {"key": "email_send_mode", "value": "mailmerge", "type": "string", "description": "Email send mode"},
        {"key": "unsubscribe_footer", "value": True, "type": "boolean", "description": "Include unsubscribe footer"},
    ]

    for setting_data in settings:
        existing = db.query(Settings).filter(Settings.key == setting_data["key"]).first()
        if not existing:
            setting = Settings(
                key=setting_data["key"],
                value_json=json.dumps(setting_data["value"]),
                type=setting_data["type"],
                description=setting_data["description"],
                updated_by="system"
            )
            db.add(setting)
            print(f"Created setting: {setting_data['key']}")

    db.commit()


def seed_mailboxes(db):
    """Seed sender mailboxes for cold email outreach."""
    # Sender mailboxes with Cold-Ready status
    mailboxes = [
        {"email": "Brian@exzelon.com", "password": "Exz@2631", "display_name": "Brian from Exzelon"},
        {"email": "David@exzelon.com", "password": "Exz@2631", "display_name": "David from Exzelon"},
        {"email": "Stacey@exzelon.com", "password": "Exz@2631", "display_name": "Stacey from Exzelon"},
        {"email": "bretiney@exzelon.com", "password": "Exz@2631", "display_name": "Bretiney from Exzelon"},
        {"email": "Imely@exzelon.com", "password": "Exz@2631", "display_name": "Imely from Exzelon"},
        {"email": "Jane.rose@exzelon.com", "password": "Exz@2631", "display_name": "Jane Rose from Exzelon"},
        {"email": "Robert@exzelon.com", "password": "Exz@2631", "display_name": "Robert from Exzelon"},
        {"email": "Britney@exzelon.com", "password": "Exz@2631", "display_name": "Britney from Exzelon"},
        {"email": "Steve@exzelon.com", "password": "Exz@2631", "display_name": "Steve from Exzelon"},
        {"email": "Jane@exzelon.com", "password": "Exz@2631", "display_name": "Jane from Exzelon"},
    ]

    for mailbox_data in mailboxes:
        existing = db.query(SenderMailbox).filter(SenderMailbox.email == mailbox_data["email"]).first()
        if not existing:
            mailbox = SenderMailbox(
                email=mailbox_data["email"],
                password=mailbox_data["password"],
                display_name=mailbox_data["display_name"],
                provider=EmailProvider.MICROSOFT_365,
                smtp_host="smtp.office365.com",
                smtp_port=587,
                imap_host="outlook.office365.com",
                imap_port=993,
                warmup_status=WarmupStatus.COLD_READY,
                is_active=True,
                daily_send_limit=30,
                notes="Initial setup - Cold Ready for outreach"
            )
            db.add(mailbox)
            print(f"Created mailbox: {mailbox_data['email']}")
        else:
            print(f"Mailbox already exists: {mailbox_data['email']}")

    # Add Microsoft 365 admin account as a special sender
    admin_mailbox_email = "Zanemartin@exzelon.com"
    existing_admin = db.query(SenderMailbox).filter(SenderMailbox.email == admin_mailbox_email).first()
    if not existing_admin:
        admin_mailbox = SenderMailbox(
            email=admin_mailbox_email,
            password="Dex@2631",
            display_name="Zane Martin - Exzelon",
            provider=EmailProvider.MICROSOFT_365,
            smtp_host="smtp.office365.com",
            smtp_port=587,
            imap_host="outlook.office365.com",
            imap_port=993,
            warmup_status=WarmupStatus.COLD_READY,
            is_active=True,
            daily_send_limit=50,
            notes="Microsoft 365 Admin Account - Primary Sender"
        )
        db.add(admin_mailbox)
        print(f"Created admin mailbox: {admin_mailbox_email}")
    else:
        print(f"Admin mailbox already exists: {admin_mailbox_email}")

    db.commit()
    print(f"Total mailboxes seeded: {len(mailboxes) + 1}")


def run_seed():
    """Run all seed functions."""
    print("Starting database seeding...")

    create_tables()

    db = SessionLocal()
    try:
        seed_users(db)
        seed_clients(db)
        seed_leads(db)
        seed_contacts(db)
        seed_settings(db)
        seed_mailboxes(db)
        print("\nDatabase seeding completed successfully!")
        print("\nTest credentials:")
        print("  Admin: admin@exzelon.com / Admin@123")
        print("  BDM: bdm@exzelon.com / Bdm@123")
        print("  Recruiter: recruiter@exzelon.com / Recruiter@123")
        print("  Test Client: testclient@example.com / TestClient@123")
        print("\nMailboxes seeded: 11 sender mailboxes (Cold-Ready status)")
    finally:
        db.close()


if __name__ == "__main__":
    run_seed()
