"""Tracking Domain CRUD API endpoints.

Allows users to configure custom tracking domains (e.g., track.company.com)
for email open/click tracking, improving deliverability by replacing the
app's default domain in tracking pixels and redirect links.
"""
import logging
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.api.deps.auth import get_current_user, require_role, get_current_tenant_id
from app.db.models.user import User, UserRole
from app.db.models.tracking_domain import TrackingDomain
from app.core.config import settings
from app.db.query_helpers import tenant_filter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tracking-domains", tags=["Tracking Domains"])


# ─── Pydantic Schemas ─────────────────────────────────────────────

class CreateTrackingDomain(BaseModel):
    domain_name: str = Field(
        ..., max_length=255, min_length=3,
        description="Custom tracking domain, e.g. track.company.com",
    )


class TrackingDomainResponse(BaseModel):
    domain_id: int
    domain_name: str
    is_verified: bool
    cname_target: Optional[str] = None
    is_default: bool
    mailbox_id: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class VerifyResult(BaseModel):
    domain_id: int
    domain_name: str
    is_verified: bool
    message: str
    cname_target: Optional[str] = None
    resolved_cname: Optional[str] = None


# ─── Helpers ───────────────────────────────────────────────────────

def _domain_to_dict(td: TrackingDomain) -> dict:
    """Convert a TrackingDomain ORM instance to a response dict."""
    return {
        "domain_id": td.domain_id,
        "domain_name": td.domain_name,
        "is_verified": td.is_verified,
        "cname_target": td.cname_target,
        "is_default": td.is_default,
        "mailbox_id": td.mailbox_id,
        "created_at": td.created_at.isoformat() if td.created_at else None,
        "updated_at": td.updated_at.isoformat() if td.updated_at else None,
    }


def _derive_cname_target() -> str:
    """Derive the CNAME target from the application's configured BASE_URL.

    If BASE_URL is set (e.g. https://ra.partnerwithus.tech), extracts the
    hostname. Otherwise falls back to the HOST config value.
    """
    base_url = settings.EFFECTIVE_BASE_URL
    try:
        parsed = urlparse(base_url)
        if parsed.hostname:
            return parsed.hostname
    except Exception:
        pass
    return settings.HOST


# ─── Endpoints ─────────────────────────────────────────────────────

