"""Database query helper utilities."""
from sqlalchemy.orm import Session, Query


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
