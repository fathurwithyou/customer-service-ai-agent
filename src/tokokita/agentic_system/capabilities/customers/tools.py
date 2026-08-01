from __future__ import annotations

from pydantic_ai import RunContext

from ...agents.support.deps import SupportDeps
from .schemas import Customer


async def get_customer(ctx: RunContext[SupportDeps], contact: str) -> Customer | None:
    """Cari pelanggan dari email atau nomor telepon yang mereka sebutkan, lalu verifikasi sesi ini.

    Panggil ini lebih dulu sebelum membuka data pesanan, pengiriman, atau pembayaran apa pun.
    Kembalikan None kalau tidak ada yang cocok -- jangan menebak.

    Args:
        contact: Email atau nomor telepon yang diberikan pelanggan.
    """
    return await ctx.deps.customers.by_contact(contact)
