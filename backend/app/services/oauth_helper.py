"""OAuth2 helper for Microsoft 365 XOAUTH2 SMTP/IMAP authentication.

Implements the OAuth2 Authorization Code flow with XOAUTH2 SASL mechanism.
Falls back to Basic Auth (password) for non-OAuth mailboxes.
"""
import base64
import json
import urllib.parse
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

import httpx
import structlog

from app.core.config import settings
from app.core.encryption import encrypt_field, decrypt_field

logger = structlog.get_logger()

# Microsoft OAuth2 endpoints
_MS_AUTHORIZE_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize"
_MS_TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"

# Scopes required for SMTP and IMAP access
_MS_SCOPES = [
    "offline_access",
    "https://outlook.office365.com/SMTP.Send",
    "https://outlook.office365.com/IMAP.AccessAsUser.All",
]


def get_oauth_authorization_url(
    email: str,
    tenant_id: Optional[str] = None,
    state: str = "",
) -> str:
    """Build the Microsoft OAuth2 authorization URL.

    Args:
        email: Email address (used as login_hint).
        tenant_id: Azure AD tenant ID. Defaults to "common" for multi-tenant.
        state: Opaque state parameter for CSRF protection / mailbox identification.

    Returns:
        Full authorization URL to redirect the user to.
    """
    tenant = tenant_id or settings.MS365_OAUTH_TENANT_ID or "common"
    redirect_uri = settings.MS365_OAUTH_REDIRECT_URI

    params = {
        "client_id": settings.MS365_OAUTH_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "response_mode": "query",
        "scope": " ".join(_MS_SCOPES),
        "state": state,
        "login_hint": email,
    }
    base = _MS_AUTHORIZE_URL.format(tenant=tenant)
    return f"{base}?{urllib.parse.urlencode(params)}"


