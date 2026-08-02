from __future__ import annotations

from pydantic_ai.capabilities import Capability

from ...guardrails.access_levels import AccessLevel
from ...shared.activity import Activity
from .tools import get_customer

ACCESS = {"get_customer": AccessLevel.OPEN}

ACTIVITY = {"get_customer": Activity(label="Mencocokkan data akun Anda", icon="user")}

customers_capability = Capability(
    id="customers",
    description="Mencari pelanggan dari email atau nomor telepon.",
    tools=[get_customer],
)
