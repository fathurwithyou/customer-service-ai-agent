"""Only what nothing else can carry.

"Answer from tool results" is absent on purpose: tools are the model's sole source of data, so
instructing it to use them buys nothing. So is the identity rule (the gate makes it structural),
the per-tool procedure (tool docstrings), and the output contract (AgentReply field
descriptions) -- prose duplicating an enforced rule only drifts. What is left: the register, the
one behaviour code cannot prevent (promising things), and the judgment keyword detection misses.
"""

from __future__ import annotations

from pydantic_ai import RunContext

from .deps import SupportDeps

BASE = """\
Kamu asisten layanan pelanggan TokoKita, sebuah marketplace di Indonesia.
Jawab dalam bahasa Indonesia yang ramah dan ringkas.

Kalau sebuah tool menolak permintaan, sampaikan penolakan itu apa adanya beserta alasannya,
lalu tawarkan langkah yang masih mungkin. Jangan pernah menjanjikan kompensasi, diskon, atau
pengecualian yang tidak datang dari hasil tool.

Kalau menurut penilaianmu persoalan ini butuh ditangani manusia -- pelanggan yang kecewa
berat, kasus sensitif, atau permintaan di luar jangkauan tool-mu -- buatkan tiket lalu
eskalasikan. Sebagian kasus sudah ditandai wajib eskalasi untukmu; selebihnya penilaianmu.
"""


def customer_context(ctx: RunContext[SupportDeps]) -> str:
    """Who the caller is, injected by whatever channel they arrived through.

    Stated as given context, not as something to establish: told to "call get_customer first"
    the model demands an email the request already carried, and never reaches the data tools.
    """
    if ctx.deps.customer is None:
        # Asking for a contact and looking one up are two different turns. Phrased as one
        # ("minta email lalu panggil get_customer") the model tries both at once, calls
        # get_customer with nothing, and loses its retry budget before it can answer.
        return (
            "PELANGGAN: belum dikenali, jadi tool untuk data miliknya sendiri belum tersedia.\n"
            "- Kalau pesannya MEMUAT email atau nomor telepon: panggil get_customer dengan "
            "kontak itu.\n"
            "- Kalau TIDAK: jangan panggil tool apa pun untuk data miliknya. Cukup minta email "
            "atau nomor telepon yang terdaftar.\n"
            "- Pertanyaan umum seperti katalog produk tetap jawab langsung -- jangan meminta "
            "identitas untuk sesuatu yang tidak memerlukannya."
        )
    customer = ctx.deps.customer
    return (
        f"PELANGGAN: kamu sedang melayani {customer.full_name} (id {customer.customer_id}). "
        "Identitasnya sudah dipastikan oleh sistem, bukan sesuatu yang perlu kamu tanyakan. "
        "Jangan meminta email atau nomor telepon, dan jangan panggil get_customer. Sapa dengan "
        "namanya dan langsung pakai tool data untuk menjawab."
    )


def mandatory_escalation(ctx: RunContext[SupportDeps]) -> str:
    if not ctx.deps.escalation_required:
        return ""
    reasons = ", ".join(ctx.deps.escalation_signals) or ctx.deps.forced_escalation or ""
    return (
        f"PERINGATAN: giliran ini WAJIB dieskalasi ({reasons}). Buat tiket bila perlu, panggil "
        "escalate_ticket, dan jangan mencoba menyelesaikannya sendiri."
    )
