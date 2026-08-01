from __future__ import annotations

from ...shared.database import Database
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
    def __init__(self, db: Database) -> None:
        self._db = db

    async def list_for(self, customer_id: int) -> list[OrderSummary]:
        return [OrderSummary(**row) for row in await self._db.order_rows(customer_id)]

    async def detail(self, order_id: int, customer_id: int) -> OrderDetail | None:
        row = await self._db.order_row(order_id, customer_id)
        if row is None:
            return None
        payment = await self._db.payment_row(order_id, customer_id)
        shipment = await self._db.shipment_row(order_id, customer_id)
        items = await self._db.order_item_rows(order_id, customer_id)
        return OrderDetail(
            order_id=row["order_id"],
            status=OrderStatus(row["status"]),
            order_date=row["order_date"],
            total_amount=row["total_amount"] or 0.0,
            shipping_address=row["shipping_address"],
            payment_method=row["payment_method"],
            payment_status=PaymentStatus(payment["status"]) if payment else None,
            paid_at=payment["paid_at"] if payment else None,
            items=[OrderItem(**item) for item in items],
            shipment=Shipment(**shipment) if shipment else None,
        )

    async def shipment(self, order_id: int, customer_id: int) -> Shipment | None:
        row = await self._db.shipment_row(order_id, customer_id)
        return Shipment(**row) if row else None

    async def change_address(
        self, order_id: int, customer_id: int, address: str
    ) -> ActionResult | None:
        """None means the order is not this customer's; the caller turns that into a retry."""
        row = await self._db.order_row(order_id, customer_id)
        if row is None:
            return None
        decision = policies.can_change_address(OrderStatus(row["status"]))
        if not decision.allowed:
            # Name the courier for THIS order, or the model will name one it remembers from an
            # earlier turn -- the exact way a wrong tracking number reaches a customer.
            shipment = await self._db.shipment_row(order_id, customer_id)
            detail = decision.detail
            if shipment and shipment["tracking_number"]:
                detail += (
                    f" Paket ini dikirim lewat {shipment['courier']} dengan nomor resi "
                    f"{shipment['tracking_number']}."
                )
            return ActionResult(code=decision.code, detail=detail)
        await self._db.set_shipping_address(order_id, customer_id, address.strip())
        return ActionResult(
            code=ResultCode.OK, detail=f"Alamat pengiriman pesanan {order_id} sudah diperbarui."
        )
