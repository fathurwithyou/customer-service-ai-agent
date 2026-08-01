from __future__ import annotations

from pydantic import BaseModel, Field


class Product(BaseModel):
    product_id: int
    name: str
    category: str | None = None
    price: float = Field(ge=0)
    stock_qty: int = Field(ge=0)
    description: str | None = None
