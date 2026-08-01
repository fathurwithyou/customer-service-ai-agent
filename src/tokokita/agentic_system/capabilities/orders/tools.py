from __future__ import annotations

from pydantic_ai import ModelRetry, RunContext

from ...agents.support.deps import SupportDeps
from ...shared.results import ActionResult
from .schemas import OrderDetail, OrderSummary, Shipment

UNKNOWN_ORDER = (
    "Pesanan itu tidak ditemukan pada akun ini. Periksa lagi nomor pesanannya, atau panggil "
    "get_orders untuk melihat daftar pesanan pelanggan."
)


async def get_orders(ctx: RunContext[SupportDeps]) -> list[OrderSummary]:
    """Daftar pesanan milik pelanggan yang sudah terverifikasi, terbaru di akhir."""
    return await ctx.deps.orders.list_for(ctx.deps.require_customer().customer_id)


async def get_order_detail(ctx: RunContext[SupportDeps], order_id: int) -> OrderDetail:
    """Rincian lengkap satu pesanan: item, pengiriman, dan pembayaran dalam satu panggilan.

    Pakai ini untuk pertanyaan "pesanan saya bagaimana?" -- lebih hemat daripada memanggil
    beberapa tool terpisah.

    Args:
        order_id: Nomor pesanan yang ditanyakan pelanggan.
    """
    detail = await ctx.deps.orders.detail(order_id, ctx.deps.require_customer().customer_id)
    if detail is None:
        raise ModelRetry(UNKNOWN_ORDER)
    return detail


async def track_shipment(ctx: RunContext[SupportDeps], order_id: int) -> Shipment:
    """Status pengiriman dan nomor resi untuk satu pesanan.

    Nomor resi HANYA boleh disebut kalau tool ini mengembalikannya. Jangan pernah menebak.

    Args:
        order_id: Nomor pesanan yang ingin dilacak.
    """
    shipment = await ctx.deps.orders.shipment(order_id, ctx.deps.require_customer().customer_id)
    if shipment is None:
        raise ModelRetry(
            "Belum ada data pengiriman untuk pesanan itu -- mungkin belum dikirim, atau nomor "
            "pesanannya keliru. Cek dulu dengan get_order_detail."
        )
    return shipment


async def update_shipping_address(
    ctx: RunContext[SupportDeps], order_id: int, new_address: str
) -> ActionResult:
    """Ubah alamat pengiriman sebuah pesanan.

    Hanya bisa selama pesanan belum dikirim. Kalau statusnya sudah shipped atau delivered,
    permintaan ini akan ditolak -- sampaikan penolakannya apa adanya.

    Args:
        order_id: Pesanan yang alamatnya diubah.
        new_address: Alamat pengiriman baru, lengkap.
    """
    result = await ctx.deps.orders.change_address(
        order_id, ctx.deps.require_customer().customer_id, new_address
    )
    if result is None:
        raise ModelRetry(UNKNOWN_ORDER)
    return result
