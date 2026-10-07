"""Demo data seeder for new starter-plan tenants.

Idempotent: every row is get-or-create by its natural key, so running it again (it
runs on every API start for the neuraforz/medeoan tenants) adds nothing, never
duplicates and never deletes. Existing rows are reused untouched.
"""
from typing import Callable, Optional, Tuple, Type

import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models.lead import LeadDetails, LeadStatus
from app.db.models.contact import ContactDetails
from app.db.models.client import ClientInfo
from app.db.models.campaign import Campaign, CampaignStatus
from app.db.models.email_template import EmailTemplate, TemplateStatus, TemplateCategory
from app.db.models.deal import Deal, DealStage

logger = structlog.get_logger()

DEMO_COMPANIES = [
    ("TechCorp Solutions", "Technology", "CA", "San Francisco"),
    ("MediHealth Inc", "Healthcare", "NY", "New York"),
    ("GreenEnergy Co", "Energy", "TX", "Austin"),
    ("FinanceFirst LLC", "Financial Services", "IL", "Chicago"),
    ("EduLearn Academy", "Education", "MA", "Boston"),
    ("RetailPro Group", "Retail", "WA", "Seattle"),
    ("BuildRight Construction", "Construction", "FL", "Miami"),
    ("FoodTech Innovations", "Food & Beverage", "OR", "Portland"),
    ("LogiMove Transport", "Logistics", "GA", "Atlanta"),
    ("MediaWave Digital", "Media & Entertainment", "CA", "Los Angeles"),
]

DEMO_TITLES = [
    "Senior Software Engineer", "Marketing Manager", "Product Manager",
    "Data Analyst", "Sales Director", "HR Coordinator",
    "DevOps Engineer", "Content Strategist", "Financial Analyst",
    "Operations Manager", "UX Designer", "Business Development Rep",
    "Cloud Architect", "Customer Success Manager", "Supply Chain Manager",
    "Quality Assurance Lead", "Digital Marketing Specialist", "IT Project Manager",
    "Recruitment Specialist", "Account Executive", "Research Scientist",
    "Compliance Officer", "Social Media Manager", "Security Engineer",
    "Training Coordinator",
]

# (first, last, title, email, index into DEMO_COMPANIES)
DEMO_CONTACTS = [
    ("Sarah", "Johnson", "HR Director", "sarah.johnson@demo-techcorp.example", 0),
    ("Mike", "Chen", "VP Engineering", "mike.chen@demo-techcorp.example", 0),
    ("Emily", "Rodriguez", "Talent Acquisition", "emily.r@demo-medihealth.example", 1),
    ("James", "Williams", "CTO", "james.w@demo-greenenergy.example", 2),
    ("Lisa", "Thompson", "Hiring Manager", "lisa.t@demo-financefirst.example", 3),
    ("David", "Kim", "Director of Ops", "david.kim@demo-edulearn.example", 4),
    ("Amanda", "Brown", "VP Sales", "amanda.b@demo-retailpro.example", 5),
    ("Robert", "Davis", "COO", "robert.d@demo-buildright.example", 6),
    ("Jennifer", "Martinez", "HR Manager", "jen.m@demo-foodtech.example", 7),
    ("Thomas", "Wilson", "Director of People", "tom.w@demo-logimove.example", 8),
    ("Rachel", "Lee", "VP Marketing", "rachel.l@demo-mediawave.example", 9),
    ("Chris", "Taylor", "Engineering Manager", "chris.t@demo-techcorp.example", 0),
    ("Megan", "Anderson", "Recruiter", "megan.a@demo-medihealth.example", 1),
    ("Alex", "Jackson", "Program Manager", "alex.j@demo-greenenergy.example", 2),
    ("Nicole", "White", "Head of Sales", "nicole.w@demo-financefirst.example", 3),
]