def exchange_code_for_tokens(
    code: str,
    tenant_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Exchange an authorization code for access + refresh tokens.

    Args:
        code: Authorization code from the OAuth callback.
        tenant_id: Azure AD tenant ID.

    Returns:
        Dict with access_token, refresh_token, expires_in (seconds).

    Raises:
        ValueError: If the token exchange fails.
    """
    tenant = tenant_id or settings.MS365_OAUTH_TENANT_ID or "common"
    token_url = _MS_TOKEN_URL.format(tenant=tenant)

    data = {
        "client_id": settings.MS365_OAUTH_CLIENT_ID,
        "client_secret": settings.MS365_OAUTH_CLIENT_SECRET,
        "code": code,
        "redirect_uri": settings.MS365_OAUTH_REDIRECT_URI,
        "grant_type": "authorization_code",
        "scope": " ".join(_MS_SCOPES),
    }

    with httpx.Client(timeout=30) as client:
        resp = client.post(token_url, data=data)

    if resp.status_code != 200:
        error_detail = resp.text[:500]
        logger.error("OAuth token exchange failed", status=resp.status_code, detail=error_detail)
        raise ValueError(f"Token exchange failed ({resp.status_code}): {error_detail}")

    token_data = resp.json()
    return {
        "access_token": token_data["access_token"],
        "refresh_token": token_data.get("refresh_token", ""),
        "expires_in": token_data.get("expires_in", 3600),
    }


def refresh_oauth_token(
    refresh_token: str,
    tenant_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Refresh an expired access token using the refresh token.

    Args:
        refresh_token: The OAuth2 refresh token.
        tenant_id: Azure AD tenant ID.

    Returns:
        Dict with new access_token, refresh_token, expires_in.

    Raises:
        ValueError: If the refresh fails (user may need to re-authorize).
    """
    tenant = tenant_id or settings.MS365_OAUTH_TENANT_ID or "common"
    token_url = _MS_TOKEN_URL.format(tenant=tenant)

    data = {
        "client_id": settings.MS365_OAUTH_CLIENT_ID,
        "client_secret": settings.MS365_OAUTH_CLIENT_SECRET,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
        "scope": " ".join(_MS_SCOPES),
    }

    with httpx.Client(timeout=30) as client:
        resp = client.post(token_url, data=data)

    if resp.status_code != 200:
        error_detail = resp.text[:500]
        logger.error("OAuth token refresh failed", status=resp.status_code, detail=error_detail)
        raise ValueError(f"Token refresh failed ({resp.status_code}): {error_detail}")

    token_data = resp.json()
    return {
        "access_token": token_data["access_token"],
        "refresh_token": token_data.get("refresh_token", refresh_token),
        "expires_in": token_data.get("expires_in", 3600),
    }


def get_valid_access_token(db, mailbox) -> str:
    """Get a valid access token for the mailbox, refreshing if expired.

    Checks expiration with a 5-minute buffer. If expired, refreshes the token
    and persists the new tokens (encrypted) to the database.

    Args:
        db: SQLAlchemy session.
        mailbox: SenderMailbox ORM instance.

    Returns:
        A valid access token string.

    Raises:
        ValueError: If no refresh token is available or refresh fails.
    """
    if not mailbox.oauth_refresh_token:
        raise ValueError("No OAuth refresh token stored for this mailbox")

    refresh_token = decrypt_field(mailbox.oauth_refresh_token)
    now = datetime.utcnow()

    # Check if current token is still valid (with 5-minute buffer)
    if (
        mailbox.oauth_access_token
        and mailbox.oauth_token_expires_at
        and mailbox.oauth_token_expires_at > now + timedelta(minutes=5)
    ):
        return decrypt_field(mailbox.oauth_access_token)

    # Token expired or missing — refresh it
    logger.info("Refreshing OAuth token", mailbox=mailbox.email)
    token_data = refresh_oauth_token(refresh_token, mailbox.oauth_tenant_id)

    # Persist new tokens (encrypted)
    mailbox.oauth_access_token = encrypt_field(token_data["access_token"])
    mailbox.oauth_refresh_token = encrypt_field(token_data["refresh_token"])
    mailbox.oauth_token_expires_at = now + timedelta(seconds=token_data["expires_in"])
    db.commit()

    return token_data["access_token"]


def build_xoauth2_string(email: str, access_token: str) -> str:
    """Build the base64-encoded XOAUTH2 SASL string.

    Format: user={email}\\x01auth=Bearer {token}\\x01\\x01
    """
    auth_string = f"user={email}\x01auth=Bearer {access_token}\x01\x01"
    return base64.b64encode(auth_string.encode()).decode()


def smtp_authenticate(server, email: str, mailbox, db) -> None:
    """Authenticate an SMTP connection using OAuth2 or password.

    Args:
        server: smtplib.SMTP instance (already connected + STARTTLS'd).
        email: Mailbox email address.
        mailbox: SenderMailbox ORM instance.
        db: SQLAlchemy session (needed for token refresh persistence).
    """
    if getattr(mailbox, "auth_method", "password") == "oauth2":
        access_token = get_valid_access_token(db, mailbox)
        xoauth2_str = build_xoauth2_string(email, access_token)
        # smtplib.SMTP.auth() with XOAUTH2 mechanism
        server.auth("XOAUTH2", lambda challenge=None: xoauth2_str)
        logger.debug("SMTP OAuth2 auth successful", email=email)
    else:
        plain_password = decrypt_field(mailbox.password)
        server.login(email, plain_password)


def imap_authenticate(imap, email: str, mailbox, db) -> None:
    """Authenticate an IMAP connection using OAuth2 or password.

    Args:
        imap: imaplib.IMAP4_SSL instance (already connected).
        email: Mailbox email address.
        mailbox: SenderMailbox ORM instance.
        db: SQLAlchemy session (needed for token refresh persistence).
    """
    if getattr(mailbox, "auth_method", "password") == "oauth2":
        access_token = get_valid_access_token(db, mailbox)
        xoauth2_str = build_xoauth2_string(email, access_token)
        # imaplib expects a callable that returns bytes
        imap.authenticate("XOAUTH2", lambda challenge: xoauth2_str.encode())
        logger.debug("IMAP OAuth2 auth successful", email=email)
    else:
        plain_password = decrypt_field(mailbox.password)
        imap.login(email, plain_password)
