"""The HTTP surface end to end. `FunctionModel` fixes which tools the agent calls, so a reply
can be checked for *grounding* rather than for whether a sampled completion looked right.

`ASGITransport`, not `TestClient`: the latter drives the app from a worker thread on its own
event loop, and an asyncpg connection belongs to the loop that opened it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from sqlalchemy import func, select

from tokokita.agentic_system.shared.database import Sessions
from tokokita.agentic_system.shared.settings import Settings
from tokokita.api.app import create_app
from tokokita.data import tables

REPLY = "Pesanan 1 sedang dikirim JNE, resi JNE0012345678."

pytestmark = pytest.mark.anyio


def _settings() -> Settings:
    return Settings(groq_api_key=None, phoenix_endpoint="")


@asynccontextmanager
async def serving(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        yield client


def _script(*calls: tuple[str, dict]) -> FunctionModel:
    def model_fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        step = sum(isinstance(m, ModelResponse) for m in messages)
        if step < len(calls):
            name, args = calls[step]
            return ModelResponse(parts=[ToolCallPart(name, args)])
        return ModelResponse(parts=[TextPart(REPLY)])

    return FunctionModel(model_fn)


async def test_health(sessions: Sessions) -> None:
    async with serving(create_app(_settings(), sessions=sessions)) as client:
        assert (await client.get("/health")).json() == {"status": "ok"}


async def test_where_is_my_order_is_grounded_in_tool_calls(sessions: Sessions) -> None:
    """Acceptance criterion 3: the reply is built from get_order_detail + track_shipment."""
    settings = _settings()
    model = _script(("get_order_detail", {"order_id": 1}), ("track_shipment", {"order_id": 1}))
    app = create_app(settings, sessions=sessions)
    async with serving(app) as client:
        with app.state.agent.override(model=model):
            response = await client.post(
                "/chat",
                json={
                    "session_id": "s1",
                    "customer_hint": "andi@example.com",
                    "message": "Pesanan 1 saya sudah sampai mana?",
                },
            )
    assert response.status_code == 200
    body = response.json()
    assert "JNE0012345678" in body["message"]
    assert body["escalated"] is False


async def test_debug_order_endpoint_requires_verification(sessions: Sessions) -> None:
    """Acceptance criterion 4, at the HTTP layer: no identity, no data."""
    async with serving(create_app(_settings(), sessions=sessions)) as client:
        anon = await client.get("/orders/1", params={"customer_hint": "nobody@example.com"})
        assert anon.status_code == 401
        ok = await client.get("/orders/1", params={"customer_hint": "andi@example.com"})
        assert ok.status_code == 200 and ok.json()["order_id"] == 1
        # Verified as Andi is not verified as Bunga -- order 3 is hers.
        hers = await client.get("/orders/3", params={"customer_hint": "andi@example.com"})
        assert hers.status_code == 404


async def test_chat_rejects_invalid_body(sessions: Sessions) -> None:
    async with serving(create_app(_settings(), sessions=sessions)) as client:
        response = await client.post("/chat", json={"session_id": "s1", "message": ""})
        assert response.status_code == 422


async def test_outcome_is_read_from_the_transcript_not_claimed(sessions: Sessions) -> None:
    """The scripted model never says it escalated -- it only writes prose. The response knows
    anyway, because escalation is read from what ran."""
    async with sessions() as session:
        expected_ticket = 1 + (await session.scalar(select(func.max(tables.Ticket.ticket_id))) or 0)

    settings = _settings()
    model = _script(
        (
            "create_ticket",
            {
                "category": "other",
                "priority": "high",
                "subject": "Minta agen manusia",
                "order_id": None,
            },
        ),
        ("escalate_ticket", {"ticket_id": expected_ticket, "reason": "minta manusia"}),
    )
    app = create_app(settings, sessions=sessions)
    async with serving(app) as client:
        with app.state.agent.override(model=model):
            response = await client.post(
                "/chat",
                json={
                    "session_id": "esc",
                    "customer_hint": "andi@example.com",
                    "message": "Saya mau bicara dengan manusia",
                },
            )

    body = response.json()
    assert body["message"] == REPLY  # the only thing the model produced
    assert body["escalated"] is True
    assert body["ticket_id"] == expected_ticket


async def test_a_crashed_run_is_persisted_once_not_duplicated(sessions: Sessions) -> None:
    """`capture_run_messages` hands back the whole run including the history it was given, so
    the salvage path slices; a bug there would re-insert every earlier turn.
    """

    def explode(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if sum(isinstance(m, ModelResponse) for m in messages):
            raise RuntimeError("groq is down")
        return ModelResponse(parts=[TextPart("halo")])

    settings = _settings()
    app = create_app(settings, sessions=sessions)
    async with serving(app) as client:
        with app.state.agent.override(model=FunctionModel(explode)):
            body = {"session_id": "boom", "customer_hint": None, "message": "halo"}
            assert (await client.post("/chat", json=body)).json()["message"] == "halo"
            crashed = await client.post("/chat", json=body)
            assert "sedang bermasalah" in crashed.json()["message"]

    async with sessions() as session:
        rows = (
            await session.scalars(
                select(tables.ConversationMessage)
                .where(tables.ConversationMessage.session_id == "boom")
                .order_by(tables.ConversationMessage.seq)
            )
        ).all()
    kinds = [r.kind for r in rows]
    assert kinds == ["request", "response", "request"], kinds
    assert len({r.seq for r in rows}) == 3, "the failed run re-inserted the earlier turn"
