"""One turn, answered in a single response.

The turn opens its own session scope rather than taking a FastAPI dependency: the streaming
sibling outlives dependency teardown, and both paths should behave the same way.
"""

from __future__ import annotations

import logfire
from pydantic_ai import Agent, capture_run_messages

from ...shared.database import Sessions, session_scope
from ...shared.settings import Settings
from .deps import SupportDeps
from .intake import Intake
from .output import FALLBACK, AgentReply


async def run_turn(
    agent: Agent[SupportDeps, str],
    sessions: Sessions,
    *,
    session_id: str,
    message: str,
    customer_hint: str | None,
    settings: Settings,
) -> AgentReply:
    async with session_scope(sessions) as session:
        intake = await Intake.prepare(
            session, session_id=session_id, message=message, customer_hint=customer_hint
        )

        with logfire.span("chat turn") as span, capture_run_messages() as captured:
            intake.describe(settings)
            try:
                result = await agent.run(message, **intake.run_args(settings))
            except Exception:  # noqa: BLE001
                # A customer-facing endpoint must never answer with a stack trace.
                span.set_attribute("failed", True)
                await intake.salvage(captured)
                return FALLBACK

        return await intake.finish(result)
