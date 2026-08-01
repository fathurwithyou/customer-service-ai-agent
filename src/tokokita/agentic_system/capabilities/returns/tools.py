from __future__ import annotations

import logfire
from pydantic_ai import ModelRetry, RunContext

from ...agents.support.deps import SupportDeps
from ...shared.results import ActionResult, ResultCode
from .schemas import ReturnRequest


async def create_return(
    ctx: RunContext[SupportDeps], order_id: int, product_id: int, reason: str
) -> ReturnRequest | ActionResult:
    """Ajukan pengembalian satu produk dari sebuah pesanan.

    Nilai refund dihitung sendiri dari data pesanan -- kamu tidak perlu dan tidak bisa
    menentukannya. Kalau nilainya melebihi batas kebijakan, pengajuan TIDAK dibuat dan kasus
    ini wajib dieskalasi ke manusia.

    Args:
        order_id: Pesanan yang produknya ingin dikembalikan.
        product_id: Produk yang dikembalikan.
        reason: Alasan pengembalian, dengan kata-kata pelanggan.
    """
    result = await ctx.deps.returns.request(
        order_id=order_id,
        product_id=product_id,
        reason=reason,
        customer_id=ctx.deps.require_customer().customer_id,
    )
    if result is None:
        raise ModelRetry(
            "Produk itu tidak ada di pesanan tersebut. Cek isi pesanannya dengan "
            "get_order_detail sebelum mengajukan pengembalian."
        )
    if isinstance(result, ActionResult) and result.code is ResultCode.REFUND_EXCEEDS_LIMIT:
        ctx.deps.forced_escalation = "refund melebihi batas kebijakan"
        logfire.warn("refund over limit", order_id=order_id)
    return result
