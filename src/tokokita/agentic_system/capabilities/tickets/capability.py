from __future__ import annotations

from pydantic_ai.capabilities import Capability

from ...guardrails.access_levels import AccessLevel
from ...shared.activity import Activity
from .tools import create_ticket, escalate_ticket

TOOLS = [create_ticket, escalate_ticket]
ACCESS = {tool.__name__: AccessLevel.VERIFIED_CUSTOMER for tool in TOOLS}

ACTIVITY = {
    "create_ticket": Activity(label="Mencatat keluhan Anda", icon="note"),
    "escalate_ticket": Activity(label="Menghubungkan ke tim kami", icon="headset"),
}

tickets_capability = Capability(
    id="tickets",
    description="Membuka tiket dukungan dan mengeskalasinya ke tim manusia.",
    tools=TOOLS,
)
