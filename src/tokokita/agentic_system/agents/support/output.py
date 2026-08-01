"""Only `message` comes from the model; the rest are read from the turn, so it cannot report an
escalation that never happened and the UI renders state instead of parsing prose.
"""

from __future__ import annotations

from pydantic import BaseModel


class AgentReply(BaseModel):
    message: str
    customer_name: str | None = None
    escalated: bool = False
    ticket_id: int | None = None
