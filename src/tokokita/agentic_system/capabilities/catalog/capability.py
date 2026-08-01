from __future__ import annotations

from pydantic_ai.capabilities import Capability

from ...guardrails.access_levels import AccessLevel
from .tools import get_product

ACCESS = {"get_product": AccessLevel.OPEN}

ACTIVITY = {"get_product": "Mencari informasi produk"}

catalog_capability = Capability(
    id="catalog",
    description="Harga, stok, dan deskripsi produk. Terbuka untuk siapa pun.",
    tools=[get_product],
)
