"""A factory, not a module-level `app`, so importing configures no exporter and opens no
database: `uvicorn tokokita.api.app:create_app --factory`.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from pydantic_ai import Agent

from ..agentic_system.agents.support.agent import TOOL_ACTIVITY, build_agent
from ..agentic_system.agents.support.deps import SupportDeps
from ..agentic_system.agents.support.output import AgentReply
from ..agentic_system.agents.support.runner import resolve_customer, run_turn
from ..agentic_system.agents.support.streaming import stream_turn
from ..agentic_system.capabilities.orders.schemas import OrderDetail
from ..agentic_system.capabilities.orders.services import OrderService
from ..agentic_system.shared.database import Database
from ..agentic_system.shared.message_store import MessageStore
from ..agentic_system.shared.settings import Settings
from ..agentic_system.shared.telemetry import setup_observability
from ..agentic_system.shared.transcript import Turn, read

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


def get_db(request: Request) -> Database:
    return request.app.state.db


def get_agent(request: Request) -> Agent[SupportDeps, str]:
    return request.app.state.agent


def create_app(settings: Settings | None = None, *, db: Database | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        owned = db is None  # an injected database belongs to the caller; only ours gets closed
        app.state.settings = settings
        app.state.db = db or await Database.connect(settings.database_path)
        app.state.agent = build_agent(settings)
        app.state.store = MessageStore(app.state.db)
        yield
        if owned:
            await app.state.db.close()

    app = FastAPI(title="TokoKita CS Agent", version="0.1.0", lifespan=lifespan)
    setup_observability(settings, app)

    @app.post("/chat/stream")
    async def chat_stream(
        body: ChatRequest,
        request: Request,
        db: Database = Depends(get_db),
        agent: Agent[SupportDeps, str] = Depends(get_agent),
    ) -> StreamingResponse:
        return StreamingResponse(
            stream_turn(
                agent,
                db,
                session_id=body.session_id,
                message=body.message,
                customer_hint=body.customer_hint,
                store=request.app.state.store,
                model_name=settings.model_name,
                activity=TOOL_ACTIVITY,
            ),
            media_type="text/event-stream",
            headers={"cache-control": "no-cache", "x-accel-buffering": "no"},
        )

    @app.get("/chat/{session_id}", response_model=list[Turn])
    async def history(session_id: str, request: Request) -> list[Turn]:
        return read(await request.app.state.store.load(session_id))

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/chat", response_model=AgentReply)
    async def chat(
        body: ChatRequest,
        request: Request,
        db: Database = Depends(get_db),
        agent: Agent[SupportDeps, str] = Depends(get_agent),
    ) -> AgentReply:
        return await run_turn(
            agent,
            db,
            session_id=body.session_id,
            message=body.message,
            customer_hint=body.customer_hint,
            store=request.app.state.store,
            model_name=settings.model_name,
        )

    @app.get("/orders/{order_id}", response_model=OrderDetail)
    async def order_detail(
        order_id: int, customer_hint: str, db: Database = Depends(get_db)
    ) -> OrderDetail:
        """Debug read, behind the same verification and scoping as the agent."""
        customer = await resolve_customer(db, customer_hint)
        if customer is None:
            raise HTTPException(status_code=401, detail="Identitas belum terverifikasi.")
        detail = await OrderService(db).detail(order_id, customer.customer_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="Pesanan tidak ditemukan.")
        return detail

    # Mounted last so the API routes above win; the SPA is whatever is left.
    if STATIC.exists():
        app.mount("/", StaticFiles(directory=STATIC, html=True), name="web")
    return app
