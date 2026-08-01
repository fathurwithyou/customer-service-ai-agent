from __future__ import annotations

import logfire
from pydantic_ai import ModelRetry, RunContext

from ...agents.support.deps import SupportDeps
from ...shared.results import ActionResult, ResultCode
from .schemas import Ticket, TicketCategory, TicketPriority


async def create_ticket(
    ctx: RunContext[SupportDeps],
    category: TicketCategory,
    priority: TicketPriority,
    subject: str,
    order_id: int | None = None,
) -> Ticket:
    """Buka tiket dukungan supaya kasusnya tercatat dan bisa ditindaklanjuti tim manusia.

    Args:
        category: Jenis masalah: shipping, refund, product, payment, atau other.
        priority: low, medium, high, atau urgent.
        subject: Ringkasan satu kalimat dari masalah pelanggan.
        order_id: Pesanan terkait, kalau ada.
    """
    ticket = await ctx.deps.tickets.open(
        customer_id=ctx.deps.require_customer().customer_id,
        order_id=order_id,
        category=category,
        priority=priority,
        subject=subject,
    )
    logfire.info("ticket created", ticket_id=ticket.ticket_id, category=category.value)
    return ticket


async def escalate_ticket(
    ctx: RunContext[SupportDeps], ticket_id: int, reason: str
) -> ActionResult:
    """Serahkan sebuah tiket ke tim manusia dan naikkan prioritasnya menjadi urgent.

    Wajib dipanggil untuk kasus penipuan, ancaman hukum, isu keselamatan, permintaan bicara
    dengan manusia, refund di atas batas kebijakan, atau data yang saling bertentangan.
    Kalau tiketnya belum ada, buat dulu dengan create_ticket.

    Args:
        ticket_id: Tiket yang dieskalasi.
        reason: Kenapa kasus ini butuh manusia.
    """
    ok = await ctx.deps.tickets.escalate(ticket_id, ctx.deps.require_customer().customer_id)
    if not ok:
        raise ModelRetry(
            "Tiket itu tidak ada pada akun ini. Buat tiket baru dengan create_ticket, lalu "
            "eskalasikan tiket itu."
        )
    logfire.warn("ticket escalated", ticket_id=ticket_id, reason=reason)
    return ActionResult(
        code=ResultCode.OK, detail=f"Tiket {ticket_id} sudah dieskalasi ke tim manusia."
    )
