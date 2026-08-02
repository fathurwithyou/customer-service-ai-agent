"""Stream a turn as server-sent events.

One handler feeds a queue because `event_stream_handler` is a callback and cannot yield into
the response; that also preserves the run's ordering of tool activity and text.

Deltas are coalesced to words so the client animates a word at a time, not a character. The
outcome is only known after the run, so it arrives in a final `done` event.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import logfire
from pydantic_ai import Agent, RunContext, capture_run_messages
from pydantic_ai.messages import FunctionToolCallEvent, PartDeltaEvent, TextPartDelta

from ...shared import telemetry
from ...shared.database import Sessions, session_scope
from ...shared.settings import Settings
from .deps import SupportDeps
from .runner import FALLBACK, finish, limits, prepare, salvage


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
        turn = await prepare(
            session, session_id=session_id, message=message, customer_hint=customer_hint
        )
        customer = turn.deps.customer
        yield event("start", {"customer_name": customer.full_name if customer else None})

        queue: asyncio.Queue[tuple[str, dict] | None] = asyncio.Queue()

        async def on_event(_: RunContext[SupportDeps], events: Any) -> None:
            held = ""
            async for item in events:
                if isinstance(item, FunctionToolCallEvent):
                    label = activity.get(item.part.tool_name)
                    if label:
                        await queue.put(("tool", {"label": label}))
                elif isinstance(item, PartDeltaEvent) and isinstance(item.delta, TextPartDelta):
                    held += item.delta.content_delta
                    cut = held.rfind(" ")
                    if cut != -1:
                        await queue.put(("delta", {"text": held[: cut + 1]}))
                        held = held[cut + 1 :]
            if held:
                await queue.put(("delta", {"text": held}))

        with logfire.span("chat turn") as span, capture_run_messages() as captured:
            telemetry.describe_turn(
                session_id=session_id,
                customer_id=customer.customer_id if customer else None,
                message=message,
                signals=turn.deps.escalation_signals,
                model=settings.model_name,
            )

            async def run() -> Any:
                try:
                    return await agent.run(
                        message,
                        deps=turn.deps,
                        message_history=turn.history,
                        conversation_id=session_id,
                        metadata=turn.metadata,
                        usage_limits=limits(settings),
                        event_stream_handler=on_event,
                    )
                finally:
                    await queue.put(None)

            task = asyncio.create_task(run())
            while (item := await queue.get()) is not None:
                yield event(*item)

            try:
                result = await task
            except Exception:  # noqa: BLE001
                span.set_attribute("failed", True)
                await salvage(turn, captured, session_id)
                yield event("delta", {"text": FALLBACK.message})
                yield event("done", FALLBACK.model_dump())
                return

        reply = await finish(turn, result, session_id=session_id, message=message)
        yield event("done", reply.model_dump())
