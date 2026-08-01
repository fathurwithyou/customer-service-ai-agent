"""The HTTP surface end to end. `FunctionModel` fixes which tools the agent calls, so a reply
can be checked for *grounding* rather than for whether a sampled completion looked right.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from tokokita.agentic_system.agents.support.agent import build_agent
from tokokita.agentic_system.shared.database import Database
from tokokita.agentic_system.shared.settings import Settings
from tokokita.api.app import create_app

REPLY = "Pesanan 1 sedang dikirim JNE, resi JNE0012345678."

pytestmark = pytest.mark.anyio


def _settings() -> Settings:
    return Settings(groq_api_key=None, phoenix_endpoint="", database_path=":memory:")


def _script(*calls: tuple[str, dict]) -> FunctionModel:
    def model_fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        step = sum(isinstance(m, ModelResponse) for m in messages)
        if step < len(calls):
            name, args = calls[step]
            return ModelResponse(parts=[ToolCallPart(name, args)])
        return ModelResponse(parts=[TextPart(REPLY)])

    return FunctionModel(model_fn)


async def test_health(db: Database) -> None:
    with TestClient(create_app(_settings(), db=db)) as client:
        assert client.get("/health").json() == {"status": "ok"}


async def test_where_is_my_order_is_grounded_in_tool_calls(db: Database) -> None:
    """Acceptance criterion 3: the reply is built from get_order_detail + track_shipment."""
    settings = _settings()
    model = _script(("get_order_detail", {"order_id": 1}), ("track_shipment", {"order_id": 1}))
    app = create_app(settings, db=db)
    with TestClient(app) as client:
        app.state.agent = build_agent(settings, model=model)
        response = client.post(
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


async def test_debug_order_endpoint_requires_verification(db: Database) -> None:
    """Acceptance criterion 4, at the HTTP layer: no identity, no data."""
    with TestClient(create_app(_settings(), db=db)) as client:
        anon = client.get("/orders/1", params={"customer_hint": "nobody@example.com"})
        assert anon.status_code == 401
        ok = client.get("/orders/1", params={"customer_hint": "andi@example.com"})
        assert ok.status_code == 200 and ok.json()["order_id"] == 1
        # Verified as Andi is not verified as Bunga -- order 3 is hers.
        hers = client.get("/orders/3", params={"customer_hint": "andi@example.com"})
        assert hers.status_code == 404


async def test_chat_rejects_invalid_body(db: Database) -> None:
    with TestClient(create_app(_settings(), db=db)) as client:
        assert client.post("/chat", json={"session_id": "s1", "message": ""}).status_code == 422


async def test_outcome_is_read_from_the_transcript_not_claimed(db: Database) -> None:
    """The scripted model never says it escalated -- it only writes prose. The response knows
    anyway, because escalation is read from what ran."""
    row = await db._db.execute("SELECT COALESCE(MAX(ticket_id), 0) + 1 FROM tickets")
    expected_ticket = (await row.fetchone())[0]

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
    app = create_app(settings, db=db)
    with TestClient(app) as client:
        app.state.agent = build_agent(settings, model=model)
        body = client.post(
            "/chat",
            json={
                "session_id": "esc",
                "customer_hint": "andi@example.com",
                "message": "Saya mau bicara dengan manusia",
            },
        ).json()

    assert body["message"] == REPLY  # the only thing the model produced
    assert body["escalated"] is True
    assert body["ticket_id"] == expected_ticket
