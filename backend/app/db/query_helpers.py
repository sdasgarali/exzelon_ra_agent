"""Database query helper utilities."""
from sqlalchemy.orm import Session, Query
from app.core.tenant_context import get_current_tenant_id, get_is_global_super_admin


def active_query(db: Session, model, show_archived: bool = False) -> Query:
    """Create a query filtered by archive status.

    Args:
        db: Database session
        model: SQLAlchemy model class (must have is_archived column)
        show_archived: If True, show only archived records.
                       If False, show only non-archived records.

    Returns:
        Filtered query object
    """
    query = db.query(model)
    if show_archived:
        query = query.filter(model.is_archived == True)
    else:
        query = query.filter(model.is_archived == False)
    return query


def tenant_query(db: Session, model, show_archived: bool | None = None) -> Query:
    """Create a tenant-scoped query.

    Automatically applies tenant_id filter based on the current request context:
    - Super Admin with no X-Tenant-Id header: no tenant filter (sees all)
    - Super Admin with X-Tenant-Id header: filters to that tenant
    - Regular user: filters to their tenant_id

    Args:
        db: Database session
        model: SQLAlchemy model class
        show_archived: If True, show only archived. If False, only non-archived.
                       If None, don't filter by archive status.

    Returns:
        Filtered query object
    """
    query = db.query(model)

    # Apply tenant filter
    tenant_id = get_current_tenant_id()
    is_gsa = get_is_global_super_admin()

    if not is_gsa or tenant_id is not None:
        # Non-GSA always filtered; GSA filtered only if explicit tenant set via header
        if tenant_id is not None and hasattr(model, "tenant_id"):
            query = query.filter(model.tenant_id == tenant_id)

    # Apply archive filter if requested
    if show_archived is not None and hasattr(model, "is_archived"):
        if show_archived:
            query = query.filter(model.is_archived == True)
        else:
            query = query.filter(model.is_archived == False)

    return query


def paginate(query: Query, page: int = 1, page_size: int = 50) -> dict:
    """Apply pagination to a query and return results with metadata.

    Args:
        query: SQLAlchemy query to paginate
        page: Page number (1-indexed)
        page_size: Number of items per page

    Returns:
        Dict with items, total, page, page_size, pages
    """
    total = query.count()
    offset = (page - 1) * page_size
    items = query.offset(offset).limit(page_size).all()
    pages = (total + page_size - 1) // page_size

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": pages,
    }
