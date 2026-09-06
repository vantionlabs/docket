"""The app-facing auth seam.

Every route depends on `get_current_user`, which returns the minimal
`CurrentUser{id, email}` the rest of the app needs. It accepts EITHER:

  - the httpOnly session cookie (browsers), or
  - an `X-API-Key: sk_...` key (service-to-service, headless, widgets).

This indirection is deliberate: to escalate a project to an external identity
provider (Keycloak/Authentik OIDC, WorkOS, ...), reimplement ONLY this
function to verify that provider's token. See docs/setup-auth.md.
"""

import uuid

from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.api_keys import resolve_api_key
from app.auth.backend import fastapi_users
from app.db.engine import get_db
from app.db.models import User

# `optional=True` → returns None instead of 401 when no cookie, so we can fall
# through to the API-key path.
current_user_optional = fastapi_users.current_user(active=True, optional=True)
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


class CurrentUser(BaseModel):
    id: uuid.UUID
    email: str


def get_current_user(
    cookie_user: User | None = Depends(current_user_optional),
    api_key: str | None = Security(_api_key_header),
    db: Session = Depends(get_db),
) -> CurrentUser:
    if cookie_user is not None:
        return CurrentUser(id=cookie_user.id, email=cookie_user.email)

    if api_key:
        user_id = resolve_api_key(db, api_key)
        if user_id is not None:
            row = db.get(User, user_id)
            if row is not None:
                return CurrentUser(id=row.id, email=row.email)

    raise HTTPException(status_code=401, detail="Not authenticated")
