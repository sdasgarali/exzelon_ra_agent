"""Field-level encryption for sensitive data (mailbox passwords, API keys).

Uses Fernet symmetric encryption from the `cryptography` package.
The encryption key is read from the ENCRYPTION_KEY environment variable.
"""
import base64
import hashlib
import structlog
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

logger = structlog.get_logger()

# Fernet requires a 32-byte URL-safe base64-encoded key.
# We derive it deterministically from the user-provided ENCRYPTION_KEY
# so users can set any string (not just a valid Fernet key).
_fernet_instance = None


def _get_fernet() -> Fernet:
    """Get or create the Fernet cipher instance."""
    global _fernet_instance
    if _fernet_instance is not None:
        return _fernet_instance

    raw_key = settings.ENCRYPTION_KEY
    if not raw_key:
        raise RuntimeError(
            "ENCRYPTION_KEY is not set. Add it to your .env file. "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )

    # If it's already a valid Fernet key (44 chars, base64), use directly
    try:
        if len(raw_key) == 44:
            Fernet(raw_key.encode())
            _fernet_instance = Fernet(raw_key.encode())
            return _fernet_instance
    except Exception:
        pass

    # Otherwise derive a Fernet-compatible key from the raw string via SHA-256
    digest = hashlib.sha256(raw_key.encode()).digest()
    fernet_key = base64.urlsafe_b64encode(digest)
    _fernet_instance = Fernet(fernet_key)
    return _fernet_instance


def encrypt_field(plaintext: str) -> str:
    """Encrypt a plaintext string. Returns a Fernet token string (always starts with 'gAAAAA')."""
    if not plaintext:
        return plaintext
    f = _get_fernet()
    return f.encrypt(plaintext.encode()).decode()


def decrypt_field(ciphertext: str) -> str:
    """Decrypt a Fernet-encrypted string back to plaintext.

    If the value doesn't look like a Fernet token (legacy plaintext),
    returns it as-is for backward compatibility during migration.
    """
    if not ciphertext:
        return ciphertext

    # Fernet tokens always start with 'gAAAAA' (base64 of version byte + timestamp)
    if not ciphertext.startswith("gAAAAA"):
        return ciphertext  # Legacy plaintext — not yet migrated

    try:
        f = _get_fernet()
        return f.decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        logger.warning("Failed to decrypt field — returning raw value (possible key mismatch)")
        return ciphertext


def is_encrypted(value: str) -> bool:
    """Check if a value looks like a Fernet-encrypted token."""
    if not value:
        return False
    return value.startswith("gAAAAA") and len(value) > 50
