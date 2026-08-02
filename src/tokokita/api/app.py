"""A factory, not a module-level `app`, so importing configures no exporter and opens no
database: `uvicorn tokokita.api.app:create_app --factory`.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from pydantic_ai import Agent
from sqlalchemy.ext.asyncio import AsyncSession

from ..agentic_system.agents.support.agent import TOOL_ACTIVITY, build_agent
from ..agentic_system.agents.support.deps import SupportDeps
from ..agentic_system.agents.support.intake import resolve_customer
from ..agentic_system.agents.support.output import AgentReply
from ..agentic_system.agents.support.runner import run_turn
from ..agentic_system.agents.support.streaming import stream_turn
from ..agentic_system.capabilities.orders.schemas import OrderDetail
from ..agentic_system.capabilities.orders.services import OrderService
from ..agentic_system.shared.database import (
    Sessions,
    create_engine,
    create_schema,
    session_factory,
    session_scope,
)
from ..agentic_system.shared.message_store import MessageStore
from ..agentic_system.shared.settings import Settings
from ..agentic_system.shared.telemetry import setup_observability
from ..agentic_system.shared.transcript import Turn, read
from ..data.seed import seed_if_empty

STATIC = Path(__file__).parent / "static"

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^(\+?62|0)\d{8,13}$")


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    customer_hint: str | None = None
    message: str = Field(min_length=1, max_length=4000)

    @field_validator("customer_hint")
    @classmethod
    def _known_hint_shape(cls, value: str | None) -> str | None:
        if value is None:
            return None
        hint = value.strip()
        if not hint:
            return None
        if EMAIL_RE.match(hint) or PHONE_RE.match(hint) or hint.isdigit():
            return hint
        raise ValueError("customer_hint harus berupa email, nomor telepon, atau order id")


def get_sessions(request: Request) -> Sessions:
    return request.app.state.sessions


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """For plain reads only. A streaming response outlives this teardown, so the chat routes
    open their own scope instead.
    """
    async with session_scope(request.app.state.sessions) as session:
        yield session


Db = Annotated[AsyncSession, Depends(get_session)]
Pool = Annotated[Sessions, Depends(get_sessions)]


def get_agent(request: Request) -> Agent[SupportDeps, str]:
    return request.app.state.agent


def create_app(settings: Settings | None = None, *, sessions: Sessions | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = settings
        app.state.agent = build_agent(settings)
        if sessions is not None:  # injected pool belongs to the caller; only ours gets disposed
            app.state.sessions = sessions
            yield
            return
        engine = create_engine(settings.database_url)
        await create_schema(engine)
        await seed_if_empty(engine)
        app.state.sessions = session_factory(engine)
        yield
        await engine.dispose()

    app = FastAPI(title="TokoKita CS Agent", version="0.1.0", lifespan=lifespan)
    setup_observability(settings, app)

    @app.post("/chat/stream")
    async def chat_stream(
        body: ChatRequest,
        pool: Pool,
        agent: Agent[SupportDeps, str] = Depends(get_agent),
    ) -> StreamingResponse:
        return StreamingResponse(
            stream_turn(
                agent,
                pool,
                session_id=body.session_id,
                message=body.message,
                customer_hint=body.customer_hint,
                settings=settings,
                activity=TOOL_ACTIVITY,
            ),
            media_type="text/event-stream",
            headers={"cache-control": "no-cache", "x-accel-buffering": "no"},
        )

    @app.get("/chat/{session_id}", response_model=list[Turn])
    async def history(session_id: str, session: Db) -> list[Turn]:
        return read(await MessageStore(session).load(session_id))

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/chat", response_model=AgentReply)
    async def chat(
        body: ChatRequest,
        pool: Pool,
        agent: Agent[SupportDeps, str] = Depends(get_agent),
    ) -> AgentReply:
        return await run_turn(
            agent,
            pool,
            session_id=body.session_id,
            message=body.message,
            customer_hint=body.customer_hint,
            settings=settings,
        )

    @app.get("/orders/{order_id}", response_model=OrderDetail)
    async def order_detail(order_id: int, customer_hint: str, session: Db) -> OrderDetail:
        """Debug read, behind the same verification and scoping as the agent."""
        customer = await resolve_customer(session, customer_hint)
        if customer is None:
            raise HTTPException(status_code=401, detail="Identitas belum terverifikasi.")
        detail = await OrderService(session).detail(order_id, customer.customer_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="Pesanan tidak ditemukan.")
        return detail

    # Mounted last so the API routes above win; the SPA is whatever is left.
    if STATIC.exists():
        app.mount("/", StaticFiles(directory=STATIC, html=True), name="web")
    return app
