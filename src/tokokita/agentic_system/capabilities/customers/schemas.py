from __future__ import annotations

from pydantic import BaseModel


class Customer(BaseModel):
    """Just the identity. The contact used to look someone up is never sent back to the
    model or onto a span."""

    customer_id: int
    full_name: str
