"""One turn, start to finish.

Resolving identity and classifying the message happen here, before the agent runs, because
both are deterministic and belong in code the model cannot influence.
"""

from __future__ import annotations

import logfire
from pydantic_ai import Agent

from ...capabilities.customers.schemas import Customer
from ...capabilities.customers.services import CustomerLookup
from ...capabilities.tickets import policies as ticket_policies
from ...shared import telemetry, transcript
from ...shared.database import Database
from ...shared.message_store import MessageStore
from .deps import SupportDeps
from .output import AgentReply

FALLBACK = AgentReply(
    message=(
        "Maaf, sistem kami sedang bermasalah sehingga saya belum bisa memeriksa data Anda. "
        "Silakan coba lagi sebentar lagi, atau balas 'hubungkan ke agen' supaya tim kami yang "
        "menindaklanjuti langsung."
    )
)


async def resolve_customer(db: Database, hint: str | None) -> Customer | None:
    """An order-id hint verifies nothing: honouring one would make a shipping label a
    credential."""
    if not hint:
        return None
    if hint.isdigit() and "@" not in hint and not hint.startswith("0"):
        return None
    return await CustomerLookup(db).by_contact(hint)


async def classify(db: Database, message: str, customer: Customer | None) -> list[str]:
    signals = ticket_policies.detect_signals(message)
    # Delivered on our side, never arrived on theirs: one of the two records is wrong and only
    # a human can find out which.
    if customer and ticket_policies.claims_not_received(message):
        rows = await db.order_rows(customer.customer_id)
        if any(row["status"] == "delivered" for row in rows):
            signals.append("data_inconsistency")
    return sorted(set(signals))


async def run_turn(
    agent: Agent[SupportDeps, str],
    db: Database,
    *,
    session_id: str,
    message: str,
    customer_hint: str | None,
    store: MessageStore,
    model_name: str,
) -> AgentReply:
    history = await store.load(session_id)
    customer = await resolve_customer(db, customer_hint)
    deps = SupportDeps(
        db=db, customer=customer, escalation_signals=await classify(db, message, customer)
    )

    with logfire.span("chat turn") as span:
        telemetry.describe_turn(
            session_id=session_id,
            customer_id=customer.customer_id if customer else None,
            message=message,
            signals=deps.escalation_signals,
            model=model_name,
        )
        try:
            result = await agent.run(
                message, deps=deps, message_history=history, conversation_id=session_id
            )
        except Exception:  # noqa: BLE001
            # A customer-facing endpoint must never answer with a stack trace.
            logfire.exception("agent run failed")
            span.set_attribute("failed", True)
            telemetry.record_answer(FALLBACK.message, escalated=False, ticket_id=None)
            return FALLBACK

        escalated, ticket_id = transcript.outcome(result.all_messages())
        reply = AgentReply(
            message=result.output,
            # deps.customer, not the turn's opening value: the gate promotes mid-run when the
            # customer identifies themselves in conversation.
            customer_name=deps.customer.full_name if deps.customer else None,
            escalated=escalated,
            ticket_id=ticket_id,
        )
        telemetry.record_answer(
            reply.message, escalated=escalated, ticket_id=ticket_id, usage=result.usage
        )

    await store.save(session_id, result.all_messages())
    if customer is not None:
        await deps.tickets.record_turn(
            customer.customer_id, reply.ticket_id, message, reply.message
        )
    return reply
