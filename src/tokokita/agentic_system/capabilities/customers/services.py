from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ....data import tables
from .schemas import Customer


class CustomerLookup:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def by_contact(self, contact: str) -> Customer | None:
        contact = contact.strip()
        row = await self._session.scalar(
            select(tables.Customer).where(
                or_(tables.Customer.email.ilike(contact), tables.Customer.phone == contact)
            )
        )
        return Customer.model_validate(row) if row else None
