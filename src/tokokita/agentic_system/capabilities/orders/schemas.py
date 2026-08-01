from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


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


class OrderSummary(BaseModel):
    order_id: int
    order_date: str | None = None
    status: OrderStatus
    total_amount: float = Field(ge=0)


class OrderItem(BaseModel):
    product_id: int
    product_name: str
    quantity: int = Field(gt=0)
    unit_price: float = Field(ge=0)


class Shipment(BaseModel):
    courier: str | None = None
    tracking_number: str | None = None
    status: ShipmentStatus | None = None
    estimated_delivery: str | None = None
    shipped_at: str | None = None
    delivered_at: str | None = None


class OrderDetail(BaseModel):
    order_id: int
    status: OrderStatus
    order_date: str | None = None
    total_amount: float = Field(ge=0)
    shipping_address: str | None = None
    payment_method: str | None = None
    payment_status: PaymentStatus | None = None
    paid_at: str | None = None
    items: list[OrderItem] = []
    shipment: Shipment | None = None
