from __future__ import annotations

from pydantic_ai.capabilities import Capability

from ...guardrails.access_levels import AccessLevel
from ...shared.activity import Activity
from .tools import get_product

ACCESS = {"get_product": AccessLevel.OPEN}

ACTIVITY = {"get_product": Activity(label="Mencari informasi produk", icon="tag")}

catalog_capability = Capability(
    id="catalog",
    description="Harga, stok, dan deskripsi produk. Terbuka untuk siapa pun.",
    tools=[get_product],
)
