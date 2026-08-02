"""Order reads and the address rule. Every query takes a customer_id and filters on it."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ....data import tables
from ...shared.results import ActionResult, ResultCode
from . import policies
from .schemas import (
    OrderDetail,
    OrderItem,
    OrderStatus,
    OrderSummary,
    PaymentStatus,
    Shipment,
)


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
        return [
            OrderSummary(
                order_id=r.order_id,
                order_date=str(r.order_date),
                status=OrderStatus(r.status),
                total_amount=r.total_amount or 0.0,
            )
            for r in rows
        ]

    async def detail(self, order_id: int, customer_id: int) -> OrderDetail | None:
        order = await self._session.scalar(self._owned(order_id, customer_id))
        if order is None:
            return None
        payment = await self._session.scalar(
            select(tables.Payment).where(tables.Payment.order_id == order_id)
        )
        lines = (
            await self._session.execute(
                select(tables.OrderItem, tables.Product.name)
                .join(tables.Product, tables.Product.product_id == tables.OrderItem.product_id)
                .where(tables.OrderItem.order_id == order_id)
            )
        ).all()
        return OrderDetail(
            order_id=order.order_id,
            status=OrderStatus(order.status),
            order_date=str(order.order_date),
            total_amount=order.total_amount or 0.0,
            shipping_address=order.shipping_address,
            payment_method=order.payment_method,
            payment_status=PaymentStatus(payment.status) if payment and payment.status else None,
            paid_at=payment.paid_at if payment else None,
            items=[
                OrderItem(
                    product_id=line.product_id,
                    product_name=name,
                    quantity=line.quantity,
                    unit_price=line.unit_price,
                )
                for line, name in lines
            ],
            shipment=await self.shipment(order_id, customer_id),
        )

    async def shipment(self, order_id: int, customer_id: int) -> Shipment | None:
        row = await self._session.scalar(
            select(tables.Shipment)
            .join(tables.Order, tables.Order.order_id == tables.Shipment.order_id)
            .where(
                tables.Shipment.order_id == order_id, tables.Order.customer_id == customer_id
            )
        )
        return Shipment.model_validate(row, from_attributes=True) if row else None

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
