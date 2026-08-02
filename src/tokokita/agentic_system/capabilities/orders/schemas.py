from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Annotated

from pydantic import AliasPath, BeforeValidator, Field

from ...shared.from_row import FromRow

# The brief's schema allows a null total; a customer-facing number cannot be null.
Amount = Annotated[float, BeforeValidator(lambda v: v or 0.0), Field(ge=0)]


class OrderStatus(StrEnum):
    PENDING = "pending"
    PAID = "paid"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class ShipmentStatus(StrEnum):
    PICKED_UP = "picked_up"
    IN_TRANSIT = "in_transit"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    FAILED = "failed"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    REFUNDED = "refunded"


class OrderSummary(FromRow):
    order_id: int
    order_date: datetime | None = None
    status: OrderStatus
    total_amount: Amount = 0.0


class OrderItem(FromRow):
    product_id: int
    product_name: str = Field(validation_alias=AliasPath("product", "name"))
    quantity: int = Field(gt=0)
    unit_price: float = Field(ge=0)


class Shipment(FromRow):
    courier: str | None = None
    tracking_number: str | None = None
    status: ShipmentStatus | None = None
    estimated_delivery: date | None = None
    shipped_at: datetime | None = None
    delivered_at: datetime | None = None


class OrderDetail(FromRow):
    order_id: int
    status: OrderStatus
    order_date: datetime | None = None
    total_amount: Amount = 0.0
    shipping_address: str | None = None
    payment_method: str | None = None
    payment_status: PaymentStatus | None = Field(
        default=None, validation_alias=AliasPath("payment", "status")
    )
    paid_at: datetime | None = Field(
        default=None, validation_alias=AliasPath("payment", "paid_at")
    )
    items: list[OrderItem] = Field(default_factory=list)
    shipment: Shipment | None = None
