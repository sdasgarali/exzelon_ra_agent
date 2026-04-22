"""Create a test campaign with lead + 3 contacts for email preview testing."""
from datetime import datetime, timedelta
from app.db.base import SessionLocal
from app.db.models.lead import LeadDetails
from app.db.models.contact import ContactDetails
from app.db.models.campaign import Campaign, SequenceStep, CampaignContact, CampaignStatus, StepType


def main():
    db = SessionLocal()
    try:
        tenant_id = 1

        # --- 1. Create or find test lead ---
        lead = db.query(LeadDetails).filter(
            LeadDetails.client_name == "TestCorp AI Preview",
            LeadDetails.tenant_id == tenant_id,
        ).first()
        if not lead:
            lead = LeadDetails(
                tenant_id=tenant_id,
                client_name="TestCorp AI Preview",
                job_title="Office Manager",
                state="Texas",
                source="mock",
                external_job_id="test-ai-preview-001",
            )
            db.add(lead)
            db.flush()
            print(f"Created lead: ID={lead.lead_id}, company=TestCorp AI Preview")
        else:
            print(f"Found existing lead: ID={lead.lead_id}")

        # --- 2. Create or find 3 test contacts ---
        contacts_data = [
            {"first_name": "Ali", "last_name": "Infy", "email": "ali.infy@gmail.com", "title": "CEO"},
            {"first_name": "Ali", "last_name": "Medeoan", "email": "ali@medeoan.com", "title": "CTO"},
            {"first_name": "Ali", "last_name": "AITechs", "email": "ali.aitechs@gmail.com", "title": "Director of Operations"},
        ]
        contacts = []
        for cd in contacts_data:
            c = db.query(ContactDetails).filter(
                ContactDetails.email == cd["email"],
                ContactDetails.tenant_id == tenant_id,
            ).first()
            if not c:
                c = ContactDetails(
                    tenant_id=tenant_id,
                    client_name="TestCorp AI Preview",
                    first_name=cd["first_name"],
                    last_name=cd["last_name"],
                    email=cd["email"],
                    title=cd["title"],
                    lead_id=lead.lead_id,
                    source="mock",
                    validation_status="valid",
                    priority_level="p1_job_poster",
                )
                db.add(c)
                db.flush()
                print(f"Created contact: ID={c.contact_id}, {cd['email']}")
            else:
                # Ensure validation status is valid
                if c.validation_status != "valid":
                    c.validation_status = "valid"
                print(f"Found existing contact: ID={c.contact_id}, {cd['email']}")
            contacts.append(c)

        # --- 3. Create email validation records ---
        from sqlalchemy import text
        for c in contacts:
            existing = db.execute(text(
                "SELECT 1 FROM email_validation_results WHERE email = :email LIMIT 1"
            ), {"email": c.email}).first()
            if not existing:
                db.execute(text(
                    "INSERT INTO email_validation_results (tenant_id, email, provider, status, validated_at, created_at, updated_at, is_archived) "
                    "VALUES (:tid, :email, 'manual', 'valid', NOW(), NOW(), NOW(), 0)"
                ), {"tid": tenant_id, "email": c.email})
                print(f"Created validation record for {c.email}")

        # --- 4. Create test campaign with preview_mode ON ---
        campaign = db.query(Campaign).filter(
            Campaign.name == "AI Preview Test Campaign",
            Campaign.tenant_id == tenant_id,
        ).first()
        if not campaign:
            campaign = Campaign(
                tenant_id=tenant_id,
                name="AI Preview Test Campaign",
                description="Test campaign to verify email preview + AI personalization before sending.",
                status=CampaignStatus.ACTIVE,
                preview_mode=True,
                created_by=1,
                mailbox_ids_json='[2, 12, 13, 14]',
                total_contacts=3,
            )
            db.add(campaign)
            db.flush()
            print(f"Created campaign: ID={campaign.campaign_id}, preview_mode=True")
        else:
            campaign.preview_mode = True
            campaign.status = CampaignStatus.ACTIVE
            print(f"Found existing campaign: ID={campaign.campaign_id}, set preview_mode=True")

        # --- 5. Create sequence step (email) ---
        step = db.query(SequenceStep).filter(
            SequenceStep.campaign_id == campaign.campaign_id,
            SequenceStep.step_order == 0,
        ).first()
        if not step:
            step = SequenceStep(
                campaign_id=campaign.campaign_id,
                step_order=0,
                step_type=StepType.EMAIL,
                subject="Quick question about {{company_name}}, {{contact_first_name}}",
                body_html=(
                    "<p>Hi {{contact_first_name}},</p>"
                    "<p>I came across {{company_name}} and noticed you're the {{contact_title}} there. "
                    "We help companies like yours find top talent faster -- especially for hard-to-fill "
                    "{{job_title}} roles in {{job_location}}.</p>"
                    "<p>Would it make sense to connect for a quick 10-minute call this week?</p>"
                    "<p>Best,<br/>{{sender_first_name}}</p>"
                ),
                body_text=(
                    "Hi {{contact_first_name}},\n\n"
                    "I came across {{company_name}} and noticed you're the {{contact_title}} there. "
                    "We help companies like yours find top talent faster -- especially for hard-to-fill "
                    "{{job_title}} roles in {{job_location}}.\n\n"
                    "Would it make sense to connect for a quick 10-minute call this week?\n\n"
                    "Best,\n{{sender_first_name}}"
                ),
                delay_days=0,
                delay_hours=0,
            )
            db.add(step)
            db.flush()
            print(f"Created step: ID={step.step_id}, order=0, type=email")
        else:
            print(f"Found existing step: ID={step.step_id}")

        # --- 6. Enroll contacts in the campaign ---
        for c in contacts:
            existing_cc = db.query(CampaignContact).filter(
                CampaignContact.campaign_id == campaign.campaign_id,
                CampaignContact.contact_id == c.contact_id,
            ).first()
            if not existing_cc:
                cc = CampaignContact(
                    campaign_id=campaign.campaign_id,
                    contact_id=c.contact_id,
                    lead_id=lead.lead_id,
                    current_step=0,
                    next_send_at=datetime.utcnow() + timedelta(minutes=5),
                )
                db.add(cc)
                print(f"Enrolled contact {c.email} in campaign")
            else:
                print(f"Contact {c.email} already enrolled")

        db.commit()
        print(f"\n=== DONE ===")
        print(f"Campaign ID: {campaign.campaign_id}")
        print(f"Lead ID: {lead.lead_id}")
        print(f"Contact IDs: {[c.contact_id for c in contacts]}")
        print(f"Step ID: {step.step_id}")
        print(f"Preview Mode: ON")
        print(f"\nMailboxes assigned: [2, 12, 13, 14] (David, Dustin, Sophia, Elsa @exzelon.com)")
        print(f"\nYou can now:")
        print(f"  1. Open http://localhost:3000/dashboard/campaigns")
        print(f"  2. Click the campaign -> Steps tab -> click AI Preview (sparkles) button")
        print(f"  3. Or use Generate Previews button to create drafts in preview mode")

    except Exception as e:
        db.rollback()
        print(f"ERROR: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
