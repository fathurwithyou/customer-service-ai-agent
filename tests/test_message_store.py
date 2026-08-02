"""The store keeps whole runs, appends rather than rewrites, and survives a part type it has
never seen -- the payload is the framework's own format, not ours.
"""

from __future__ import annotations

import pytest
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    UserPromptPart,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tokokita.agentic_system.shared.message_store import MessageStore
from tokokita.data import tables

pytestmark = pytest.mark.anyio


def run_of(run_id: str, text: str) -> list:
    return [
        ModelRequest(parts=[UserPromptPart(content=text)], run_id=run_id),
        ModelResponse(parts=[TextPart(content=f"jawaban {text}")], run_id=run_id),
    ]


async def test_append_does_not_rewrite_earlier_turns(session: AsyncSession) -> None:
    store = MessageStore(session)
    await store.append("s", run_of("r1", "satu"))
    await store.append("s", run_of("r2", "dua"))

    rows = (
        await session.scalars(
            select(tables.ConversationMessage)
            .where(tables.ConversationMessage.session_id == "s")
            .order_by(tables.ConversationMessage.seq)
        )
    ).all()
    assert [r.seq for r in rows] == [1, 2, 3, 4]
    assert [r.run_id for r in rows] == ["r1", "r1", "r2", "r2"]


async def test_load_round_trips_through_the_framework_format(session: AsyncSession) -> None:
    store = MessageStore(session)
    await store.append("s", run_of("r1", "halo"))
    loaded = await store.load("s")
    assert [type(m).__name__ for m in loaded] == ["ModelRequest", "ModelResponse"]
    assert loaded[0].parts[0].content == "halo"
    assert loaded[1].parts[0].content == "jawaban halo"


async def test_nothing_is_windowed_away_on_the_way_out(session: AsyncSession) -> None:
    """The store is the audit record; trimming is the window capability's job."""
    store = MessageStore(session)
    for i in range(20):
        await store.append("s", run_of(f"r{i}", f"pesan {i}"))

    loaded = await store.load("s")
    assert len(loaded) == 40
    assert loaded[0].parts[0].content == "pesan 0"


async def test_sessions_do_not_bleed(session: AsyncSession) -> None:
    store = MessageStore(session)
    await store.append("a", run_of("r1", "milik a"))
    await store.append("b", run_of("r2", "milik b"))
    assert (await store.load("a"))[0].parts[0].content == "milik a"
    assert (await store.load("b"))[0].parts[0].content == "milik b"


async def test_system_prompts_are_not_stored(session: AsyncSession) -> None:
    """Instructions are re-injected every run, so a stored one is only a stale copy waiting to
    be replayed. The framework warns when it strips them; that warning is the assertion.
    """
    store = MessageStore(session)
    with pytest.warns(UserWarning, match="system prompts were stripped"):
        await store.append(
            "s",
            [
                ModelRequest(
                    parts=[SystemPromptPart(content="rahasia"), UserPromptPart(content="halo")],
                    run_id="r1",
                )
            ],
        )
    payload = await session.scalar(
        select(tables.ConversationMessage.payload).where(
            tables.ConversationMessage.session_id == "s"
        )
    )
    assert [type(p).__name__ for p in payload.parts] == ["UserPromptPart"]

