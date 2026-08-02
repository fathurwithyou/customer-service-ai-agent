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

from tokokita.agentic_system.shared.database import Database
from tokokita.agentic_system.shared.message_store import MAX_RUNS, MessageStore

pytestmark = pytest.mark.anyio


def run_of(run_id: str, text: str) -> list:
    return [
        ModelRequest(parts=[UserPromptPart(content=text)], run_id=run_id),
        ModelResponse(parts=[TextPart(content=f"jawaban {text}")], run_id=run_id),
    ]


async def test_append_does_not_rewrite_earlier_turns(db: Database) -> None:
    store = MessageStore(db)
    await store.append("s", run_of("r1", "satu"))
    await store.append("s", run_of("r2", "dua"))

    rows = await db._all("SELECT seq, run_id FROM conversation_messages WHERE session_id='s'")
    assert [r["seq"] for r in rows] == [1, 2, 3, 4]
    assert [r["run_id"] for r in rows] == ["r1", "r1", "r2", "r2"]


async def test_load_round_trips_through_the_framework_format(db: Database) -> None:
    store = MessageStore(db)
    await store.append("s", run_of("r1", "halo"))
    loaded = await store.load("s")
    assert [type(m).__name__ for m in loaded] == ["ModelRequest", "ModelResponse"]
    assert loaded[0].parts[0].content == "halo"
    assert loaded[1].parts[0].content == "jawaban halo"


async def test_window_drops_whole_runs_never_half_of_one(db: Database) -> None:
    """Cutting mid-run would separate a tool call from its return."""
    store = MessageStore(db)
    for i in range(MAX_RUNS + 3):
        await store.append("s", run_of(f"r{i}", f"pesan {i}"))

    loaded = await store.load("s")
    assert len(loaded) == MAX_RUNS * 2  # every kept run is intact
    assert loaded[0].parts[0].content == f"pesan {3}"  # the three oldest runs fell off


async def test_sessions_do_not_bleed(db: Database) -> None:
    store = MessageStore(db)
    await store.append("a", run_of("r1", "milik a"))
    await store.append("b", run_of("r2", "milik b"))
    assert (await store.load("a"))[0].parts[0].content == "milik a"
    assert (await store.load("b"))[0].parts[0].content == "milik b"


async def test_system_prompts_are_not_stored(db: Database) -> None:
    store = MessageStore(db)
    await store.append(
        "s",
        [
            ModelRequest(
                parts=[SystemPromptPart(content="rahasia"), UserPromptPart(content="halo")],
                run_id="r1",
            )
        ],
    )
    row = await db._one("SELECT payload FROM conversation_messages WHERE session_id='s'")
    assert "rahasia" not in row["payload"]
