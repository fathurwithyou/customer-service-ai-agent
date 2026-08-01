from __future__ import annotations

from ...shared.database import Database
from .schemas import Ticket, TicketCategory, TicketPriority


class TicketService:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def open(
        self,
        *,
        customer_id: int,
        order_id: int | None,
        category: TicketCategory,
        priority: TicketPriority,
        subject: str,
    ) -> Ticket:
        ticket_id = await self._db.insert_ticket(
            customer_id, order_id, category.value, priority.value, subject
        )
        return Ticket(
            ticket_id=ticket_id,
            order_id=order_id,
            category=category,
            priority=priority,
            subject=subject,
        )

    async def escalate(self, ticket_id: int, customer_id: int) -> bool:
        return await self._db.mark_ticket_escalated(ticket_id, customer_id)

    async def record_turn(self, customer_id: int, ticket_id: int | None, *texts: str) -> None:
        ticket_id = ticket_id or await self._db.open_ticket_id(customer_id)
        if ticket_id is None:
            return
        for sender, text in zip(("customer", "ai"), texts, strict=False):
            await self._db.insert_ticket_message(ticket_id, sender, text)
