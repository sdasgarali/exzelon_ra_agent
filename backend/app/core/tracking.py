"""HMAC-based tracking token generation and validation."""
import hashlib
import hmac
import urllib.parse
from app.core.config import settings


def generate_tracking_token(tracking_id: str) -> str:
    """Generate an HMAC token for a tracking ID."""
    return hmac.new(
        settings.SECRET_KEY.encode(),
        tracking_id.encode(),
        hashlib.sha256
    ).hexdigest()[:16]


def validate_tracking_token(tracking_id: str, token: str) -> bool:
    """Validate an HMAC token for a tracking ID."""
    expected = generate_tracking_token(tracking_id)
    return hmac.compare_digest(expected, token)


def sanitize_redirect_url(url: str) -> str | None:
    """Sanitize a redirect URL to prevent open redirect attacks.

    Only allows http and https schemes. Returns None if invalid.
    """
    if not url:
        return None
    decoded = urllib.parse.unquote(url)
    parsed = urllib.parse.urlparse(decoded)
    if parsed.scheme not in ("http", "https"):
        return None
    # Prevent protocol-relative URLs
    if decoded.startswith("//"):
        return None
    return decoded