DEMO_TEMPLATES = [
    dict(
        name="[Demo] Introduction Template",
        subject="Quick question about {{title}}",
        body_html="Hi {{first_name}},<br><br>I noticed {{company}} is hiring for a {{title}} role. I help companies find top talent faster.<br><br>Would you be open to a quick 15-minute call this week?<br><br>Best,<br>{{sender_name}}",
        body_text="Hi {{first_name}},\n\nI noticed {{company}} is hiring for a {{title}} role. I help companies find top talent faster.\n\nWould you be open to a quick 15-minute call this week?\n\nBest,\n{{sender_name}}",
        status=TemplateStatus.ACTIVE,
        category=TemplateCategory.OUTREACH,
    ),
    dict(
        name="[Demo] Follow-up Template",
        subject="Re: {{title}} position",
        body_html="Hi {{first_name}},<br><br>Just following up on my previous email about the {{title}} opportunity at {{company}}.<br><br>I have several qualified candidates who could be a great fit. Would you have 10 minutes to discuss?<br><br>Best regards,<br>{{sender_name}}",
        body_text="Hi {{first_name}},\n\nJust following up on my previous email about the {{title}} opportunity at {{company}}.\n\nI have several qualified candidates who could be a great fit. Would you have 10 minutes to discuss?\n\nBest regards,\n{{sender_name}}",
        status=TemplateStatus.ACTIVE,
        category=TemplateCategory.FOLLOWUP,
    ),
]

DEMO_CAMPAIGN_NAME = "[Demo] Outreach Campaign"

DEFAULT_STAGES = [
    dict(name="New Lead", stage_order=1, color="#3b82f6"),
    dict(name="Contacted", stage_order=2, color="#8b5cf6"),
    dict(name="Qualified", stage_order=3, color="#06b6d4"),
    dict(name="Proposal", stage_order=4, color="#f59e0b"),
    dict(name="Negotiation", stage_order=5, color="#ef4444"),
    dict(name="Won", stage_order=6, color="#22c55e", is_won=True),
    dict(name="Lost", stage_order=7, color="#6b7280", is_lost=True),
]

# (deal name, stage name, value, probability)
DEMO_DEALS = [
    ("TechCorp Solutions -- Sarah Johnson", "New Lead", 15000, 20),
    ("MediHealth Inc -- Emily Rodriguez", "Contacted", 25000, 40),
    ("GreenEnergy Co -- James Williams", "Qualified", 50000, 60),
    ("FinanceFirst LLC -- Lisa Thompson", "Proposal", 35000, 70),
    ("RetailPro Group -- Amanda Brown", "Negotiation", 40000, 80),
]


def _get_or_create(
    db: Session,
    model: Type,
    lookup: dict,
    build: Callable[[], object],
) -> Tuple[object, bool]:
    """Return ``(row, created)``. Inserts inside a SAVEPOINT so that a concurrent
    insert of the same natural key (two API workers starting together) is absorbed
    by re-reading the winner instead of failing the whole seed."""
    row = db.query(model).filter_by(**lookup).first()
    if row is not None:
        return row, False
    savepoint = db.begin_nested()
    try:
        row = build()
        db.add(row)
        db.flush()
        savepoint.commit()
        return row, True
    except IntegrityError:
        savepoint.rollback()
        existing = db.query(model).filter_by(**lookup).first()
        if existing is None:
            raise
        return existing, False


