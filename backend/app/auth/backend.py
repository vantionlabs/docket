"""fastapi-users authentication backend: httpOnly cookie + JWT strategy.

Login at `/auth/jwt/login` sets an **httpOnly** cookie holding a JWT signed
with `settings.auth_secret` — the token is never exposed to JavaScript, so
XSS cannot exfiltrate it. The browser sends the cookie automatically on
same-site requests; with `SameSite=Lax` and the frontend + API under one
registrable domain, that also blocks CSRF. Verification is local (no
external identity provider), which is the point of owning auth here.
"""

import uuid

from fastapi_users import FastAPIUsers
from fastapi_users.authentication import (
    AuthenticationBackend,
    CookieTransport,
    JWTStrategy,
)

from app.auth.users import get_user_manager
from app.config import settings
from app.db.models import User

cookie_transport = CookieTransport(
    cookie_name=settings.auth_cookie_name,
    cookie_max_age=settings.auth_token_lifetime_seconds,
    cookie_secure=settings.auth_cookie_secure,
    cookie_httponly=True,
    cookie_samesite=settings.auth_cookie_samesite,
    cookie_domain=settings.auth_cookie_domain,
)


def get_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(
        secret=settings.auth_secret,
        lifetime_seconds=settings.auth_token_lifetime_seconds,
    )


auth_backend = AuthenticationBackend(
    name="cookie",
    transport=cookie_transport,
    get_strategy=get_jwt_strategy,
)

fastapi_users = FastAPIUsers[User, uuid.UUID](get_user_manager, [auth_backend])

# The raw fastapi-users dependency (returns the ORM User). The app-facing
# seam is `get_current_user` in dependencies.py, which wraps this.
current_active_user = fastapi_users.current_user(active=True)
