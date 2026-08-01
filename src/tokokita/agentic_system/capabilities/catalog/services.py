"""The public catalog. Nothing here belongs to a customer, so nothing here is scoped."""

from __future__ import annotations

from ...shared.database import Database
from .schemas import Product


class CatalogService:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def find(self, *, product_id: int | None, name: str | None) -> Product | None:
        row = await self._db.product_row(product_id=product_id, name=name)
        return Product(**row) if row else None
