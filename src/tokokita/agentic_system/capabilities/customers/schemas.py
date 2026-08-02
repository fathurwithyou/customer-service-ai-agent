from __future__ import annotations

from ...shared.from_row import FromRow


class Customer(FromRow):
    """Just the identity. The contact used to look someone up is never sent back to the
    model or onto a span."""

    customer_id: int
    full_name: str
