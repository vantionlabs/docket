"""API keys for non-browser clients (service-to-service, headless, widgets).

The plaintext key is shown once at creation; we persist only its SHA-256
hash. Presented as `X-API-Key: sk_...`; resolves to the owning user through
the same `CurrentUser` seam as the cookie session.
"""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ApiKey

_PREFIX = "sk_"


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def generate_key() -> tuple[str, str, str]:
    """Return (plaintext, key_hash, display_prefix). Store the hash + prefix;
    return the plaintext to the caller exactly once."""
    plaintext = _PREFIX + secrets.token_urlsafe(32)
    return plaintext, _hash(plaintext), plaintext[: len(_PREFIX) + 6]


def create_api_key(db: Session, user_id: uuid.UUID, name: str) -> tuple[ApiKey, str]:
    plaintext, key_hash, prefix = generate_key()
    api_key = ApiKey(user_id=user_id, name=name, key_hash=key_hash, prefix=prefix)
    db.add(api_key)
    db.commit()
    return api_key, plaintext


def resolve_api_key(db: Session, presented: str) -> uuid.UUID | None:
    """Return the owning user id for a valid, non-revoked key, else None.
    Touches `last_used_at` on success."""
    row = db.scalar(
        select(ApiKey).where(ApiKey.key_hash == _hash(presented), ApiKey.revoked_at.is_(None))
    )
    if row is None:
        return None
    row.last_used_at = datetime.now(UTC)
    db.commit()
    return row.user_id
