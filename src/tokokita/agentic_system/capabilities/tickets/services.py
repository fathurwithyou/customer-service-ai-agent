from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ....data import tables
from .schemas import Ticket, TicketCategory, TicketPriority


class TicketService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def open(
        self,
        *,
        customer_id: int,
        order_id: int | None,
        category: TicketCategory,
        priority: TicketPriority,
        subject: str,
    ) -> Ticket:
        row = tables.Ticket(
            customer_id=customer_id,
            order_id=order_id,
            category=category.value,
            priority=priority.value,
            subject=subject,
        )
        self._session.add(row)
        await self._session.commit()
        return Ticket(
            ticket_id=row.ticket_id,
            order_id=order_id,
            category=category,
            priority=priority,
            subject=subject,
        )

    async def escalate(self, ticket_id: int, customer_id: int) -> bool:
        result = await self._session.execute(
            update(tables.Ticket)
            .where(
                tables.Ticket.ticket_id == ticket_id,
                tables.Ticket.customer_id == customer_id,
            )
            .values(status="escalated", priority="urgent")
        )
        await self._session.commit()
        return result.rowcount > 0

    async def record_turn(self, customer_id: int, ticket_id: int | None, *texts: str) -> None:
        if ticket_id is None:
            ticket_id = await self._session.scalar(
                select(tables.Ticket.ticket_id)
                .where(
                    tables.Ticket.customer_id == customer_id,
                    tables.Ticket.status.in_(("open", "pending", "escalated")),
                )
                .order_by(tables.Ticket.ticket_id.desc())
                .limit(1)
            )
        if ticket_id is None:
            return
        for sender, text in zip(("customer", "ai"), texts, strict=False):
            self._session.add(
                tables.TicketMessage(ticket_id=ticket_id, sender=sender, message=text)
            )
        await self._session.commit()
