"""AI objection handling library with system-provided templates."""
import structlog
from sqlalchemy.orm import Session

from app.db.models.objection_template import ObjectionTemplate
from app.db.query_helpers import tenant_filter

logger = structlog.get_logger()

SYSTEM_OBJECTIONS = [
    {
        "type": "budget",
        "text": "It's too expensive / We don't have the budget",
        "response": (
            "I completely understand budget is a key consideration. Many of our "
            "clients initially had similar concerns but found the ROI justified the "
            "investment within the first quarter. Would you be open to a quick call "
            "where I can share some specific numbers from companies in your industry?"
        ),
    },
    {
        "type": "timing",
        "text": "Now is not a good time / We're too busy",
        "response": (
            "I appreciate you being upfront about timing. Rather than taking up "
            "your time now, would it make sense to schedule a brief 10-minute call "
            "next month when things settle down? I can send a calendar invite for "
            "a date that works better."
        ),
    },
    {
        "type": "authority",
        "text": "I'm not the right person / I need to check with my team",
        "response": (
            "That makes total sense -- these decisions usually involve multiple "
            "stakeholders. Would it be helpful if I put together a brief one-pager "
            "that you could share with the team? I can also join a call with the "
            "relevant decision-makers if that would be easier."
        ),
    },
    {
        "type": "need",
        "text": "We already have a solution / We don't need this",
        "response": (
            "That's great that you have something in place. Out of curiosity, how "
            "satisfied are you with the results you're currently getting? Many "
            "teams we work with switched because they found our approach gave them "
            "2-3x better results. I'd love to share what makes our approach different."
        ),
    },
    {
        "type": "competitor",
        "text": "We're using [Competitor] / We're evaluating other options",
        "response": (
            "Good to know! [Competitor] is a solid option. What we hear from teams "
            "who've evaluated both is that our platform offers [specific "
            "differentiator]. Would it be helpful to see a side-by-side comparison? "
            "It might help inform your evaluation."
        ),
    },
    {
        "type": "trust",
        "text": "I've never heard of you / How do I know this works?",
        "response": (
            "That's a fair question. We work with [X number] companies in your "
            "industry, including [notable reference if available]. I'd be happy to "
            "connect you with a current client who can share their experience "
            "firsthand. Would that be helpful?"
        ),
    },
    {
        "type": "followup",
        "text": "Send me more information / I'll review and get back to you",
        "response": (
            "Absolutely! I'll send over a brief overview tailored to your "
            "industry. Just so I can make it relevant -- what specific challenges "
            "are you looking to solve? That way I can highlight the most applicable "
            "features."
        ),
    },
]


def seed_system_objections(db: Session, tenant_id: int) -> dict:
    """Seed system-provided objection templates for a tenant.

    Args:
        db: Database session.
        tenant_id: Tenant to seed for.

    Returns:
        Dict with number of templates seeded.
    """
    existing = db.query(ObjectionTemplate).filter(
        ObjectionTemplate.tenant_id == tenant_id,
        ObjectionTemplate.is_system == True,
    ).count()

    if existing > 0:
        return {"seeded": 0, "message": "Already seeded"}

    for obj in SYSTEM_OBJECTIONS:
        template = ObjectionTemplate(
            tenant_id=tenant_id,
            objection_type=obj["type"],
            objection_text=obj["text"],
            response_text=obj["response"],
            is_system=True,
            effectiveness_score=70,
        )
        db.add(template)

    db.commit()
    logger.info("system_objections_seeded", tenant_id=tenant_id, count=len(SYSTEM_OBJECTIONS))
    return {"seeded": len(SYSTEM_OBJECTIONS)}


def get_objection_response(
    db: Session,
    tenant_id: int,
    objection_type: str,
) -> dict:
    """Get the best response for an objection type.

    Args:
        db: Database session.
        tenant_id: Tenant scope.
        objection_type: Category of objection (budget/timing/authority/etc).

    Returns:
        Dict with response text and metadata, or None.
    """
    template_q = db.query(ObjectionTemplate).filter(
        ObjectionTemplate.objection_type == objection_type,
        ObjectionTemplate.is_archived == False,
    )
    template_q = tenant_filter(template_q, ObjectionTemplate, tenant_id)
    template = template_q.order_by(
        ObjectionTemplate.effectiveness_score.desc()
    ).first()

    if not template:
        return None

    return {
        "template_id": template.template_id,
        "objection_type": template.objection_type,
        "response_text": template.response_text,
        "effectiveness_score": template.effectiveness_score,
        "is_system": template.is_system,
    }
