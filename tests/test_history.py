"""The model-facing window: whole runs only, and never a run that died mid-flight."""

from __future__ import annotations

from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    UserPromptPart,
)

from tokokita.agentic_system.agents.support.history import MAX_RUNS, recent_runs


def run_of(run_id: str, text: str) -> list:
    return [
        ModelRequest(parts=[UserPromptPart(content=text)], run_id=run_id),
        ModelResponse(parts=[TextPart(content=f"jawaban {text}")], run_id=run_id),
    ]


def test_window_drops_whole_runs_never_half_of_one() -> None:
    """Cutting mid-run would separate a tool call from its return."""
    messages = [m for i in range(MAX_RUNS + 3) for m in run_of(f"r{i}", f"pesan {i}")]

    kept = recent_runs(messages)
    assert len(kept) == MAX_RUNS * 2  # every kept run is intact
    assert kept[0].parts[0].content == "pesan 3"  # the three oldest runs fell off


def test_a_run_with_an_unanswered_call_is_never_replayed() -> None:
    """A crashed run can leave a tool call with no return; replaying it is a malformed request.

    `state` does not catch this -- the framework leaves it `complete` when the model call raised.
    """
    dead = [
        ModelRequest(parts=[UserPromptPart(content="gagal")], run_id="r2"),
        ModelResponse(parts=[ToolCallPart("get_order", {}, tool_call_id="c1")], run_id="r2"),
    ]
    messages = run_of("r1", "selesai") + dead + run_of("r3", "berikutnya")

    assert [m.run_id for m in recent_runs(messages)] == ["r1", "r1", "r3", "r3"]


def test_a_short_conversation_is_left_alone() -> None:
    messages = run_of("r1", "halo")
    assert recent_runs(messages) == messages
