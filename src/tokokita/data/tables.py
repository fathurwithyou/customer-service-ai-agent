"""The marketplace tables. `Base.metadata` is the schema -- there is no separate DDL file to
drift from it.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Customer(Base):
    __tablename__ = "customers"

    customer_id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str]
    email: Mapped[str] = mapped_column(unique=True)
    phone: Mapped[str | None]
    loyalty_tier: Mapped[str] = mapped_column(default="bronze")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Product(Base):
    __tablename__ = "products"

    product_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    category: Mapped[str | None]
    price: Mapped[float]
    stock_qty: Mapped[int] = mapped_column(default=0)
    description: Mapped[str | None]


class Order(Base):
    __tablename__ = "orders"

    order_id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.customer_id"), index=True)
    order_date: Mapped[datetime] = mapped_column(server_default=func.now())
    status: Mapped[str]
    total_amount: Mapped[float | None]
    shipping_address: Mapped[str | None]
    payment_method: Mapped[str | None]


class OrderItem(Base):
    __tablename__ = "order_items"

    order_item_id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.order_id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.product_id"))
    quantity: Mapped[int]
    unit_price: Mapped[float]


class Shipment(Base):
    __tablename__ = "shipments"

    shipment_id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.order_id"), index=True)
    courier: Mapped[str | None]
    tracking_number: Mapped[str | None]
    status: Mapped[str | None]
    estimated_delivery: Mapped[str | None]
    shipped_at: Mapped[str | None]
    delivered_at: Mapped[str | None]


class Payment(Base):
    __tablename__ = "payments"

    payment_id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.order_id"), index=True)
    amount: Mapped[float | None]
    method: Mapped[str | None]
    status: Mapped[str | None]
    paid_at: Mapped[str | None]


class Return(Base):
    __tablename__ = "returns"

    return_id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.order_id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.product_id"))
    reason: Mapped[str | None]
    status: Mapped[str] = mapped_column(default="requested")
    refund_amount: Mapped[float | None]
    requested_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Ticket(Base):
    __tablename__ = "tickets"

    ticket_id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.customer_id"), index=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.order_id"))
    category: Mapped[str | None]
    priority: Mapped[str | None]
    status: Mapped[str] = mapped_column(default="open")
    subject: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    resolved_at: Mapped[datetime | None]


class TicketMessage(Base):
    __tablename__ = "ticket_messages"

    message_id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.ticket_id"), index=True)
    sender: Mapped[str | None]
    message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ConversationMessage(Base):
    """One row per pydantic-ai ModelMessage. The columns are the fields it puts on every
    message; the message itself stays in `payload` in the framework's own format.
    """

    __tablename__ = "conversation_messages"
    __table_args__ = (UniqueConstraint("session_id", "seq"),)

    message_id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(index=True)
    seq: Mapped[int]
    kind: Mapped[str]
    run_id: Mapped[str | None]
    state: Mapped[str]  # "interrupted" marks a run that died mid-flight
    created_at: Mapped[str | None]  # ModelMessage.timestamp; null on a request
    payload: Mapped[str] = mapped_column(Text)
