"""The refund ceiling. Above it, a refund stops being a chatbot's decision."""

from __future__ import annotations

REFUND_ESCALATION_LIMIT = 1_000_000.0


def requires_escalation(amount: float) -> bool:
    return amount > REFUND_ESCALATION_LIMIT
