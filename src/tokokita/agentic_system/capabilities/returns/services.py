"""Return business logic.

The load-bearing decision: the refund amount is derived from `order_items`, never accepted as
an argument. Had it been a parameter, the model could have named a figure under the ceiling and
walked past the guard -- the check would be reading a number chosen by the guarded party.
"""

from __future__ import annotations

from ...shared.database import Database
from ...shared.results import ActionResult, ResultCode
from . import policies
from .schemas import ReturnRequest


class ReturnService:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def request(
        self, *, order_id: int, product_id: int, reason: str, customer_id: int
    ) -> ReturnRequest | ActionResult | None:
        """None means that product is not on that order; the caller turns it into a retry."""
        refund = await self._db.order_line_value(order_id, product_id, customer_id)
        if refund is None:
            return None
        if policies.requires_escalation(refund):
            return ActionResult(
                code=ResultCode.REFUND_EXCEEDS_LIMIT,
                detail=(
                    f"Nilai refund Rp {refund:,.0f} melebihi batas yang bisa saya proses "
                    "sendiri. Pengajuan belum dibuat -- eskalasikan ke tim manusia dengan "
                    "escalate_ticket."
                ),
            )
        return_id = await self._db.insert_return(order_id, product_id, reason, refund)
        return ReturnRequest(
            return_id=return_id,
            order_id=order_id,
            product_id=product_id,
            reason=reason,
            refund_amount=refund,
        )
