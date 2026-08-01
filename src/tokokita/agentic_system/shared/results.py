"""A policy refusal is a result, not an exception. `success` is derived: two fields for one
fact can disagree.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class ResultCode(StrEnum):
    OK = "ok"
    ORDER_ALREADY_SHIPPED = "order_already_shipped"
    ORDER_CANCELLED = "order_cancelled"
    REFUND_EXCEEDS_LIMIT = "refund_exceeds_limit"
    UNAVAILABLE = "unavailable"


class ActionResult(BaseModel):
    code: ResultCode
    detail: str

    @property
    def success(self) -> bool:
        return self.code is ResultCode.OK


class Decision(BaseModel):
    allowed: bool
    code: ResultCode
    detail: str

    def as_result(self) -> ActionResult:
        return ActionResult(code=self.code, detail=self.detail)
