"""One turn, start to finish. Identity and escalation signals are resolved before the agent
runs -- both are deterministic and belong outside the model's reach.

`prepare` and `finish` are shared with the streaming sibling.

A turn opens its own session scope rather than taking a FastAPI dependency: a streaming
response outlives dependency teardown, so that path would be handed a closed session.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import logfire
from pydantic_ai import Agent, UsageLimits, capture_run_messages
from pydantic_ai.messages import ModelMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ....data import tables
from ...capabilities.customers.schemas import Customer
from ...capabilities.customers.services import CustomerLookup
from ...capabilities.tickets import policies as ticket_policies
from ...shared import telemetry, transcript
from ...shared.database import Sessions, session_scope
from ...shared.message_store import MessageStore
from ...shared.settings import Settings
from .deps import SupportDeps
from .output import AgentReply

FALLBACK = AgentReply(
    message=(
        "Maaf, sistem kami sedang bermasalah sehingga saya belum bisa memeriksa data Anda. "
        "Silakan coba lagi sebentar lagi, atau balas 'hubungkan ke agen' supaya tim kami yang "
        "menindaklanjuti langsung."
    )
)


@dataclass
class Intake:
    """Everything gathered before the model runs. Named for the phase rather than for the turn:
    `Turn` already means a customer-visible exchange, on the wire and in the UI.
    """

    store: MessageStore
    history: list[ModelMessage]
    deps: SupportDeps
    metadata: dict[str, object]


async def resolve_customer(session: AsyncSession, hint: str | None) -> Customer | None:
    """An order id verifies nothing -- it is printed on the parcel."""
    if not hint:
        return None
    if hint.isdigit() and "@" not in hint and not hint.startswith("0"):
        return None
    return await CustomerLookup(session).by_contact(hint)


async def classify(session: AsyncSession, message: str, customer: Customer | None) -> list[str]:
    signals = ticket_policies.detect_signals(message)
    # Delivered on our side, never arrived on theirs: one of the two records is wrong and only
    # a human can find out which.
    if customer and ticket_policies.claims_not_received(message):
        delivered = await session.scalar(
            select(tables.Order.order_id).where(
                tables.Order.customer_id == customer.customer_id,
                tables.Order.status == "delivered",
            )
        )
        if delivered is not None:
            signals.append("data_inconsistency")
    return sorted(set(signals))


async def prepare(
    session: AsyncSession, *, session_id: str, message: str, customer_hint: str | None
) -> Intake:
    store = MessageStore(session)
    history = await store.load(session_id)
    customer = await resolve_customer(session, customer_hint)
    signals = await classify(session, message, customer)
    return Intake(
        store=store,
        history=history,
        deps=SupportDeps(session=session, customer=customer, escalation_signals=signals),
        # Lands on the `invoke_agent` span, where a trace viewer looks. It does not reach
        # `ModelMessage.metadata` -- that field stays null -- so the DB keeps its own columns.
        metadata={
            "session_id": session_id,
            "customer_id": customer.customer_id if customer else None,
            "escalation_signals": signals,
        },
    )


def run_args(intake: Intake, *, session_id: str, settings: Settings) -> dict[str, Any]:
    """Every argument both entry points hand the agent. Kept in one place because a difference
    between them would be a difference in behaviour that no test would name.
    """
    return {
        "deps": intake.deps,
        "message_history": intake.history,
        "conversation_id": session_id,
        "metadata": intake.metadata,
        "usage_limits": UsageLimits(
            request_limit=settings.request_limit,
            total_tokens_limit=settings.total_tokens_limit,
        ),
    }


async def finish(intake: Intake, result, *, session_id: str, message: str) -> AgentReply:
    escalated, ticket_id = transcript.outcome(result.all_messages())
    reply = AgentReply(
        message=result.output,
        # intake.deps.customer, not the opening value: the gate promotes mid-run when the customer
        # identifies themselves in conversation.
        customer_name=intake.deps.customer.full_name if intake.deps.customer else None,
        escalated=escalated,
        ticket_id=ticket_id,
    )
    telemetry.record_answer(
        reply.message,
        escalated=escalated,
        ticket_id=ticket_id,
        usage=result.usage,
        model=result.response.model_name,
    )
    await intake.store.append(session_id, result.new_messages())
    if intake.deps.customer is not None:
        await intake.deps.tickets.record_turn(
            intake.deps.customer.customer_id, ticket_id, message, reply.message
        )
    return reply


async def salvage(intake: Intake, captured: list[ModelMessage], session_id: str) -> None:
    """Keep what a crashed run produced -- without this the turn vanishes from the record.

    `capture_run_messages` hands back the history it was given as well, so the new messages are
    the tail. The window capability is what keeps a half-finished run out of the next request.
    """
    logfire.exception("agent run failed")
    telemetry.record_answer(FALLBACK.message, escalated=False, ticket_id=None)
    await intake.store.append(session_id, captured[len(intake.history) :])


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
        intake = await prepare(
            session, session_id=session_id, message=message, customer_hint=customer_hint
        )

        with logfire.span("chat turn") as span, capture_run_messages() as captured:
            telemetry.describe_turn(
                session_id=session_id,
                customer_id=intake.deps.customer.customer_id if intake.deps.customer else None,
                message=message,
                signals=intake.deps.escalation_signals,
                model=settings.model_name,
            )
            try:
                result = await agent.run(
                    message, **run_args(intake, session_id=session_id, settings=settings)
                )
            except Exception:  # noqa: BLE001
                # A customer-facing endpoint must never answer with a stack trace.
                span.set_attribute("failed", True)
                await salvage(intake, captured, session_id)
                return FALLBACK

        return await finish(intake, result, session_id=session_id, message=message)
