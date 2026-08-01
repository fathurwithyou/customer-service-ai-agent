"""The reply no longer claims to have escalated -- that is read from the transcript -- so all
that is left to enforce is that a turn which must reach a human did.
"""

from __future__ import annotations

from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.messages import ModelResponse, ToolCallPart

from ..agents.support.deps import SupportDeps


async def escalation_is_honoured(ctx: RunContext[SupportDeps], reply: str) -> str:
    called = {
        part.tool_name
        for message in ctx.messages
        if isinstance(message, ModelResponse)
        for part in message.parts
        if isinstance(part, ToolCallPart)
    }
    if ctx.deps.escalation_required and "escalate_ticket" not in called:
        raise ModelRetry(
            "Kasus ini wajib dieskalasi ke manusia. Panggil create_ticket bila tiketnya belum "
            "ada, lalu escalate_ticket, sebelum menjawab pelanggan."
        )
    return reply
