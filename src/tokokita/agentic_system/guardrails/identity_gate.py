"""Withhold, refuse, and own the moment a session becomes verified.

This sees every tool call, including tools that do not exist yet -- an `if` per tool is
useless in the one place someone forgets it.

  prepare_tools      hides the tool, so no tokens go on a refusal
  wrap_tool_execute  the control; redundant by design (replayed history still passes here)
  after_tool_execute the privilege transition, kept out of the domain tool

An undeclared tool needs a customer, so forgetting to classify one fails closed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic_ai import RunContext, ToolDefinition
from pydantic_ai.capabilities import AbstractCapability, WrapToolExecuteHandler

from ..agents.support.deps import SupportDeps
from ..capabilities.customers.schemas import Customer
from ..shared.results import ActionResult, ResultCode
from .access_levels import UNVERIFIED_REFUSAL, AccessLevel


@dataclass
class IdentityGate(AbstractCapability[SupportDeps]):
    access: dict[str, AccessLevel] = field(default_factory=dict)
    verifies_with: str = "get_customer"

    def needs_customer(self, tool_name: str) -> bool:
        return self.access.get(tool_name, AccessLevel.VERIFIED_CUSTOMER) is not AccessLevel.OPEN

    async def prepare_tools(
        self, ctx: RunContext[SupportDeps], tool_defs: list[ToolDefinition]
    ) -> list[ToolDefinition]:
        if ctx.deps.customer is not None:
            return tool_defs
        return [t for t in tool_defs if not self.needs_customer(t.name)]

    async def wrap_tool_execute(
        self,
        ctx: RunContext[SupportDeps],
        *,
        call: Any,
        tool_def: ToolDefinition,
        args: dict[str, Any],
        handler: WrapToolExecuteHandler,
    ) -> Any:
        if self.needs_customer(tool_def.name) and ctx.deps.customer is None:
            return ActionResult(code=ResultCode.UNAVAILABLE, detail=UNVERIFIED_REFUSAL)
        return await handler(args)

    async def after_tool_execute(
        self,
        ctx: RunContext[SupportDeps],
        *,
        call: Any,
        tool_def: ToolDefinition,
        args: dict[str, Any],
        result: Any,
    ) -> Any:
        if tool_def.name == self.verifies_with and isinstance(result, Customer):
            ctx.deps.customer = result
        return result
