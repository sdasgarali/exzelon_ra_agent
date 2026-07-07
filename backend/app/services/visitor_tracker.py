"""Website visitor tracking -- JS pixel + reverse IP lookup."""
import structlog
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.models.visitor import VisitorEvent

logger = structlog.get_logger()

TRACKING_PIXEL_JS = """
(function() {
  var d = document, s = d.createElement('script');
  var endpoint = '%ENDPOINT%';
  var tid = '%TENANT_ID%';

  function track(event, data) {
    var img = new Image();
    img.src = endpoint + '/track?t=' + tid + '&e=' + event + '&u=' + encodeURIComponent(location.href) + '&r=' + encodeURIComponent(document.referrer) + '&ts=' + Date.now();
  }

  track('pageview');

  // Track time on page
  var start = Date.now();
  window.addEventListener('beforeunload', function() {
    track('leave', {duration: Date.now() - start});
  });
})();
"""


def record_visit(
    db: Session,
    tenant_id: int,
    page_url: str,
    referrer: str = None,
    ip_address: str = None,
    user_agent: str = None,
    visitor_id: str = None,
) -> dict:
    """Record a website visitor event.

    Args:
        db: Database session.
        tenant_id: Tenant scope.
        page_url: URL visited.
        referrer: Referring URL.
        ip_address: Client IP address.
        user_agent: Browser user agent.
        visitor_id: Cookie-based visitor identifier.

    Returns:
        Dict confirming the tracking event.
    """
    # Try to identify company from IP (simplified -- placeholder)
    company_name = None
    company_domain = None

    event = VisitorEvent(
        visitor_id=visitor_id or f"anon_{datetime.utcnow().timestamp()}",
        page_url=page_url,
        referrer=referrer,
        ip_address=ip_address,
        user_agent=user_agent,
        company_name=company_name,
        company_domain=company_domain,
        visited_at=datetime.utcnow(),
    )
    db.add(event)
    db.commit()
    return {"tracked": True}


def get_visitor_stats(db: Session, tenant_id: int) -> dict:
    """Get visitor statistics for the last 30 days.

    Args:
        db: Database session.
        tenant_id: Tenant scope.

    Returns:
        Dict with total visits, unique sessions, and unique companies.
    """
    cutoff = datetime.utcnow() - timedelta(days=30)

    base_q = db.query(VisitorEvent).filter(
        VisitorEvent.is_archived == False,
        VisitorEvent.visited_at >= cutoff,
    )

    total = base_q.count()

    unique_visitors = db.query(
        func.count(func.distinct(VisitorEvent.visitor_id))
    ).filter(
        VisitorEvent.is_archived == False,
        VisitorEvent.visited_at >= cutoff,
    ).scalar() or 0

    unique_companies = db.query(
        func.count(func.distinct(VisitorEvent.company_domain))
    ).filter(
        VisitorEvent.is_archived == False,
        VisitorEvent.company_domain.isnot(None),
        VisitorEvent.visited_at >= cutoff,
    ).scalar() or 0

    return {
        "total_visits": total,
        "unique_visitors": unique_visitors,
        "unique_companies": unique_companies,
        "period_days": 30,
    }
