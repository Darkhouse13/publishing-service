"""Fernet-based symmetric encryption helpers for credential storage.

All sensitive values (API keys, passwords) must be encrypted at rest using
this module.  The ``ENCRYPTION_KEY`` is loaded once from Pydantic Settings at
import time.
"""

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    """Return a lazily-initialised :class:`Fernet` instance.

    Raises:
        ValueError: If ``ENCRYPTION_KEY`` is not configured.
    """
    global _fernet
    if _fernet is None:
        key = settings.ENCRYPTION_KEY
        if not key:
            raise ValueError("ENCRYPTION_KEY is not set. Add it to your .env file.")
        _fernet = Fernet(key.encode())
    return _fernet


def encrypt(plaintext: str) -> str:
    """Encrypt *plaintext* and return a base64-encoded Fernet token string."""
    f = _get_fernet()
    return f.encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    """Decrypt a Fernet *token* and return the original plaintext string.

    Raises:
        ValueError: If the token is invalid or was encrypted with a different key.
    """
    f = _get_fernet()
    try:
        return f.decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("Failed to decrypt token – invalid key or corrupted data.") from exc
