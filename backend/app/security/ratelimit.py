"""Redis fixed-window rate limiting.

A `RateLimiter(limit, window)` is a FastAPI dependency: it counts requests
per identity (the current user) in a fixed time window and raises 429 when
the limit is exceeded. Fixed-window is simple and good enough for protecting
cost-sensitive endpoints; swap for a sliding window if you need smoother
bounds. Fails OPEN (allows the request) if Redis is briefly unreachable, so a
Redis blip never takes the API down — tighten to fail-closed if abuse
protection must be strict.
"""

from functools import lru_cache

import redis
from fastapi import Depends, HTTPException

from app.auth.dependencies import CurrentUser, get_current_user
from app.config import settings
from app.logging import get_logger

log = get_logger(__name__)


@lru_cache
def _redis() -> redis.Redis:
    return redis.from_url(settings.redis_url)


class RateLimiter:
    def __init__(self, limit: int, window_seconds: int, scope: str) -> None:
        self.limit = limit
        self.window = window_seconds
        self.scope = scope

    def __call__(self, user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        key = f"ratelimit:{self.scope}:{user.id}"
        try:
            client = _redis()
            count = client.incr(key)
            if count == 1:
                client.expire(key, self.window)
        except redis.RedisError:
            log.warning("ratelimit.redis_unavailable", scope=self.scope)
            return user  # fail open
        if count > self.limit:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Try again shortly.",
                headers={"Retry-After": str(self.window)},
            )
        return user


# Ready-to-use limiter for the chat endpoint (the costly path). Use it as a
# dependency: it returns the CurrentUser, so it replaces get_current_user.
chat_limiter = RateLimiter(settings.chat_rate_limit, settings.chat_rate_window_seconds, "chat")