def seed_demo_data(tenant_id: int, db: Session) -> dict:
    """Seed demo data for a tenant that has no leads yet. Safe to call repeatedly.

    Seeds (get-or-create): 10 clients, 25 leads, 15 contacts, 2 templates,
    1 campaign, 5 deals. A tenant that already has leads of its own is left alone.
    Returns: dict with counts of rows CREATED by this call (all zero on a re-run).
    """
    result = {"clients": 0, "leads": 0, "contacts": 0, "templates": 0, "campaigns": 0, "deals": 0}

    try:
        # A tenant with real (or previously seeded) leads is not a demo candidate.
        existing_leads = db.query(LeadDetails).filter(LeadDetails.tenant_id == tenant_id).count()
        if existing_leads > 0:
            logger.debug("Demo data already exists, skipping", tenant_id=tenant_id)
            return result

        # 1. Clients — unique on (tenant_id, client_name) (idx_client_tenant_name).
        clients = []
        for name, industry, state, _city in DEMO_COMPANIES:
            client, created = _get_or_create(
                db, ClientInfo,
                {"tenant_id": tenant_id, "client_name": name},
                lambda name=name, industry=industry, state=state: ClientInfo(
                    tenant_id=tenant_id,
                    client_name=name,
                    industry=industry,
                    location_state=state,
                    employee_count=50 + (len(name) * 10),  # pseudo-random
                ),
            )
            clients.append(client)
            result["clients"] += int(created)

        # 2. Leads (job postings)
        for i, title in enumerate(DEMO_TITLES):
            company = DEMO_COMPANIES[i % len(DEMO_COMPANIES)]
            client = clients[i % len(clients)]
            _lead, created = _get_or_create(
                db, LeadDetails,
                {"tenant_id": tenant_id, "client_name": company[0], "job_title": title, "source": "demo"},
                lambda title=title, client=client, company=company: LeadDetails(
                    tenant_id=tenant_id,
                    job_title=title,
                    client_name=company[0],
                    state=client.location_state or company[2],
                    city=company[3],
                    source="demo",
                    lead_status=LeadStatus.OPEN,
                ),
            )
            result["leads"] += int(created)

        # 3. Contacts — keyed by email within the tenant.
        contacts = []
        for first, last, title, email, company_idx in DEMO_CONTACTS:
            contact, created = _get_or_create(
                db, ContactDetails,
                {"tenant_id": tenant_id, "email": email},
                lambda first=first, last=last, title=title, email=email, company_idx=company_idx: ContactDetails(
                    tenant_id=tenant_id,
                    first_name=first,
                    last_name=last,
                    title=title,
                    email=email,
                    client_name=DEMO_COMPANIES[company_idx][0],
                    source="demo",
                ),
            )
            contacts.append(contact)
            result["contacts"] += int(created)

        # 4. Email templates — keyed by name.
        for spec in DEMO_TEMPLATES:
            _tpl, created = _get_or_create(
                db, EmailTemplate,
                {"tenant_id": tenant_id, "name": spec["name"]},
                lambda spec=spec: EmailTemplate(tenant_id=tenant_id, **spec),
            )
            result["templates"] += int(created)

        # 5. Demo campaign — keyed by name.
        _campaign, created = _get_or_create(
            db, Campaign,
            {"tenant_id": tenant_id, "name": DEMO_CAMPAIGN_NAME},
            lambda: Campaign(
                tenant_id=tenant_id,
                name=DEMO_CAMPAIGN_NAME,
                description="Sample outreach campaign targeting hiring managers",
                status=CampaignStatus.DRAFT,
            ),
        )
        result["campaigns"] += int(created)

        # 6. Deal stages: only when the tenant has none of its own.
        stages = db.query(DealStage).filter(DealStage.tenant_id == tenant_id).all()
        if not stages:
            stages = [DealStage(tenant_id=tenant_id, **spec) for spec in DEFAULT_STAGES]
            db.add_all(stages)
            db.flush()
        stage_map = {s.name: s for s in stages}

        # 7. Deals — keyed by name; skipped when the tenant's stages don't include it.
        for idx, (deal_name, stage_name, value, prob) in enumerate(DEMO_DEALS):
            stage = stage_map.get(stage_name)
            if not stage:
                continue
            contact: Optional[ContactDetails] = contacts[idx % len(contacts)] if contacts else None
            _deal, created = _get_or_create(
                db, Deal,
                {"tenant_id": tenant_id, "name": deal_name},
                lambda deal_name=deal_name, stage=stage, value=value, prob=prob, contact=contact: Deal(
                    tenant_id=tenant_id,
                    name=deal_name,
                    stage_id=stage.stage_id,
                    contact_id=contact.contact_id if contact else None,
                    value=value,
                    probability=prob,
                ),
            )
            result["deals"] += int(created)

        db.commit()

        if any(result.values()):
            logger.info("Demo data seeded successfully", tenant_id=tenant_id, **result)

    except Exception as e:
        logger.error("Failed to seed demo data", tenant_id=tenant_id, error=str(e))
        db.rollback()
        result = {k: 0 for k in result}

    return result
