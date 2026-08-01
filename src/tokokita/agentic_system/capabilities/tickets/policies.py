"""When a turn stops being the agent's to resolve.

Substring matching, crude on purpose: over-escalating costs a human two minutes, a missed
fraud report costs a customer their money.
"""

from __future__ import annotations

ESCALATION_PATTERNS: dict[str, tuple[str, ...]] = {
    "fraud": ("penipuan", "ditipu", "menipu", "scam", "fraud", "pembobolan", "dibobol"),
    "legal": (
        "pengacara",
        "tuntut",
        "menuntut",
        "somasi",
        "lapor polisi",
        "polisi",
        "pengadilan",
        "hukum",
        "lawyer",
        "sue",
        "legal action",
        "ylki",
    ),
    "safety": (
        "terbakar",
        "kebakaran",
        "meledak",
        "keracunan",
        "beracun",
        "melukai",
        "terluka",
        "berbahaya",
        "cedera",
        "unsafe",
        "injury",
        "fire",
    ),
    "human_request": (
        "bicara dengan manusia",
        "ngomong sama orang",
        "customer service manusia",
        "agen manusia",
        "operator",
        "manusia asli",
        "bukan bot",
        "speak to a human",
        "talk to a person",
        "real person",
        "human agent",
    ),
    "strong_negative": (
        "kecewa berat",
        "sangat kecewa",
        "marah",
        "parah banget",
        "tidak becus",
        "buruk sekali",
        "menyebalkan",
        "bangsat",
        "sialan",
        "terrible",
        "furious",
        "unacceptable",
        "worst",
    ),
}

NOT_RECEIVED_TERMS = (
    "belum sampai",
    "belum terima",
    "belum diterima",
    "tidak sampai",
    "tidak diterima",
    "gak sampai",
    "ga sampai",
    "nggak sampai",
    "belum datang",
    "hilang",
    "not received",
    "never arrived",
    "didn't arrive",
    "not delivered",
)


def detect_signals(message: str) -> list[str]:
    lowered = message.lower()
    return sorted(
        signal
        for signal, terms in ESCALATION_PATTERNS.items()
        if any(term in lowered for term in terms)
    )


def claims_not_received(message: str) -> bool:
    lowered = message.lower()
    return any(term in lowered for term in NOT_RECEIVED_TERMS)
