"""What a turn carries. Services are built here rather than reached for globally, so a test can
construct a turn against a fake database without patching.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from ...capabilities.catalog.services import CatalogService
from ...capabilities.customers.schemas import Customer
from ...capabilities.customers.services import CustomerLookup
from ...capabilities.orders.services import OrderService
from ...capabilities.returns.services import ReturnService
from ...capabilities.tickets.services import TicketService


@dataclass
class SupportDeps:
    session: AsyncSession
    customer: Customer | None = None
    escalation_signals: list[str] = field(default_factory=list)
    forced_escalation: str | None = None

    def __post_init__(self) -> None:
        self.customers = CustomerLookup(self.session)
        self.orders = OrderService(self.session)
        self.returns = ReturnService(self.session)
        self.tickets = TicketService(self.session)
        self.catalog = CatalogService(self.session)

    @property
    def escalation_required(self) -> bool:
        return bool(self.escalation_signals) or self.forced_escalation is not None

    def require_customer(self) -> Customer:
        """Scoped tools are unreachable without a customer, so this only fires on a wiring bug."""
        if self.customer is None:
            raise RuntimeError("scoped tool reached without a verified customer")
        return self.customer
