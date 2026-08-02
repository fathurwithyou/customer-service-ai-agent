"""What the model sees, which is less than what we store.

Windowing belongs to the agent, not to the store, so it is a `ProcessHistory` capability rather
than a clause in the load query.

The window counts runs, not messages: cutting mid-run would separate a tool call from its
return. A run that died mid-flight is dropped for the same reason -- it can hold a call with no
return, and replaying that is a malformed request. `state` alone does not catch this: the
framework only writes `interrupted` when a tool was cancelled, not when the model call itself
raised, so the test is whether every call in the run was answered.
"""

from __future__ import annotations

from pydantic_ai.capabilities import ProcessHistory
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    ToolCallPart,
    ToolReturnPart,
)

MAX_RUNS = 12


def answered(run: list[ModelMessage]) -> bool:
    calls = {
        part.tool_call_id
        for message in run
        if isinstance(message, ModelResponse)
        for part in message.parts
        if isinstance(part, ToolCallPart)
    }
    returns = {
        part.tool_call_id
        for message in run
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, ToolReturnPart | RetryPromptPart)
    }
    return calls <= returns


def recent_runs(messages: list[ModelMessage]) -> list[ModelMessage]:
    runs: list[list[ModelMessage]] = []
    for message in messages:
        if not runs or runs[-1][0].run_id != message.run_id:
            runs.append([])
        runs[-1].append(message)
    # The last run is the one in flight: its calls are answered as it goes, so it is never judged.
    kept = [run for run in runs[:-1] if answered(run)] + runs[-1:]
    return [message for run in kept[-MAX_RUNS:] for message in run]


WINDOW = ProcessHistory(recent_runs, description="Keep the last few complete runs.")
