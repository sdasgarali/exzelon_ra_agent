"""Seed test inbox data with realistic conversations."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from app.db.base import SessionLocal
from app.db.models.inbox_message import InboxMessage
from datetime import datetime, timedelta
import hashlib

db = SessionLocal()

count = db.query(InboxMessage).count()
print(f"Existing inbox messages: {count}")

if count > 0:
    print("Clearing existing inbox data for re-seed...")
    db.query(InboxMessage).delete()
    db.commit()

now = datetime.utcnow()

threads = [
    {
        "thread_id": hashlib.md5(b"thread-1").hexdigest()[:16],
        "contact_name": "Sarah Johnson",
        "from_email": "sarah.johnson@acmecorp.com",
        "to_email": "outreach@exzelon.com",
        "category": "interested",
        "sentiment": "positive",
        "messages": [
            {"direction": "sent", "subject": "Staffing Solutions for Acme Corp",
             "body": "Hi Sarah,\n\nI noticed Acme Corp is hiring for several IT positions. We specialize in connecting companies with top-tier talent.\n\nWould you be open to a quick call this week?\n\nBest regards,\nExzelon Team",
             "hours_ago": 48},
            {"direction": "received", "subject": "Re: Staffing Solutions for Acme Corp",
             "body": "Hi there,\n\nThanks for reaching out! We are indeed looking for qualified candidates. I would love to learn more about your services.\n\nCan we schedule a call for Thursday at 2pm EST?\n\nBest,\nSarah Johnson\nHR Director, Acme Corp",
             "hours_ago": 24},
            {"direction": "sent", "subject": "Re: Staffing Solutions for Acme Corp",
             "body": "Hi Sarah,\n\nThursday at 2pm EST works perfectly. I will send a calendar invite shortly.\n\nLooking forward to speaking with you!\n\nBest,\nExzelon Team",
             "hours_ago": 23},
        ],
    },
    {
        "thread_id": hashlib.md5(b"thread-2").hexdigest()[:16],
        "contact_name": "Michael Chen",
        "from_email": "mchen@globaltech.io",
        "to_email": "outreach@exzelon.com",
        "category": "not_interested",
        "sentiment": "negative",
        "messages": [
            {"direction": "sent", "subject": "Partnership Opportunity - GlobalTech",
             "body": "Hi Michael,\n\nI wanted to introduce Exzelon RA and how we can help GlobalTech fill your open engineering positions faster.\n\nWould you be interested in learning more?\n\nBest,\nExzelon Team",
             "hours_ago": 72},
            {"direction": "received", "subject": "Re: Partnership Opportunity - GlobalTech",
             "body": "Hi,\n\nThanks but we already have an in-house recruiting team and are not looking for external help at this time.\n\nPlease remove me from your mailing list.\n\nRegards,\nMichael Chen\nVP Engineering",
             "hours_ago": 36},
        ],
    },
    {
        "thread_id": hashlib.md5(b"thread-3").hexdigest()[:16],
        "contact_name": "Emily Rodriguez",
        "from_email": "emily.r@brightpath.com",
        "to_email": "outreach@exzelon.com",
        "category": "ooo",
        "sentiment": "neutral",
        "messages": [
            {"direction": "sent", "subject": "Talent Acquisition for BrightPath",
             "body": "Hi Emily,\n\nI see BrightPath is expanding rapidly. We would love to help you find the right people.\n\nCan we connect this week?\n\nBest,\nExzelon Team",
             "hours_ago": 30},
            {"direction": "received", "subject": "Out of Office: Re: Talent Acquisition for BrightPath",
             "body": "Thank you for your email. I am currently out of the office until March 15th with limited access to email.\n\nFor urgent matters, please contact my colleague James Wilson at jwilson@brightpath.com.\n\nI will respond to your message upon my return.\n\nBest regards,\nEmily Rodriguez",
             "hours_ago": 29},
        ],
    },
    {
        "thread_id": hashlib.md5(b"thread-4").hexdigest()[:16],
        "contact_name": "David Park",
        "from_email": "dpark@innovateinc.com",
        "to_email": "outreach@exzelon.com",
        "category": "question",
        "sentiment": "neutral",
        "messages": [
            {"direction": "sent", "subject": "Recruiting Services - Innovate Inc",
             "body": "Hi David,\n\nI noticed Innovate Inc has multiple open positions. We can help you fill them with qualified candidates.\n\nWould you like to discuss?\n\nBest,\nExzelon Team",
             "hours_ago": 60},
            {"direction": "received", "subject": "Re: Recruiting Services - Innovate Inc",
             "body": "Hi,\n\nInteresting timing. We are struggling to find senior developers.\n\nA few questions:\n1. What industries do you specialize in?\n2. What is your typical placement fee?\n3. Do you offer any guarantees on placements?\n\nThanks,\nDavid Park\nCTO, Innovate Inc",
             "hours_ago": 12},
        ],
    },
    {
        "thread_id": hashlib.md5(b"thread-5").hexdigest()[:16],
        "contact_name": "Lisa Thompson",
        "from_email": "lisa.t@nexusgroup.co",
        "to_email": "outreach@exzelon.com",
        "category": "referral",
        "sentiment": "positive",
        "messages": [
            {"direction": "sent", "subject": "Staffing Solutions for Nexus Group",
             "body": "Hi Lisa,\n\nI wanted to reach out about how Exzelon RA can support Nexus Group hiring goals.\n\nBest,\nExzelon Team",
             "hours_ago": 96},
            {"direction": "received", "subject": "Re: Staffing Solutions for Nexus Group",
             "body": "Hi,\n\nI appreciate the outreach. I am not the right person for this, but I think you should talk to our Head of HR, Karen Mitchell.\n\nHer email is kmitchell@nexusgroup.co. Please tell her I referred you.\n\nBest,\nLisa Thompson\nOperations Director",
             "hours_ago": 48},
        ],
    },
    {
        "thread_id": hashlib.md5(b"thread-6").hexdigest()[:16],
        "contact_name": "Robert Williams",
        "from_email": "rwilliams@techforge.dev",
        "to_email": "outreach@exzelon.com",
        "category": "do_not_contact",
        "sentiment": "negative",
        "messages": [
            {"direction": "sent", "subject": "Open Positions at TechForge",
             "body": "Hi Robert,\n\nI see TechForge is hiring for backend engineers. We can help!\n\nBest,\nExzelon Team",
             "hours_ago": 120},
            {"direction": "received", "subject": "Re: Open Positions at TechForge",
             "body": "STOP EMAILING ME. I have asked multiple times to be removed from your list. If I receive another email I will report this as spam.\n\nDo NOT contact me again.",
             "hours_ago": 100},
        ],
    },
    {
        "thread_id": hashlib.md5(b"thread-7").hexdigest()[:16],
        "contact_name": "Amanda Foster",
        "from_email": "afoster@cloudnine.io",
        "to_email": "outreach@exzelon.com",
        "category": "interested",
        "sentiment": "positive",
        "messages": [
            {"direction": "sent", "subject": "Cloud Nine - Talent Solutions",
             "body": "Hi Amanda,\n\nCloud Nine is growing fast - congrats! We help companies like yours find top engineering talent.\n\nInterested in learning more?\n\nBest,\nExzelon Team",
             "hours_ago": 8},
            {"direction": "received", "subject": "Re: Cloud Nine - Talent Solutions",
             "body": "Hi!\n\nYes, absolutely! We are desperately looking for DevOps engineers and full-stack developers. Our internal recruiting team is overwhelmed.\n\nCan you send me your pricing and a brief about your process?\n\nThanks!\nAmanda Foster\nVP People, Cloud Nine",
             "hours_ago": 2},
        ],
    },
    {
        "thread_id": hashlib.md5(b"thread-8").hexdigest()[:16],
        "contact_name": "James Miller",
        "from_email": "jmiller@datapulse.com",
        "to_email": "outreach@exzelon.com",
        "category": None,
        "sentiment": None,
        "messages": [
            {"direction": "sent", "subject": "DataPulse Hiring Needs",
             "body": "Hi James,\n\nI see DataPulse has open data science roles. We can help connect you with qualified candidates.\n\nWant to chat?\n\nBest,\nExzelon Team",
             "hours_ago": 4},
        ],
    },
    {
        "thread_id": hashlib.md5(b"thread-9").hexdigest()[:16],
        "contact_name": "Patricia Lee",
        "from_email": "patricia@quantumleap.co",
        "to_email": "outreach@exzelon.com",
        "category": "question",
        "sentiment": "positive",
        "messages": [
            {"direction": "sent", "subject": "Recruitment Support for Quantum Leap",
             "body": "Hi Patricia,\n\nQuantum Leap is making waves in quantum computing. Need help building your team?\n\nBest,\nExzelon Team",
             "hours_ago": 16},
            {"direction": "received", "subject": "Re: Recruitment Support for Quantum Leap",
             "body": "Hello,\n\nThis is interesting. We have been having trouble finding quantum computing specialists.\n\nDo you have access to candidates with quantum computing experience? What is your typical time-to-fill for niche roles?\n\nPatricia Lee\nChief People Officer",
             "hours_ago": 6},
        ],
    },
    {
        "thread_id": hashlib.md5(b"thread-10").hexdigest()[:16],
        "contact_name": "Kevin Brown",
        "from_email": "kbrown@startuphub.vc",
        "to_email": "outreach@exzelon.com",
        "category": "other",
        "sentiment": "neutral",
        "messages": [
            {"direction": "sent", "subject": "Talent Solutions for StartupHub Portfolio",
             "body": "Hi Kevin,\n\nAs a VC, you likely have portfolio companies that need talent. We can help!\n\nBest,\nExzelon Team",
             "hours_ago": 40},
            {"direction": "received", "subject": "Re: Talent Solutions for StartupHub Portfolio",
             "body": "Hi,\n\nThanks for reaching out. Let me loop in a few of our portfolio company founders who might benefit from this.\n\nI will get back to you next week.\n\nKevin Brown\nPartner, StartupHub VC",
             "hours_ago": 20},
        ],
    },
]

msg_id = 1
for t in threads:
    for m in t["messages"]:
        is_received = m["direction"] == "received"
        inbox_msg = InboxMessage(
            thread_id=t["thread_id"],
            contact_id=None,
            mailbox_id=None,
            outreach_event_id=None,
            campaign_id=None,
            direction=m["direction"],
            from_email=t["from_email"] if is_received else t["to_email"],
            to_email=t["to_email"] if is_received else t["from_email"],
            subject=m["subject"],
            body_html=None,
            body_text=m["body"],
            raw_message_id=f"msg-{msg_id}@exzelon.com",
            in_reply_to=None,
            received_at=now - timedelta(hours=m["hours_ago"]),
            is_read=(m["hours_ago"] > 10),
            category=t["category"] if is_received else None,
            sentiment=t["sentiment"] if is_received else None,
        )
        db.add(inbox_msg)
        msg_id += 1

db.commit()
final_count = db.query(InboxMessage).count()
print(f"Seeded {final_count} inbox messages across {len(threads)} threads")
db.close()
