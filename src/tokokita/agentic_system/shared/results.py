"""A policy refusal is a result, not an exception.

The outcome is a code and a sentence: the code is what a test asserts on and what a caller
branches on, the sentence is what the model reads. A `success` boolean alongside the code would
be a second field for one fact, and two fields for one fact can disagree.
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


class Decision(BaseModel):
    allowed: bool
    code: ResultCode
    detail: str
