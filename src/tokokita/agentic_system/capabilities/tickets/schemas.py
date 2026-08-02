from __future__ import annotations

from enum import StrEnum

from ...shared.from_row import FromRow


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


class Ticket(FromRow):
    ticket_id: int
    order_id: int | None = None
    category: TicketCategory
    priority: TicketPriority
    subject: str
