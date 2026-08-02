from __future__ import annotations

from pydantic import Field

from ...shared.from_row import FromRow


class Product(FromRow):
    product_id: int
    name: str
    category: str | None = None
    price: float = Field(ge=0)
    stock_qty: int = Field(ge=0)
    description: str | None = None
