"""The public catalog. Nothing here belongs to a customer, so nothing here is scoped."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ....data import tables
from .schemas import Product


class CatalogService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find(self, *, product_id: int | None, name: str | None) -> Product | None:
        query = select(tables.Product)
        if product_id is not None:
            query = query.where(tables.Product.product_id == product_id)
        elif name:
            query = query.where(tables.Product.name.ilike(f"%{name}%")).limit(1)
        else:
            return None
        row = await self._session.scalar(query)
        return Product.model_validate(row, from_attributes=True) if row else None
