"""Async SQLAlchemy engine + session factory.

Selects SQLite (DEV) or Postgres (PROD) based on VECTOR_STORE_MODE.
"""

from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import VectorStoreMode, settings
from app.models.db import Base


def _make_engine():
    if settings.VECTOR_STORE_MODE == VectorStoreMode.DEV:
        url = f"sqlite+aiosqlite:///{settings.SQLITE_PATH}"
        return create_async_engine(url, echo=settings.DEBUG, connect_args={"check_same_thread": False})
    else:
        return create_async_engine(settings.POSTGRES_DSN, echo=settings.DEBUG, pool_size=10, max_overflow=20)


engine = _make_engine()
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def create_db_and_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
