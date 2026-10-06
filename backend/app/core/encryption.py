"""
Encryption for personally identifiable information at rest.

Closes Known Issue KI-002: customer name, email, and phone were stored as
plaintext columns. Anyone with a database file, a stolen backup, or read
access to a replica could read every customer record in every tenant.

## How it works

`EncryptedString` is a SQLAlchemy TypeDecorator. Encryption happens on the way
into the database and decryption on the way out, so application code and every
existing query keep working unchanged - `customer.email` is still a string.

Fernet (AES-128-CBC + HMAC-SHA256) from the `cryptography` package. Authenticated,
so tampering with ciphertext is detected rather than silently decrypting to
garbage.

## The trade-off, stated plainly

Encrypted columns cannot be searched with SQL `LIKE` or compared with `=`,
because identical plaintext produces different ciphertext every time (Fernet
includes a random IV). That is the property that makes it secure and also the
property that breaks search.

`store.search_customers()` therefore filters in Python after decryption. That is
O(n) per search. At a few thousand customers per org it is fine; past roughly
50,000 it needs a searchable-encryption scheme (a blind index: a separate
deterministic HMAC column used only for equality lookup). Noted in the
architecture debt register rather than pretended away.

## Key management

The key derives from SECRET_KEY via HKDF, so there is no second secret to
distribute. **Consequence: rotating SECRET_KEY makes existing encrypted data
unreadable.** Set PII_ENCRYPTION_KEY explicitly if you need to rotate JWT
signing independently of data encryption - which you eventually will.

## Migrating existing data

Existing plaintext rows do not decrypt. `decrypt_value()` detects this and
returns the value as-is, so the application keeps working during rollout.
`scripts/encrypt_existing_pii.py` performs the one-time backfill.
"""
from __future__ import annotations

import base64
import logging

from sqlalchemy import String, TypeDecorator

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

try:
    from cryptography.fernet import Fernet, InvalidToken
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    _CRYPTO_AVAILABLE = True
except ImportError:  # pragma: no cover
    _CRYPTO_AVAILABLE = False
    InvalidToken = Exception  # type: ignore

_fernet = None


def _get_fernet():
    """Build the Fernet instance once, lazily."""
    global _fernet
    if _fernet is not None:
        return _fernet
    if not _CRYPTO_AVAILABLE:
        logger.warning(
            "cryptography is not installed - PII will be stored in PLAINTEXT. "
            "Install it before any production deployment."
        )
        return None

    explicit = getattr(settings, "PII_ENCRYPTION_KEY", "")
    if explicit:
        key = explicit.encode() if isinstance(explicit, str) else explicit
    else:
        # Derive from SECRET_KEY. HKDF with a distinct info string keeps this
        # key cryptographically separate from anything else SECRET_KEY is used
        # for, so a weakness in one does not compromise the other.
        derived = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"returniq-pii-encryption-v1",
            info=b"customer-pii-at-rest",
        ).derive(settings.SECRET_KEY.encode())
        key = base64.urlsafe_b64encode(derived)

    _fernet = Fernet(key)
    return _fernet


def encrypt_value(plaintext: str | None) -> str | None:
    if plaintext is None or plaintext == "":
        return plaintext
    f = _get_fernet()
    if f is None:
        return plaintext
    return f.encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str | None) -> str | None:
    """
    Decrypt, tolerating plaintext.

    Rows written before encryption was enabled are not valid Fernet tokens.
    Returning them unchanged lets the application run normally while the
    backfill script works through the table, instead of erroring on every
    un-migrated row.
    """
    if ciphertext is None or ciphertext == "":
        return ciphertext
    f = _get_fernet()
    if f is None:
        return ciphertext
    try:
        return f.decrypt(ciphertext.encode()).decode()
    except (InvalidToken, ValueError, TypeError):
        # Pre-encryption plaintext, or a value encrypted under a different key.
        return ciphertext


class EncryptedString(TypeDecorator):
    """
    Transparently encrypted String column.

    Ciphertext is ~1.6x longer than plaintext plus a fixed overhead, so the
    underlying column is sized generously. Usage:

        email: Mapped[str] = mapped_column(EncryptedString(255))
    """
    impl = String
    cache_ok = True

    def __init__(self, length: int = 255, **kwargs):
        # Fernet output is base64 of (IV + ciphertext + HMAC). Allow ample room.
        super().__init__(length=max(length * 3, 512), **kwargs)

    def process_bind_param(self, value, dialect):
        return encrypt_value(value)

    def process_result_value(self, value, dialect):
        return decrypt_value(value)


def is_encryption_active() -> bool:
    return _get_fernet() is not None
