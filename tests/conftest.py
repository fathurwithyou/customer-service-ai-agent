"""`ALLOW_MODEL_REQUESTS = False` makes an accidental real call a test failure, not a bill."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from pydantic_ai import models

from tokokita.agentic_system.agents.support.deps import SupportDeps
from tokokita.agentic_system.capabilities.customers.schemas import Customer
from tokokita.agentic_system.shared.database import Database
from tokokita.agentic_system.shared.settings import Settings

models.ALLOW_MODEL_REQUESTS = False


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def db() -> AsyncIterator[Database]:
    database = await Database.connect(":memory:", seed_if_empty=False)
    await database.bootstrap()
    yield database
    await database.close()


@pytest.fixture
def settings() -> Settings:
    return Settings(groq_api_key=None, phoenix_endpoint="", database_path=":memory:")


@pytest.fixture
async def andi(db: Database) -> SupportDeps:
    """A verified turn as Andi (customer 1: order 1 shipped, order 2 delivered)."""
    row = await db.customer_row("andi@example.com")
    assert row is not None
    return SupportDeps(db=db, customer=Customer(**row))


@pytest.fixture
def anonymous(db: Database) -> SupportDeps:
    return SupportDeps(db=db)
