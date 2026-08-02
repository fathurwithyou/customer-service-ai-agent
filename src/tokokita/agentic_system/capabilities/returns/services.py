"""The refund amount is derived from `order_items`, never accepted as an argument -- otherwise
the ceiling would be checking a number the guarded party chose.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ....data import tables
from ...shared.results import ActionResult, ResultCode
from . import policies
from .schemas import ReturnRequest


class ReturnService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def request(
        self, *, order_id: int, product_id: int, reason: str, customer_id: int
    ) -> ReturnRequest | ActionResult | None:
        """None means that product is not on that order; the caller turns it into a retry."""
        refund = await self._session.scalar(
            select(tables.OrderItem.quantity * tables.OrderItem.unit_price)
            .join(tables.Order, tables.Order.order_id == tables.OrderItem.order_id)
            .where(
                tables.OrderItem.order_id == order_id,
                tables.OrderItem.product_id == product_id,
                tables.Order.customer_id == customer_id,
            )
        )
        if refund is None:
            return None
        if policies.requires_escalation(refund):
            return ActionResult(
                code=ResultCode.REFUND_EXCEEDS_LIMIT,
                detail=(
                    f"Nilai refund Rp {refund:,.0f} melebihi batas yang bisa saya proses "
                    "sendiri. Pengajuan belum dibuat -- eskalasikan ke tim manusia dengan "
                    "escalate_ticket."
                ),
            )
        row = tables.Return(
            order_id=order_id, product_id=product_id, reason=reason, refund_amount=refund
        )
        self._session.add(row)
        await self._session.commit()
        return ReturnRequest(
            return_id=row.return_id,
            order_id=order_id,
            product_id=product_id,
            reason=reason,
            refund_amount=refund,
        )
