"""Demo data seeder for new starter-plan tenants."""
import structlog
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from app.db.models.tenant import Tenant, TenantPlan
from app.db.models.lead import LeadDetails, LeadStatus
from app.db.models.contact import ContactDetails
from app.db.models.client import ClientInfo
from app.db.models.campaign import Campaign, CampaignStatus
from app.db.models.email_template import EmailTemplate, TemplateStatus
from app.db.models.deal import Deal, DealStage

logger = structlog.get_logger()


def seed_demo_data(tenant_id: int, db: Session) -> dict:
    """Seed demo data for a new tenant. Called after email verification.

    Seeds: 10 clients, 25 leads, 15 contacts, 2 templates, 1 campaign, 5 deals.
    Returns: dict with counts of seeded items.
    """
    result = {"clients": 0, "leads": 0, "contacts": 0, "templates": 0, "campaigns": 0, "deals": 0}

    try:
        # Check if already seeded (prevent double-seed)
        existing_leads = db.query(LeadDetails).filter(LeadDetails.tenant_id == tenant_id).count()
        if existing_leads > 0:
            logger.info("Demo data already exists, skipping", tenant_id=tenant_id)
            return result

        # 1. Seed clients
        demo_companies = [
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

        clients = []
        for name, industry, state, city in demo_companies:
            client = ClientInfo(
                tenant_id=tenant_id,
                client_name=name,
                industry=industry,
                location_state=state,
                employee_count=50 + (len(name) * 10),  # pseudo-random
            )
            db.add(client)
            clients.append(client)
        db.flush()
        result["clients"] = len(clients)

        # 2. Seed leads (job postings)
        demo_titles = [
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

        leads = []
        for i, title in enumerate(demo_titles):
            client = clients[i % len(clients)]
            lead = LeadDetails(
                tenant_id=tenant_id,
                job_title=title,
                client_name=client.client_name,
                state=client.location_state,
                city=demo_companies[i % len(demo_companies)][3],
                source="demo",
                lead_status=LeadStatus.OPEN,
            )
            db.add(lead)
            leads.append(lead)
        db.flush()
        result["leads"] = len(leads)

        # 3. Seed contacts
        demo_contacts = [
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

        contacts = []
        for first, last, title, email, client_idx in demo_contacts:
            client = clients[client_idx]
            contact = ContactDetails(
                tenant_id=tenant_id,
                first_name=first,
                last_name=last,
                title=title,
                email=email,
                client_name=client.client_name,
                source="demo",
            )
            db.add(contact)
            contacts.append(contact)
        db.flush()
        result["contacts"] = len(contacts)

        # 4. Seed email templates
        templates = [
            EmailTemplate(
                tenant_id=tenant_id,
                name="[Demo] Introduction Template",
                subject="Quick question about {{title}}",
                body_html="Hi {{first_name}},<br><br>I noticed {{company}} is hiring for a {{title}} role. I help companies find top talent faster.<br><br>Would you be open to a quick 15-minute call this week?<br><br>Best,<br>{{sender_name}}",
                body_text="Hi {{first_name}},\n\nI noticed {{company}} is hiring for a {{title}} role. I help companies find top talent faster.\n\nWould you be open to a quick 15-minute call this week?\n\nBest,\n{{sender_name}}",
                status=TemplateStatus.ACTIVE,
            ),
            EmailTemplate(
                tenant_id=tenant_id,
                name="[Demo] Follow-up Template",
                subject="Re: {{title}} position",
                body_html="Hi {{first_name}},<br><br>Just following up on my previous email about the {{title}} opportunity at {{company}}.<br><br>I have several qualified candidates who could be a great fit. Would you have 10 minutes to discuss?<br><br>Best regards,<br>{{sender_name}}",
                body_text="Hi {{first_name}},\n\nJust following up on my previous email about the {{title}} opportunity at {{company}}.\n\nI have several qualified candidates who could be a great fit. Would you have 10 minutes to discuss?\n\nBest regards,\n{{sender_name}}",
                status=TemplateStatus.INACTIVE,
            ),
        ]
        for t in templates:
            db.add(t)
        db.flush()
        result["templates"] = len(templates)

        # 5. Seed a demo campaign
        campaign = Campaign(
            tenant_id=tenant_id,
            name="[Demo] Outreach Campaign",
            description="Sample outreach campaign targeting hiring managers",
            status=CampaignStatus.DRAFT,
        )
        db.add(campaign)
        db.flush()
        result["campaigns"] = 1

        # 6. Seed deals (if stages exist)
        stages = db.query(DealStage).filter(DealStage.tenant_id == tenant_id).all()
        if not stages:
            # Seed default stages for this tenant
            default_stages = [
                DealStage(tenant_id=tenant_id, name="New Lead", stage_order=1, color="#3b82f6"),
                DealStage(tenant_id=tenant_id, name="Contacted", stage_order=2, color="#8b5cf6"),
                DealStage(tenant_id=tenant_id, name="Qualified", stage_order=3, color="#06b6d4"),
                DealStage(tenant_id=tenant_id, name="Proposal", stage_order=4, color="#f59e0b"),
                DealStage(tenant_id=tenant_id, name="Negotiation", stage_order=5, color="#ef4444"),
                DealStage(tenant_id=tenant_id, name="Won", stage_order=6, color="#22c55e", is_won=True),
                DealStage(tenant_id=tenant_id, name="Lost", stage_order=7, color="#6b7280", is_lost=True),
            ]
            for s in default_stages:
                db.add(s)
            db.flush()
            stages = default_stages

        stage_map = {s.name: s for s in stages}

        demo_deals = [
            ("TechCorp Solutions -- Sarah Johnson", "New Lead", 15000, 20),
            ("MediHealth Inc -- Emily Rodriguez", "Contacted", 25000, 40),
            ("GreenEnergy Co -- James Williams", "Qualified", 50000, 60),
            ("FinanceFirst LLC -- Lisa Thompson", "Proposal", 35000, 70),
            ("RetailPro Group -- Amanda Brown", "Negotiation", 40000, 80),
        ]

        deal_count = 0
        for deal_name, stage_name, value, prob in demo_deals:
            stage = stage_map.get(stage_name)
            if stage:
                contact_idx = deal_count % len(contacts)
                deal = Deal(
                    tenant_id=tenant_id,
                    name=deal_name,
                    stage_id=stage.stage_id,
                    contact_id=contacts[contact_idx].contact_id if contacts else None,
                    value=value,
                    probability=prob,
                )
                db.add(deal)
                deal_count += 1
        db.flush()
        result["deals"] = deal_count

        db.commit()

        logger.info("Demo data seeded successfully",
                     tenant_id=tenant_id,
                     **result)

    except Exception as e:
        logger.error("Failed to seed demo data", tenant_id=tenant_id, error=str(e))
        db.rollback()

    return result
