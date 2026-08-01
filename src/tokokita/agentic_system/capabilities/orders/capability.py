from __future__ import annotations

from pydantic_ai.capabilities import Capability

from ...guardrails.access_levels import AccessLevel
from .tools import get_order_detail, get_orders, track_shipment, update_shipping_address

TOOLS = [get_orders, get_order_detail, track_shipment, update_shipping_address]
ACCESS = {tool.__name__: AccessLevel.VERIFIED_CUSTOMER for tool in TOOLS}

ACTIVITY = {
    "get_orders": "Membuka daftar pesanan Anda",
    "get_order_detail": "Mengecek detail pesanan",
    "track_shipment": "Melacak posisi paket",
    "update_shipping_address": "Memperbarui alamat pengiriman",
}

orders_capability = Capability(
    id="orders",
    description="Riwayat pesanan, rincian, pelacakan pengiriman, dan perubahan alamat.",
    tools=TOOLS,
)
