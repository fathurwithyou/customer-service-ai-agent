"""Engine and session, nothing more.

Scoping moved into the services: every method that reads customer data takes a `customer_id`
and puts it in the WHERE clause. That is weaker than a repository with no unscoped method to
call, so `tests/test_services.py` asserts the isolation directly.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ...data.tables import Base

Sessions = async_sessionmaker[AsyncSession]


def create_engine(url: str) -> AsyncEngine:
    return create_async_engine(url, future=True, pool_pre_ping=True)


def session_factory(engine: AsyncEngine) -> Sessions:
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


async def create_schema(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@asynccontextmanager
async def session_scope(factory: Sessions) -> AsyncIterator[AsyncSession]:
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
