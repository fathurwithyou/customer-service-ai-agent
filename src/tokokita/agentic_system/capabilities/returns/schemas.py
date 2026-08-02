from __future__ import annotations

from pydantic import Field

from ...shared.from_row import FromRow


class ReturnRequest(FromRow):
    return_id: int
    order_id: int
    product_id: int
    reason: str
    refund_amount: float = Field(ge=0)
