"""Order reads and the address rule. Every query takes a customer_id and filters on it."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ....data import tables
from ...shared.results import ActionResult, ResultCode
from . import policies
from .schemas import OrderDetail, OrderStatus, OrderSummary, Shipment


class OrderService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _owned(self, order_id: int, customer_id: int):
        return select(tables.Order).where(
            tables.Order.order_id == order_id, tables.Order.customer_id == customer_id
        )

    async def list_for(self, customer_id: int) -> list[OrderSummary]:
        rows = await self._session.scalars(
            select(tables.Order)
            .where(tables.Order.customer_id == customer_id)
            .order_by(tables.Order.order_id)
        )
        return [OrderSummary.model_validate(row) for row in rows]

    async def detail(self, order_id: int, customer_id: int) -> OrderDetail | None:
        order = await self._session.scalar(
            self._owned(order_id, customer_id).options(
                selectinload(tables.Order.items).selectinload(tables.OrderItem.product),
                selectinload(tables.Order.shipment),
                selectinload(tables.Order.payment),
            )
        )
        return OrderDetail.model_validate(order) if order else None

    async def shipment(self, order_id: int, customer_id: int) -> Shipment | None:
        row = await self._session.scalar(
            select(tables.Shipment)
            .join(tables.Order, tables.Order.order_id == tables.Shipment.order_id)
            .where(
                tables.Shipment.order_id == order_id, tables.Order.customer_id == customer_id
            )
        )
        return Shipment.model_validate(row) if row else None

    async def change_address(
        self, order_id: int, customer_id: int, address: str
    ) -> ActionResult | None:
        """None means the order is not this customer's; the caller turns that into a retry."""
        order = await self._session.scalar(self._owned(order_id, customer_id))
        if order is None:
            return None
        decision = policies.can_change_address(OrderStatus(order.status))
        if not decision.allowed:
            # Name this order's courier, or the model quotes one it remembers from an
            # earlier turn.
            shipment = await self.shipment(order_id, customer_id)
            detail = decision.detail
            if shipment and shipment.tracking_number:
                detail += (
                    f" Paket ini dikirim lewat {shipment.courier} dengan nomor resi "
                    f"{shipment.tracking_number}."
                )
            return ActionResult(code=decision.code, detail=detail)
        order.shipping_address = address.strip()
        await self._session.commit()
        return ActionResult(
            code=ResultCode.OK, detail=f"Alamat pengiriman pesanan {order_id} sudah diperbarui."
        )
