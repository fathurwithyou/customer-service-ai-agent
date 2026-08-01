"""Business logic, tested without an LLM. If a rule needs the agent to verify, it is in the
wrong layer.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from tokokita.agentic_system.capabilities.catalog.services import CatalogService
from tokokita.agentic_system.capabilities.customers.services import CustomerLookup
from tokokita.agentic_system.capabilities.orders.schemas import (
    OrderStatus,
    PaymentStatus,
    ShipmentStatus,
)
from tokokita.agentic_system.capabilities.orders.services import OrderService
from tokokita.agentic_system.capabilities.returns.schemas import ReturnRequest
from tokokita.agentic_system.capabilities.returns.services import ReturnService
from tokokita.agentic_system.capabilities.tickets.schemas import TicketCategory, TicketPriority
from tokokita.agentic_system.capabilities.tickets.services import TicketService
from tokokita.agentic_system.shared.database import Database
from tokokita.agentic_system.shared.results import ActionResult, ResultCode

pytestmark = pytest.mark.anyio

ANDI, BUNGA, CITRA = 1, 2, 3


async def test_identity_resolves_by_email_and_phone(db: Database) -> None:
    service = CustomerLookup(db)
    assert (await service.by_contact("andi@example.com")).full_name == "Andi Wijaya"
    assert (await service.by_contact("081200000002")).full_name == "Bunga Lestari"
    assert await service.by_contact("nobody@example.com") is None


async def test_order_detail_is_assembled_from_scoped_rows(db: Database) -> None:
    detail = await OrderService(db).detail(1, ANDI)
    assert detail.status is OrderStatus.SHIPPED
    assert detail.total_amount == 178000
    assert [i.product_name for i in detail.items] == ["Kaos Polos Hitam"]
    assert detail.shipment.tracking_number == "JNE0012345678"
    assert detail.shipment.status is ShipmentStatus.IN_TRANSIT
    assert detail.payment_status is PaymentStatus.PAID


async def test_another_customers_order_is_invisible(db: Database) -> None:
    """Order 3 is Bunga's. Andi is verified -- but not as Bunga."""
    assert await OrderService(db).detail(3, ANDI) is None
    assert await OrderService(db).detail(3, BUNGA) is not None


async def test_order_list_is_scoped(db: Database) -> None:
    """Asserts the partition, not a count -- adding seed orders must not break this."""
    andi = {o.order_id for o in await OrderService(db).list_for(ANDI)}
    bunga = {o.order_id for o in await OrderService(db).list_for(BUNGA)}
    assert andi and bunga
    assert not (andi & bunga)
    assert {1, 2} <= andi and 3 in bunga


async def test_address_change_refused_once_shipped(db: Database) -> None:
    result = await OrderService(db).change_address(1, ANDI, "Jl. Baru No. 5, Depok")
    assert result.code is ResultCode.ORDER_ALREADY_SHIPPED
    detail = await OrderService(db).detail(1, ANDI)
    assert detail.shipping_address == "Jl. Melati No. 1, Jakarta"


async def test_address_change_allowed_before_shipping(db: Database) -> None:
    result = await OrderService(db).change_address(3, BUNGA, "Jl. Anggrek No. 2, Bandung")
    assert result.success is True
    detail = await OrderService(db).detail(3, BUNGA)
    assert detail.shipping_address == "Jl. Anggrek No. 2, Bandung"


async def test_address_change_on_someone_elses_order_is_not_found(db: Database) -> None:
    assert await OrderService(db).change_address(3, ANDI, "Jl. X") is None


async def test_refund_is_derived_from_the_order(db: Database) -> None:
    """2 x Rp 89.000 -- a number the model never gets to name."""
    created = await ReturnService(db).request(
        order_id=1, product_id=1, reason="Ukuran tidak cocok", customer_id=ANDI
    )
    assert isinstance(created, ReturnRequest)
    assert created.refund_amount == 178000


async def test_return_rejects_product_not_on_the_order(db: Database) -> None:
    assert (
        await ReturnService(db).request(
            order_id=1, product_id=2, reason="salah kirim", customer_id=ANDI
        )
        is None
    )


async def test_catalog_is_public_and_matches_by_name(db: Database) -> None:
    service = CatalogService(db)
    product = await service.find(product_id=None, name="sneakers")
    assert product.price == 349000
    assert (await service.find(product_id=3, name=None)).stock_qty == 0


async def test_ticket_lifecycle(db: Database) -> None:
    service = TicketService(db)
    ticket = await service.open(
        customer_id=ANDI,
        order_id=1,
        category=TicketCategory.SHIPPING,
        priority=TicketPriority.HIGH,
        subject="Paket belum sampai",
    )
    assert await service.escalate(ticket.ticket_id, ANDI) is True


async def test_escalating_someone_elses_ticket_fails(db: Database) -> None:
    assert await TicketService(db).escalate(1, CITRA) is False  # ticket 1 is Andi's


def test_refund_amount_cannot_be_negative() -> None:
    with pytest.raises(ValidationError):
        ReturnRequest(return_id=1, order_id=1, product_id=1, reason="x", refund_amount=-1)


def test_action_result_success_is_derived() -> None:
    assert ActionResult(code=ResultCode.OK, detail="x").success is True
    assert ActionResult(code=ResultCode.UNAVAILABLE, detail="x").success is False


async def test_address_change_succeeds_on_a_processing_order(db: Database) -> None:
    """Order 4 exists so this path is reachable at all -- orders 1 and 2 are both past it."""
    result = await OrderService(db).change_address(4, ANDI, "Jl. Sangkuriang No. 7, Bandung")
    assert result.success is True
    assert (
        await OrderService(db).detail(4, ANDI)
    ).shipping_address == "Jl. Sangkuriang No. 7, Bandung"


async def test_refusal_names_the_courier_of_that_order(db: Database) -> None:
    """Without this the model fills the gap from an earlier turn and quotes another order's
    tracking number -- observed in a real conversation."""
    result = await OrderService(db).change_address(1, ANDI, "Jl. Baru No. 5")
    assert "JNE0012345678" in result.detail
    assert "SIC0098765432" not in result.detail


async def test_cancelled_order_refuses_with_its_own_code(db: Database) -> None:
    result = await OrderService(db).change_address(7, ANDI, "Jl. Baru No. 5")
    assert result.code is ResultCode.ORDER_CANCELLED


async def test_unpaid_order_reports_pending_payment(db: Database) -> None:
    detail = await OrderService(db).detail(6, ANDI)
    assert detail.status is OrderStatus.PENDING
    assert detail.payment_status is PaymentStatus.PENDING
    assert detail.paid_at is None


async def test_expensive_order_is_seeded_over_the_ceiling(db: Database) -> None:
    result = await ReturnService(db).request(
        order_id=5, product_id=4, reason="rusak", customer_id=ANDI
    )
    assert isinstance(result, ActionResult)
    assert result.code is ResultCode.REFUND_EXCEEDS_LIMIT
    assert await db.count_returns(5) == 0


async def test_multi_item_order_needs_the_product_named(db: Database) -> None:
    detail = await OrderService(db).detail(4, ANDI)
    assert len(detail.items) == 2
    ok = await ReturnService(db).request(
        order_id=4, product_id=6, reason="tidak sesuai", customer_id=ANDI
    )
    assert ok.refund_amount == 135000  # the named line, not the order total


async def test_customer_with_no_orders(db: Database) -> None:
    assert await OrderService(db).list_for(CITRA) == []
