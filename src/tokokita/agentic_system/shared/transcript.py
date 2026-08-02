"""Read a stored transcript back into the few lines a person needs."""

from __future__ import annotations

from pydantic import BaseModel
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from .activity import Activity


class Turn(BaseModel):
    role: str  # "customer" | "agent"
    text: str
    activity: list[Activity] = []


def read(messages: list[ModelMessage], activity: dict[str, Activity]) -> list[Turn]:
    """`activity` maps a tool name to the phrase a customer reads. Passed in rather than
    imported so this stays free of the agent, and so a replayed turn is labelled with exactly
    the words the live stream used.
    """
    # A call that drew a retry never ran, so only calls with a matching return are reported.
    ran = {
        part.tool_call_id
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, ToolReturnPart)
    }
    turns: list[Turn] = []
    tools: list[Activity] = []
    for message in messages:
        if isinstance(message, ModelRequest):
            for part in message.parts:
                if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                    turns.append(Turn(role="customer", text=part.content))
        elif isinstance(message, ModelResponse):
            for part in message.parts:
                if isinstance(part, ToolCallPart) and part.tool_call_id in ran:
                    tools.append(
                        activity.get(part.tool_name)
                        or Activity(label=part.tool_name, icon="dot")
                    )
                elif isinstance(part, TextPart) and part.content.strip():
                    turns.append(Turn(role="agent", text=part.content, activity=tools))
                    tools = []
    return turns


def outcome(messages: list[ModelMessage]) -> tuple[bool, int | None]:
    """Whether the turn was escalated, and to which ticket -- read from what ran.

    Asking the model to report this would be asking it to restate a fact the runtime already
    holds, and a restatement can disagree with the fact.
    """
    escalated, ticket_id = False, None
    for message in messages:
        if isinstance(message, ModelResponse):
            for part in message.parts:
                if isinstance(part, ToolCallPart) and part.tool_name == "escalate_ticket":
                    escalated = True
        elif isinstance(message, ModelRequest):
            for part in message.parts:
                if isinstance(part, ToolReturnPart) and part.tool_name == "create_ticket":
                    ticket_id = part.content.ticket_id
    return escalated, ticket_id
