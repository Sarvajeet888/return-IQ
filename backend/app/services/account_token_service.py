"""PHASE 5 — Single-use account tokens (invitation, email verification).

WHY NOT TEMPORARY PASSWORDS
---------------------------
The previous invite flow created the account with `Welcome@<6 hex chars>` and
emailed it. Three problems, in increasing order of severity:

1. **Low entropy.** Six hex characters is 24 bits. The `Welcome@` prefix is
   fixed and public. That is roughly 16.7 million candidates against an
   endpoint whose rate limit is generous by design.
2. **It persists.** A password is a durable credential. It sits in the
   recipient's inbox, their provider's servers, and every backup of both,
   working indefinitely until someone changes it. Most people never do.
3. **It is a full credential.** Anyone who reads that email -- a shared
   mailbox, a forwarded thread, a compromised account -- gets complete access
   to the org's returns, customers and fraud scores.

A token here grants exactly one action (set your initial password / confirm
your address), exactly once, within a short window, and is stored only as a
hash so that database access cannot be turned into account access.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from app.db import store

# 32 bytes from the OS CSPRNG -> 256 bits of entropy, URL-safe base64.
# Not uuid4(): uuid4 is 122 bits and, more importantly, several UUID versions
# are time- or MAC-derived. Reaching for `secrets` states the intent so nobody
# later "simplifies" it to uuid1 or random.
_TOKEN_BYTES = 32

PURPOSE_INVITATION = "invitation"
PURPOSE_EMAIL_VERIFICATION = "email_verification"

# Invitations are longer-lived because a new colleague may not check email
# until the next working day; verification is shorter because the user is
# already at their keyboard when it is sent.
_TTL = {
    PURPOSE_INVITATION: timedelta(days=7),
    PURPOSE_EMAIL_VERIFICATION: timedelta(hours=24),
}


def _hash(raw_token: str) -> str:
    """SHA-256, not bcrypt.

    Deliberate difference from password hashing. Bcrypt's slowness defends
    low-entropy human-chosen secrets against offline brute force. This token
    has 256 bits of CSPRNG entropy, so brute force is not a threat model, and
    a slow hash on every verification request would be a self-inflicted DoS
    vector. Fast hashing of a high-entropy secret is correct here; it would be
    wrong for a password.
    """
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def issue(user_id: str, purpose: str) -> str:
    """Create a token and return the RAW value.

    The raw value is returned exactly once, to be emailed. It is never stored
    and cannot be recovered afterwards -- if the email is lost the invitation
    must be reissued, which is the correct trade.
    """
    if purpose not in _TTL:
        raise ValueError(f"Unknown token purpose: {purpose!r}")

    # Invalidate any outstanding token for the same purpose. Otherwise
    # re-inviting someone leaves the earlier token live, so revoking an
    # invitation by reissuing it would not actually revoke anything.
    store.invalidate_account_tokens(user_id, purpose)

    raw = secrets.token_urlsafe(_TOKEN_BYTES)
    store.create_account_token(
        token_hash=_hash(raw),
        user_id=user_id,
        purpose=purpose,
        expires_at=datetime.now(UTC) + _TTL[purpose],
    )
    return raw


def consume(raw_token: str, purpose: str) -> str | None:
    """Validate and burn a token. Returns the user_id, or None if invalid.

    Returns None -- never raises a distinguishing error -- for every failure
    mode: unknown token, wrong purpose, expired, already used. Callers get one
    indistinguishable answer, so an attacker cannot use error differences to
    learn whether a token existed.

    The check-and-burn is a single atomic UPDATE in the store layer rather than
    a read followed by a write. Two requests arriving together with the same
    token would otherwise both pass the read before either wrote, and the token
    would be used twice.
    """
    if not raw_token or not isinstance(raw_token, str):
        return None

    return store.consume_account_token(
        token_hash=_hash(raw_token),
        purpose=purpose,
        now=datetime.now(UTC),
    )