@router.post("", summary="Create a tracking domain")
def create_tracking_domain(
    data: CreateTrackingDomain,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Create a new custom tracking domain (admin+ only).

    Auto-generates the CNAME target from the app's configured domain.
    The user must then create a DNS CNAME record pointing their custom
    domain to this target before verification will pass.
    """
    # Normalize: lowercase, strip whitespace
    domain_name = data.domain_name.strip().lower()

    # Check for duplicate (including archived, since domain_name has a unique constraint)
    dup_query = db.query(TrackingDomain).filter(
        TrackingDomain.domain_name == domain_name
    )
    dup_query = tenant_filter(dup_query, TrackingDomain, tenant_id)
    existing = dup_query.first()

    if existing and not existing.is_archived:
        raise HTTPException(status_code=409, detail="Tracking domain already exists")

    # If previously archived, re-activate it
    if existing and existing.is_archived:
        existing.is_archived = False
        existing.is_verified = False
        existing.cname_target = _derive_cname_target()
        existing.is_default = False
        db.commit()
        db.refresh(existing)
        logger.info("Re-activated archived tracking domain: %s", domain_name)
        return _domain_to_dict(existing)

    tracking_domain = TrackingDomain(
        domain_name=domain_name,
        cname_target=_derive_cname_target(),
        is_verified=False,
        is_default=False,
        tenant_id=tenant_id or 1,
    )
    db.add(tracking_domain)
    db.commit()
    db.refresh(tracking_domain)

    logger.info("Created tracking domain: %s (cname_target=%s)", domain_name, tracking_domain.cname_target)
    return _domain_to_dict(tracking_domain)


@router.get("", summary="List tracking domains")
def list_tracking_domains(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """List all non-archived tracking domains (operator+ role)."""
    q = db.query(TrackingDomain).filter(TrackingDomain.is_archived == False)
    q = tenant_filter(q, TrackingDomain, tenant_id)
    domains = q.order_by(TrackingDomain.domain_id).all()
    return [_domain_to_dict(td) for td in domains]


@router.post("/{domain_id}/verify", summary="Verify DNS CNAME record")
def verify_tracking_domain(
    domain_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Verify that the domain's DNS CNAME record points to the expected target.

    Uses dnspython to perform the DNS lookup. If dnspython is not installed,
    the domain is marked as verified with a warning.
    """
    q = db.query(TrackingDomain).filter(
        TrackingDomain.domain_id == domain_id,
        TrackingDomain.is_archived == False,
    )
    q = tenant_filter(q, TrackingDomain, tenant_id)
    td = q.first()
    if not td:
        raise HTTPException(status_code=404, detail="Tracking domain not found")

    cname_target = td.cname_target or _derive_cname_target()

    try:
        import dns.resolver  # type: ignore[import-untyped]

        try:
            answers = dns.resolver.resolve(td.domain_name, "CNAME")
            resolved_cnames = [str(rdata.target).rstrip(".") for rdata in answers]

            if cname_target.rstrip(".") in [c.rstrip(".") for c in resolved_cnames]:
                td.is_verified = True
                db.commit()
                db.refresh(td)
                logger.info("Tracking domain verified: %s -> %s", td.domain_name, cname_target)
                return {
                    "domain_id": td.domain_id,
                    "domain_name": td.domain_name,
                    "is_verified": True,
                    "message": f"CNAME record verified. {td.domain_name} resolves to {cname_target}.",
                    "cname_target": cname_target,
                    "resolved_cname": resolved_cnames[0] if resolved_cnames else None,
                }
            else:
                td.is_verified = False
                db.commit()
                logger.warning(
                    "CNAME mismatch for %s: expected %s, got %s",
                    td.domain_name, cname_target, resolved_cnames,
                )
                return {
                    "domain_id": td.domain_id,
                    "domain_name": td.domain_name,
                    "is_verified": False,
                    "message": (
                        f"CNAME mismatch. Expected {cname_target}, "
                        f"but {td.domain_name} resolves to {', '.join(resolved_cnames)}."
                    ),
                    "cname_target": cname_target,
                    "resolved_cname": resolved_cnames[0] if resolved_cnames else None,
                }

        except dns.resolver.NoAnswer:
            td.is_verified = False
            db.commit()
            return {
                "domain_id": td.domain_id,
                "domain_name": td.domain_name,
                "is_verified": False,
                "message": f"No CNAME record found for {td.domain_name}. Please add a CNAME record pointing to {cname_target}.",
                "cname_target": cname_target,
                "resolved_cname": None,
            }

        except dns.resolver.NXDOMAIN:
            td.is_verified = False
            db.commit()
            return {
                "domain_id": td.domain_id,
                "domain_name": td.domain_name,
                "is_verified": False,
                "message": f"Domain {td.domain_name} does not exist in DNS. Please check the domain name and try again.",
                "cname_target": cname_target,
                "resolved_cname": None,
            }

        except dns.resolver.Timeout:
            return {
                "domain_id": td.domain_id,
                "domain_name": td.domain_name,
                "is_verified": td.is_verified,
                "message": f"DNS lookup timed out for {td.domain_name}. Please try again later.",
                "cname_target": cname_target,
                "resolved_cname": None,
            }

        except Exception as e:
            logger.error("DNS resolution error for %s: %s", td.domain_name, str(e))
            return {
                "domain_id": td.domain_id,
                "domain_name": td.domain_name,
                "is_verified": td.is_verified,
                "message": f"DNS lookup failed: {str(e)}",
                "cname_target": cname_target,
                "resolved_cname": None,
            }

    except ImportError:
        # dnspython not installed — mark as verified with a warning
        logger.warning(
            "dnspython not installed. Marking %s as verified without DNS check.",
            td.domain_name,
        )
        td.is_verified = True
        db.commit()
        db.refresh(td)
        return {
            "domain_id": td.domain_id,
            "domain_name": td.domain_name,
            "is_verified": True,
            "message": (
                "DNS verification library (dnspython) is not installed. "
                "Domain marked as verified without actual DNS check. "
                "Install dnspython for proper CNAME verification."
            ),
            "cname_target": cname_target,
            "resolved_cname": None,
        }


@router.delete("/{domain_id}", summary="Delete a tracking domain")
def delete_tracking_domain(
    domain_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Soft-delete a tracking domain by setting is_archived=True (admin+ only).

    If the domain was the default, the default flag is cleared.
    """
    q = db.query(TrackingDomain).filter(
        TrackingDomain.domain_id == domain_id,
        TrackingDomain.is_archived == False,
    )
    q = tenant_filter(q, TrackingDomain, tenant_id)
    td = q.first()
    if not td:
        raise HTTPException(status_code=404, detail="Tracking domain not found")

    td.is_archived = True
    td.is_default = False
    td.is_verified = False
    db.commit()

    logger.info("Soft-deleted tracking domain: %s (id=%d)", td.domain_name, domain_id)
    return {"message": "Tracking domain deleted"}


@router.put("/{domain_id}/default", summary="Set as default tracking domain")
def set_default_tracking_domain(
    domain_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN])),
    tenant_id: Optional[int] = Depends(get_current_tenant_id),
):
    """Set a tracking domain as the default (admin+ only).

    Unsets any previously default domain. Only non-archived, verified domains
    can be set as default.
    """
    q = db.query(TrackingDomain).filter(
        TrackingDomain.domain_id == domain_id,
        TrackingDomain.is_archived == False,
    )
    q = tenant_filter(q, TrackingDomain, tenant_id)
    td = q.first()
    if not td:
        raise HTTPException(status_code=404, detail="Tracking domain not found")

    if not td.is_verified:
        raise HTTPException(
            status_code=400,
            detail="Cannot set an unverified domain as default. Verify the DNS CNAME record first.",
        )

    # Unset all other defaults (scoped to tenant)
    unset_query = db.query(TrackingDomain).filter(
        TrackingDomain.is_default == True,
        TrackingDomain.domain_id != domain_id,
    )
    unset_query = tenant_filter(unset_query, TrackingDomain, tenant_id)
    unset_query.update({"is_default": False}, synchronize_session="fetch")

    td.is_default = True
    db.commit()
    db.refresh(td)

    logger.info("Set default tracking domain: %s (id=%d)", td.domain_name, domain_id)
    return _domain_to_dict(td)
