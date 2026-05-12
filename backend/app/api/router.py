"""API router configuration."""
from fastapi import APIRouter
from app.api.endpoints import (
    auth, users, leads, clients, contacts,
    validation, outreach, settings, pipelines, dashboard, mailboxes, warmup,
    templates, audit, backups,
    campaigns, inbox, webhooks, deals, copilot, integrations, automation,
    tracking_domains, lead_search, saved_searches, analytics,
    icp_wizard, sequence_generator, crm_sync, deal_tasks, spam_check,
    admin_tenants, billing, activity_log, onboarding,
    reply_macros, notifications, calendar, credits, goals, visitor_tracking,
    sms, objections, dfy, email_preview, deliverability,
    outreach_roles, reports, lob,
)

api_router = APIRouter()

# Include all endpoint routers
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(leads.router)
api_router.include_router(clients.router)
api_router.include_router(contacts.router)
api_router.include_router(validation.router)
api_router.include_router(outreach.router)
api_router.include_router(settings.router)
api_router.include_router(pipelines.router)
api_router.include_router(dashboard.router)
api_router.include_router(mailboxes.router)
api_router.include_router(warmup.router)
api_router.include_router(templates.router)
api_router.include_router(audit.router)
api_router.include_router(backups.router)
api_router.include_router(campaigns.router)
api_router.include_router(inbox.router)
api_router.include_router(webhooks.router)
api_router.include_router(deals.router)
api_router.include_router(copilot.router)
api_router.include_router(integrations.router)
api_router.include_router(automation.router)
# Phase 1-5: Beat Instantly.ai endpoints
api_router.include_router(tracking_domains.router)
api_router.include_router(lead_search.router)
api_router.include_router(saved_searches.router)
api_router.include_router(analytics.router)
api_router.include_router(icp_wizard.router)
api_router.include_router(sequence_generator.router)
api_router.include_router(crm_sync.router)
api_router.include_router(deal_tasks.router)
api_router.include_router(spam_check.router)
api_router.include_router(admin_tenants.router)
api_router.include_router(billing.router)
api_router.include_router(activity_log.router)
api_router.include_router(onboarding.router)
# Phase 1 Quick Wins
api_router.include_router(reply_macros.router)
api_router.include_router(notifications.router)
api_router.include_router(calendar.router)
api_router.include_router(credits.router)
api_router.include_router(goals.router)
api_router.include_router(visitor_tracking.router)
# Phase 2-4 endpoints
api_router.include_router(sms.router)
api_router.include_router(objections.router)
api_router.include_router(dfy.router)
# Email Preview & Approve
api_router.include_router(email_preview.router)
# Deliverability Intelligence
api_router.include_router(deliverability.router)
# Outreach Roles
api_router.include_router(outreach_roles.router)
# Reports
api_router.include_router(reports.router)
# Lines of Business
api_router.include_router(lob.router)
