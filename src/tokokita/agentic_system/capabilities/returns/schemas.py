from __future__ import annotations

from pydantic import BaseModel, Field


class ReturnRequest(BaseModel):
    return_id: int
    order_id: int
    product_id: int
    reason: str
    refund_amount: float = Field(ge=0)
