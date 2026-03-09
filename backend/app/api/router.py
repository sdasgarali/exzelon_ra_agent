"""API router configuration."""
from fastapi import APIRouter
from app.api.endpoints import (
    auth, users, leads, clients, contacts,
    validation, outreach, settings, pipelines, dashboard, mailboxes, warmup,
    templates, audit, backups,
    campaigns, inbox, webhooks, deals, copilot, integrations, automation,
    tracking_domains, lead_search, saved_searches, analytics,
    icp_wizard, sequence_generator, crm_sync, deal_tasks, spam_check,
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
