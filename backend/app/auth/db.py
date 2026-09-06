"""Async SQLAlchemy adapter for fastapi-users.

fastapi-users is async-first: its SQLAlchemy adapter needs an AsyncSession.
The rest of the app is sync (see app/db/engine.py) — user CRUD is the only
async path, on its own engine, against the same Postgres. psycopg3 drives
both sync and async with the same `postgresql+psycopg://` URL.
"""

from collections.abc import AsyncGenerator

from fastapi import Depends
from fastapi_users.db import SQLAlchemyUserDatabase
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.db.models import User

async_engine = create_async_engine(settings.sqlalchemy_database_url, pool_pre_ping=True)
async_session_maker = async_sessionmaker(async_engine, expire_on_commit=False)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session


async def get_user_db(session: AsyncSession = Depends(get_async_session)):
    yield SQLAlchemyUserDatabase(session, User)
