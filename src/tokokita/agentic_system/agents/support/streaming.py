"""The same turn as server-sent events.

Deltas are coalesced to words: character-level deltas flicker. The outcome is only known once
the run is over, so it arrives in a final `done` event.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import logfire
from pydantic_ai import Agent, AgentRunResultEvent, capture_run_messages
from pydantic_ai.messages import FunctionToolCallEvent, PartDeltaEvent, TextPartDelta

from ...shared.database import Sessions, session_scope
from ...shared.settings import Settings
from .deps import SupportDeps
from .intake import Intake
from .output import FALLBACK


def event(name: str, data: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def stream_turn(
    agent: Agent[SupportDeps, str],
    sessions: Sessions,
    *,
    session_id: str,
    message: str,
    customer_hint: str | None,
    settings: Settings,
    activity: dict[str, str],
) -> AsyncIterator[str]:
    async with session_scope(sessions) as session:
        intake = await Intake.prepare(
            session, session_id=session_id, message=message, customer_hint=customer_hint
        )
        customer = intake.customer
        yield event("start", {"customer_name": customer.full_name if customer else None})

        with logfire.span("chat turn") as span, capture_run_messages() as captured:
            intake.describe(settings)
            held = ""
            try:
                async with agent.run_stream_events(
                    message, **intake.run_args(settings)
                ) as events:
                    async for item in events:
                        if isinstance(item, FunctionToolCallEvent):
                            if label := activity.get(item.part.tool_name):
                                yield event("tool", {"label": label})
                        elif isinstance(item, PartDeltaEvent) and isinstance(
                            item.delta, TextPartDelta
                        ):
                            held += item.delta.content_delta
                            if (cut := held.rfind(" ")) != -1:
                                yield event("delta", {"text": held[: cut + 1]})
                                held = held[cut + 1 :]
                        elif isinstance(item, AgentRunResultEvent):
                            result = item.result
                if held:
                    yield event("delta", {"text": held})
            except Exception:  # noqa: BLE001
                span.set_attribute("failed", True)
                await intake.salvage(captured)
                yield event("delta", {"text": FALLBACK.message})
                yield event("done", FALLBACK.model_dump())
                return

        reply = await intake.finish(result)
        yield event("done", reply.model_dump())
