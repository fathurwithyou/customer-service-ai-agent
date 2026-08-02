"""None of these rules needs a real model -- the whole point of keeping them out of the prompt."""

from __future__ import annotations

import pytest
from pydantic_ai.models.test import TestModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from tokokita.agentic_system.agents.support.agent import CAPABILITIES, TOOL_ACCESS, build_agent
from tokokita.agentic_system.agents.support.deps import SupportDeps
from tokokita.agentic_system.capabilities.customers.services import CustomerLookup
from tokokita.agentic_system.capabilities.orders import policies as order_policies
from tokokita.agentic_system.capabilities.orders.schemas import OrderStatus
from tokokita.agentic_system.capabilities.returns import policies as refund_policies
from tokokita.agentic_system.capabilities.returns.services import ReturnService
from tokokita.agentic_system.capabilities.tickets import policies as ticket_policies
from tokokita.agentic_system.guardrails.identity_gate import IdentityGate
from tokokita.agentic_system.shared.results import ActionResult, ResultCode
from tokokita.agentic_system.shared.settings import Settings
from tokokita.data import tables

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize(
    ("status", "allowed"),
    [
        (OrderStatus.PENDING, True),
        (OrderStatus.PAID, True),
        (OrderStatus.PROCESSING, True),
        (OrderStatus.SHIPPED, False),
        (OrderStatus.DELIVERED, False),
        (OrderStatus.CANCELLED, False),
    ],
)
def test_address_change_decision_table(status: OrderStatus, allowed: bool) -> None:
    assert order_policies.can_change_address(status).allowed is allowed


@pytest.mark.parametrize(
    ("amount", "escalate"),
    [(0, False), (999_999, False), (1_000_000, False), (1_000_001, True), (5_000_000, True)],
)
def test_refund_ceiling_is_exclusive(amount: float, escalate: bool) -> None:
    assert refund_policies.requires_escalation(amount) is escalate


async def test_expensive_refund_is_refused_and_nothing_is_created(session: AsyncSession) -> None:
    order = tables.Order(
        customer_id=1,
        status="delivered",
        total_amount=3_000_000,
        shipping_address="Jl. Melati No. 1, Jakarta",
        payment_method="credit_card",
    )
    session.add(order)
    await session.flush()
    session.add(
        tables.OrderItem(
            order_id=order.order_id, product_id=2, quantity=3, unit_price=1_000_000
        )
    )
    await session.commit()

    result = await ReturnService(session).request(
        order_id=order.order_id, product_id=2, reason="rusak semua", customer_id=1
    )
    assert isinstance(result, ActionResult)
    assert result.code is ResultCode.REFUND_EXCEEDS_LIMIT
    assert not await session.scalar(
        select(func.count())
        .select_from(tables.Return)
        .where(tables.Return.order_id == order.order_id)
    )


@pytest.mark.parametrize(
    ("message", "signal"),
    [
        ("Saya merasa ditipu, uang saya hilang", "fraud"),
        ("Saya akan lapor polisi kalau tidak beres", "legal"),
        ("Barangnya meledak waktu dicharge", "safety"),
        ("Tolong sambungkan ke manusia asli", "human_request"),
        ("Saya sangat kecewa dengan layanan ini", "strong_negative"),
        ("I want to speak to a human please", "human_request"),
    ],
)
def test_escalation_signals_are_detected(message: str, signal: str) -> None:
    assert signal in ticket_policies.detect_signals(message)


def test_ordinary_question_raises_no_signal() -> None:
    assert ticket_policies.detect_signals("Halo, pesanan saya sudah sampai mana ya?") == []


def test_not_received_claim_is_recognised() -> None:
    assert ticket_policies.claims_not_received("paket saya belum sampai")
    assert not ticket_policies.claims_not_received("paket sudah saya terima, terima kasih")


async def _tools_offered(settings: Settings, deps: SupportDeps) -> set[str]:
    model = TestModel(call_tools=[])
    agent = build_agent(settings, model=model)
    await agent.run("halo", deps=deps)
    return {t.name for t in model.last_model_request_parameters.function_tools}


async def test_scoped_tools_are_absent_before_verification(
    settings: Settings, anonymous: SupportDeps
) -> None:
    assert await _tools_offered(settings, anonymous) == {"get_customer", "get_product"}


async def test_all_tools_appear_after_verification(settings: Settings, andi: SupportDeps) -> None:
    assert await _tools_offered(settings, andi) == set(TOOL_ACCESS)


async def test_scoped_tool_is_refused_even_if_reached(anonymous: SupportDeps) -> None:
    """Defence in depth: prepare_tools hid it, wrap_tool_execute still refuses."""

    async def handler(args: dict) -> str:
        raise AssertionError("the tool body must not run")

    class _Ctx:
        deps = anonymous

    class _ToolDef:
        name = "get_order_detail"

    result = await IdentityGate(access=TOOL_ACCESS).wrap_tool_execute(
        _Ctx(),  # type: ignore[arg-type]
        call=None,
        tool_def=_ToolDef(),  # type: ignore[arg-type]
        args={"order_id": 1},
        handler=handler,
    )
    assert isinstance(result, ActionResult)
    assert result.code is ResultCode.UNAVAILABLE


def test_every_capability_tool_is_classified() -> None:
    """An unclassified tool silently becomes unreachable -- catch it here, not in prod."""

    registered = {tool.__name__ for cap in CAPABILITIES for tool in cap.tools}
    assert registered == set(TOOL_ACCESS)


def test_unknown_tools_fail_closed() -> None:
    assert IdentityGate().needs_customer("some_future_tool") is True


async def test_lookup_promotes_the_session(anonymous: SupportDeps, session: AsyncSession) -> None:
    """The privilege transition belongs to the gate, not to the tool that returns the customer."""

    customer = await CustomerLookup(session).by_contact("andi@example.com")

    class _Ctx:
        deps = anonymous

    class _ToolDef:
        name = "get_customer"

    assert anonymous.customer is None
    await IdentityGate(access=TOOL_ACCESS).after_tool_execute(
        _Ctx(),  # type: ignore[arg-type]
        call=None,
        tool_def=_ToolDef(),  # type: ignore[arg-type]
        args={"contact": "andi@example.com"},
        result=customer,
    )
    assert anonymous.customer == customer


async def test_other_tools_do_not_promote(anonymous: SupportDeps, session: AsyncSession) -> None:

    customer = await CustomerLookup(session).by_contact("andi@example.com")

    class _Ctx:
        deps = anonymous

    class _ToolDef:
        name = "get_product"

    await IdentityGate(access=TOOL_ACCESS).after_tool_execute(
        _Ctx(),  # type: ignore[arg-type]
        call=None,
        tool_def=_ToolDef(),  # type: ignore[arg-type]
        args={},
        result=customer,
    )
    assert anonymous.customer is None
