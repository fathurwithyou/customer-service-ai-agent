"""Everything a turn needs before the model runs, and how it finishes.

Both entry points share this: `runner.py` answers in one response, `streaming.py` emits the
same turn as events. Identity and escalation signals are resolved here rather than asked of the
model -- both are deterministic and belong outside its reach.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import logfire
from pydantic_ai import UsageLimits
from pydantic_ai.messages import ModelMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ....data import tables
from ...capabilities.customers.schemas import Customer
from ...capabilities.customers.services import CustomerLookup
from ...capabilities.tickets import policies as ticket_policies
from ...shared import telemetry, transcript
from ...shared.message_store import MessageStore
from ...shared.settings import Settings
from .deps import SupportDeps
from .output import FALLBACK, AgentReply


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


@dataclass
class Intake:
    """Named for the phase, not the turn: `Turn` already means a customer-visible exchange, on
    the wire and in the UI.
    """

    session_id: str
    message: str
    store: MessageStore
    history: list[ModelMessage]
    deps: SupportDeps
    metadata: dict[str, object]

    @classmethod
    async def prepare(
        cls, session: AsyncSession, *, session_id: str, message: str, customer_hint: str | None
    ) -> Intake:
        store = MessageStore(session)
        history = await store.load(session_id)
        customer = await resolve_customer(session, customer_hint)
        signals = await classify(session, message, customer)
        return cls(
            session_id=session_id,
            message=message,
            store=store,
            history=history,
            deps=SupportDeps(session=session, customer=customer, escalation_signals=signals),
            # Lands on the `invoke_agent` span, where a trace viewer looks. It does not reach
            # `ModelMessage.metadata` -- that field stays null -- so the DB keeps its columns.
            metadata={
                "session_id": session_id,
                "customer_id": customer.customer_id if customer else None,
                "escalation_signals": signals,
            },
        )

    @property
    def customer(self) -> Customer | None:
        return self.deps.customer

    def describe(self, settings: Settings) -> None:
        telemetry.describe_turn(
            session_id=self.session_id,
            customer_id=self.customer.customer_id if self.customer else None,
            message=self.message,
            signals=self.deps.escalation_signals,
            model=settings.model_name,
        )

    def run_args(self, settings: Settings) -> dict[str, Any]:
        """Every argument both entry points hand the agent. Kept in one place because a
        difference between them would be a difference in behaviour that no test would name.
        """
        return {
            "deps": self.deps,
            "message_history": self.history,
            "conversation_id": self.session_id,
            "metadata": self.metadata,
            "usage_limits": UsageLimits(
                request_limit=settings.request_limit,
                total_tokens_limit=settings.total_tokens_limit,
            ),
        }

    async def finish(self, result: Any) -> AgentReply:
        escalated, ticket_id = transcript.outcome(result.all_messages())
        reply = AgentReply(
            message=result.output,
            # self.customer, not the opening value: the gate promotes mid-run when the customer
            # identifies themselves in conversation.
            customer_name=self.customer.full_name if self.customer else None,
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
        await self.store.append(self.session_id, result.new_messages())
        if self.customer is not None:
            await self.deps.tickets.record_turn(
                self.customer.customer_id, ticket_id, self.message, reply.message
            )
        return reply

    async def salvage(self, captured: list[ModelMessage]) -> None:
        """Keep what a crashed run produced -- without this the turn vanishes from the record.

        `capture_run_messages` hands back the history it was given as well, so the new messages
        are the tail. The window capability keeps a half-finished run out of the next request.
        """
        logfire.exception("agent run failed")
        telemetry.record_answer(FALLBACK.message, escalated=False, ticket_id=None)
        await self.store.append(self.session_id, captured[len(self.history) :])
