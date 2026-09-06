"""API-key management (create / list / revoke).

Authenticated as the logged-in user (cookie). The plaintext key is returned
ONCE, on creation — it is never retrievable again.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import NOT_FOUND, UNAUTHORIZED
from app.auth.api_keys import create_api_key
from app.auth.dependencies import CurrentUser, get_current_user
from app.db.engine import get_db
from app.db.models import ApiKey

router = APIRouter(prefix="/api-keys", tags=["api-keys"], responses=UNAUTHORIZED)


class ApiKeyCreate(BaseModel):
    name: str = Field(description="A label to recognise this key later.")


class ApiKeyOut(BaseModel):
    id: uuid.UUID
    name: str
    prefix: str = Field(description="Masked prefix for display, e.g. `sk_a1b2c3`.")
    last_used_at: datetime | None
    created_at: datetime


class ApiKeyCreated(ApiKeyOut):
    key: str = Field(description="The plaintext key. Shown ONCE — store it now.")


@router.post("", response_model=ApiKeyCreated, status_code=201, summary="Create an API key")
def create_key(
    body: ApiKeyCreate,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiKeyCreated:
    api_key, plaintext = create_api_key(db, user.id, body.name)
    return ApiKeyCreated(
        id=api_key.id,
        name=api_key.name,
        prefix=api_key.prefix,
        last_used_at=api_key.last_used_at,
        created_at=api_key.created_at,
        key=plaintext,
    )


@router.get("", response_model=list[ApiKeyOut], summary="List your API keys")
def list_keys(
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ApiKey]:
    return list(
        db.scalars(
            select(ApiKey)
            .where(ApiKey.user_id == user.id, ApiKey.revoked_at.is_(None))
            .order_by(ApiKey.created_at.desc())
        )
    )


@router.delete("/{key_id}", status_code=204, summary="Revoke an API key", responses=NOT_FOUND)
def revoke_key(
    key_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    from datetime import UTC

    row = db.get(ApiKey, key_id)
    if row is None or row.user_id != user.id or row.revoked_at is not None:
        raise HTTPException(404, "API key not found")
    row.revoked_at = datetime.now(UTC)
    db.commit()
