"""Database engine + session factory (SQLAlchemy 2.0, sync, psycopg3).

All database access goes through sessions from here — there is no other
data-access path (no PostgREST, no raw connections). API routes take
`Depends(get_db)`; background workflows open their own `SessionLocal()`
(never reuse a request session across a task boundary).
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

engine = create_engine(
    settings.sqlalchemy_database_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=5,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: one session per request, always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
