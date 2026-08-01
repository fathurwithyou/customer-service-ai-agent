from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class TicketCategory(StrEnum):
    SHIPPING = "shipping"
    REFUND = "refund"
    PRODUCT = "product"
    PAYMENT = "payment"
    OTHER = "other"


class TicketPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class Ticket(BaseModel):
    ticket_id: int
    order_id: int | None = None
    category: TicketCategory
    priority: TicketPriority
    subject: str
