"""Composition root: model, dependencies, output contract, capabilities, guardrails."""

from __future__ import annotations

from pydantic_ai import Agent

from ...capabilities.catalog.capability import ACCESS as CATALOG_ACCESS
from ...capabilities.catalog.capability import ACTIVITY as CATALOG_ACTIVITY
from ...capabilities.catalog.capability import catalog_capability
from ...capabilities.customers.capability import ACCESS as CUSTOMERS_ACCESS
from ...capabilities.customers.capability import ACTIVITY as CUSTOMERS_ACTIVITY
from ...capabilities.customers.capability import customers_capability
from ...capabilities.orders.capability import ACCESS as ORDERS_ACCESS
from ...capabilities.orders.capability import ACTIVITY as ORDERS_ACTIVITY
from ...capabilities.orders.capability import orders_capability
from ...capabilities.returns.capability import ACCESS as RETURNS_ACCESS
from ...capabilities.returns.capability import ACTIVITY as RETURNS_ACTIVITY
from ...capabilities.returns.capability import returns_capability
from ...capabilities.tickets.capability import ACCESS as TICKETS_ACCESS
from ...capabilities.tickets.capability import ACTIVITY as TICKETS_ACTIVITY
from ...capabilities.tickets.capability import tickets_capability
from ...guardrails.escalation import escalation_is_honoured
from ...guardrails.identity_gate import IdentityGate
from ...shared.model_factory import build_model
from ...shared.settings import Settings
from .deps import SupportDeps
from .history import WINDOW
from .instructions import BASE, customer_context, mandatory_escalation

CAPABILITIES = [
    customers_capability,
    catalog_capability,
    orders_capability,
    returns_capability,
    tickets_capability,
]

TOOL_ACTIVITY = {
    **CUSTOMERS_ACTIVITY,
    **CATALOG_ACTIVITY,
    **ORDERS_ACTIVITY,
    **RETURNS_ACTIVITY,
    **TICKETS_ACTIVITY,
}

TOOL_ACCESS = {
    **CUSTOMERS_ACCESS,
    **CATALOG_ACCESS,
    **ORDERS_ACCESS,
    **RETURNS_ACCESS,
    **TICKETS_ACCESS,
}


def build_agent(settings: Settings) -> Agent[SupportDeps, str]:
    """No `model` parameter: a test swaps it with `agent.override(model=...)`, which is the
    framework's own seam and keeps the test out of the composition root.
    """
    agent = Agent(
        build_model(settings),
        deps_type=SupportDeps,
        output_type=str,
        retries=settings.tool_retries,
        instructions=BASE,
        capabilities=[*CAPABILITIES, WINDOW, IdentityGate(access=TOOL_ACCESS)],
    )
    agent.instructions(customer_context)
    agent.instructions(mandatory_escalation)
    agent.output_validator(escalation_is_honoured)
    return agent
