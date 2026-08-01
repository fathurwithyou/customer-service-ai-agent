"""Two levels, because the gate only ever asks one question: does this tool need a verified
customer? A third level would name a justification, not a behaviour.
"""

from __future__ import annotations

from enum import StrEnum


class AccessLevel(StrEnum):
    OPEN = "open"
    VERIFIED_CUSTOMER = "verified_customer"


UNVERIFIED_REFUSAL = (
    "Demi keamanan, data ini hanya bisa dibuka setelah identitas terverifikasi. "
    "Minta email atau nomor telepon yang terdaftar, lalu panggil get_customer."
)
