"""`ALLOW_MODEL_REQUESTS = False` makes an accidental real call a test failure, not a bill."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
from pydantic_ai import models
from sqlalchemy.ext.asyncio import AsyncSession

from tokokita.agentic_system.agents.support.deps import SupportDeps
from tokokita.agentic_system.capabilities.customers.services import CustomerLookup
from tokokita.agentic_system.shared.database import (
    Sessions,
    create_engine,
    create_schema,
    session_factory,
)
from tokokita.agentic_system.shared.settings import Settings
from tokokita.data.seed import load_seed
from tokokita.data.tables import Base

models.ALLOW_MODEL_REQUESTS = False

# Its own database, because every test drops the schema. `docker compose up -d db` creates it.
TEST_URL = os.getenv(
    "TOKOKITA_TEST_DATABASE_URL",
    "postgresql+asyncpg://tokokita:tokokita@localhost:5433/tokokita_test",
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def sessions() -> AsyncIterator[Sessions]:
    engine = create_engine(TEST_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await create_schema(engine)
    await load_seed(engine)
    yield session_factory(engine)
    await engine.dispose()


@pytest.fixture
async def session(sessions: Sessions) -> AsyncIterator[AsyncSession]:
    async with sessions() as db:
        yield db


@pytest.fixture
def settings() -> Settings:
    return Settings(groq_api_key=None, phoenix_endpoint="")


@pytest.fixture
async def andi(session: AsyncSession) -> SupportDeps:
    """A verified turn as Andi (customer 1: order 1 shipped, order 2 delivered)."""
    customer = await CustomerLookup(session).by_contact("andi@example.com")
    assert customer is not None
    return SupportDeps(session=session, customer=customer)


@pytest.fixture
def anonymous(session: AsyncSession) -> SupportDeps:
    return SupportDeps(session=session)
