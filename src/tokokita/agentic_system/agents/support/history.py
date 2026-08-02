"""What the model sees, which is less than what we store.

Runs, not messages: cutting mid-run separates a tool call from its return.
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
