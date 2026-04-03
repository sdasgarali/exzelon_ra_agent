"""Lead round-robin assignment service."""
import structlog
from sqlalchemy.orm import Session

from app.db.models.user import User
from app.db.models.lead import LeadDetails
from app.db.models.campaign import Campaign
from app.db.query_helpers import tenant_filter

logger = structlog.get_logger()


def assign_leads_round_robin(
    db: Session,
    lead_ids: list,
    campaign_id: int,
    tenant_id: int,
) -> dict:
    """Assign leads to team members in round-robin fashion.

    Args:
        db: Database session.
        lead_ids: List of lead IDs to assign.
        campaign_id: Campaign to associate the assignment with.
        tenant_id: Tenant scope.

    Returns:
        Dict with assignment results.
    """
    campaign = db.query(Campaign).filter(
        Campaign.campaign_id == campaign_id
    ).first()
    if not campaign:
        return {"error": "Campaign not found"}

    # Get active operators/admins in tenant
    users_q = db.query(User).filter(
        User.is_active == True,
        User.is_archived == False,
    )
    users_q = tenant_filter(users_q, User, tenant_id)
    team_members = users_q.all()

    if not team_members:
        return {"error": "No team members available"}

    assignments = []
    for i, lead_id in enumerate(lead_ids):
        user = team_members[i % len(team_members)]
        lead_q = db.query(LeadDetails).filter(LeadDetails.lead_id == lead_id)
        lead_q = tenant_filter(lead_q, LeadDetails, tenant_id)
        lead = lead_q.first()
        if lead:
            lead.assigned_to = user.user_id
            assignments.append({
                "lead_id": lead_id,
                "assigned_to": user.user_id,
                "user_name": user.full_name or user.email,
            })

    db.commit()
    logger.info(
        "leads_assigned_round_robin",
        count=len(assignments),
        campaign_id=campaign_id,
        tenant_id=tenant_id,
    )
    return {"assigned": len(assignments), "assignments": assignments}
