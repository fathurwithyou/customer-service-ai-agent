from __future__ import annotations

from pydantic_ai.capabilities import Capability

from ...guardrails.access_levels import AccessLevel
from .tools import create_return

ACCESS = {"create_return": AccessLevel.VERIFIED_CUSTOMER}

ACTIVITY = {"create_return": "Menyiapkan pengajuan pengembalian"}

returns_capability = Capability(
    id="returns",
    description="Pengajuan pengembalian produk, dengan batas nilai refund.",
    tools=[create_return],
)
