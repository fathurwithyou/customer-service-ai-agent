from __future__ import annotations

from pydantic_ai.capabilities import Capability

from ...guardrails.access_levels import AccessLevel
from ...shared.activity import Activity
from .tools import get_order_detail, get_orders, track_shipment, update_shipping_address

TOOLS = [get_orders, get_order_detail, track_shipment, update_shipping_address]
ACCESS = {tool.__name__: AccessLevel.VERIFIED_CUSTOMER for tool in TOOLS}

ACTIVITY = {
    "get_orders": Activity(label="Membuka daftar pesanan Anda", icon="list"),
    "get_order_detail": Activity(label="Mengecek detail pesanan", icon="box"),
    "track_shipment": Activity(label="Melacak posisi paket", icon="truck"),
    "update_shipping_address": Activity(label="Memperbarui alamat pengiriman", icon="pin"),
}

orders_capability = Capability(
    id="orders",
    description="Riwayat pesanan, rincian, pelacakan pengiriman, dan perubahan alamat.",
    tools=TOOLS,
)
