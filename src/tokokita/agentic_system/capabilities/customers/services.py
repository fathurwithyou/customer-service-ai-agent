from __future__ import annotations

from ...shared.database import Database
from .schemas import Customer


class CustomerLookup:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def by_contact(self, contact: str) -> Customer | None:
        row = await self._db.customer_row(contact.strip())
        return Customer(**row) if row else None
