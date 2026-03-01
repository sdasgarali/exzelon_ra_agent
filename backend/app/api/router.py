"""API router configuration."""
from fastapi import APIRouter
from app.api.endpoints import (
    auth, users, leads, clients, contacts,
    validation, outreach, settings, pipelines, dashboard, mailboxes, warmup,
    templates, audit
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
