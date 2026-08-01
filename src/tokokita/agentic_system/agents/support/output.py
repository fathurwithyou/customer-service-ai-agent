"""What a turn returns to the caller.

Only `message` comes from the model. The rest are facts read from the turn -- who we
recognised, whether it reached a human, which ticket -- so the model cannot report an
escalation that never happened, and the UI can render state as state instead of parsing prose.
"""

from __future__ import annotations

from pydantic import BaseModel


class AgentReply(BaseModel):
    message: str
    customer_name: str | None = None
    escalated: bool = False
    ticket_id: int | None = None
