"""`ALLOW_MODEL_REQUESTS = False` makes an accidental real call a test failure, not a bill."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

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
from tokokita.data.seed import seed_if_empty

models.ALLOW_MODEL_REQUESTS = False


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def sessions(tmp_path: Path) -> AsyncIterator[Sessions]:
    """A file, not `:memory:` -- each connection would otherwise get its own empty database."""
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    await create_schema(engine)
    await seed_if_empty(engine)
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
