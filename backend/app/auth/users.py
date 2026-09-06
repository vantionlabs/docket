"""fastapi-users UserManager: user lifecycle hooks + token secrets."""

import uuid

from fastapi import Depends
from fastapi_users import BaseUserManager, UUIDIDMixin
from fastapi_users.db import SQLAlchemyUserDatabase

from app.auth.db import get_user_db
from app.config import settings
from app.db.models import User
from app.logging import get_logger

log = get_logger(__name__)


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    reset_password_token_secret = settings.auth_secret
    verification_token_secret = settings.auth_secret

    async def on_after_register(self, user: User, request=None) -> None:
        """Give the new user an org they own (spec section 11).

        Done here rather than lazily so the very first request already has a
        tenant, and so a user who never uploads anything still appears in
        the org tables rather than being invisible until they do.

        fastapi-users is the one async path in this app, so the sync session
        is opened explicitly rather than injected.
        """
        from app.auth.orgs import ensure_personal_org
        from app.db.engine import SessionLocal

        log.info("user.registered", user_id=str(user.id))
        with SessionLocal() as db:
            ensure_personal_org(db, user.id, user.email)

    async def on_after_forgot_password(self, user: User, token: str, request=None) -> None:
        from app.email.client import send_email

        link = f"{settings.frontend_url}/reset-password?token={token}"
        send_email(
            to=user.email,
            subject="Reset your password",
            html=f'<p>Reset your password: <a href="{link}">{link}</a></p>',
        )

    async def on_after_request_verify(self, user: User, token: str, request=None) -> None:
        from app.email.client import send_email

        link = f"{settings.frontend_url}/verify-email?token={token}"
        send_email(
            to=user.email,
            subject="Verify your email",
            html=f'<p>Verify your email: <a href="{link}">{link}</a></p>',
        )


async def get_user_manager(user_db: SQLAlchemyUserDatabase = Depends(get_user_db)):
    yield UserManager(user_db)
