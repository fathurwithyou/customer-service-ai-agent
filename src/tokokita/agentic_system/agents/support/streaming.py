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
from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import FunctionToolCallEvent, PartDeltaEvent, TextPartDelta

from ...shared import telemetry, transcript
from ...shared.database import Database
from ...shared.message_store import MessageStore
from .deps import SupportDeps
from .output import AgentReply
from .runner import FALLBACK, classify, resolve_customer


def event(name: str, data: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def stream_turn(
    agent: Agent[SupportDeps, str],
    db: Database,
    *,
    session_id: str,
    message: str,
    customer_hint: str | None,
    store: MessageStore,
    model_name: str,
    activity: dict[str, str],
) -> AsyncIterator[str]:
    history = await store.load(session_id)
    customer = await resolve_customer(db, customer_hint)
    deps = SupportDeps(
        db=db, customer=customer, escalation_signals=await classify(db, message, customer)
    )
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

    with logfire.span("chat turn") as span:
        telemetry.describe_turn(
            session_id=session_id,
            customer_id=customer.customer_id if customer else None,
            message=message,
            signals=deps.escalation_signals,
            model=model_name,
        )

        async def run() -> Any:
            try:
                return await agent.run(
                    message,
                    deps=deps,
                    message_history=history,
                    conversation_id=session_id,
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
            logfire.exception("agent run failed")
            span.set_attribute("failed", True)
            telemetry.record_answer(FALLBACK.message, escalated=False, ticket_id=None)
            yield event("delta", {"text": FALLBACK.message})
            yield event("done", FALLBACK.model_dump())
            return

        messages = result.all_messages()
        escalated, ticket_id = transcript.outcome(messages)
        reply = AgentReply(
            message=result.output,
            customer_name=deps.customer.full_name if deps.customer else None,
            escalated=escalated,
            ticket_id=ticket_id,
        )
        telemetry.record_answer(
            reply.message, escalated=escalated, ticket_id=ticket_id, usage=result.usage
        )

    await store.save(session_id, messages)
    if deps.customer is not None:
        await deps.tickets.record_turn(deps.customer.customer_id, ticket_id, message, reply.message)
    yield event("done", reply.model_dump())
