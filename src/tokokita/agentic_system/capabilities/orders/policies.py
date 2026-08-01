from __future__ import annotations

from ...shared.results import Decision, ResultCode
from .schemas import OrderStatus

# Once the parcel is with the courier the address is the courier's copy, not ours -- editing
# our row would show the customer a change that will never reach the driver.
ADDRESS_LOCKED = {OrderStatus.SHIPPED, OrderStatus.DELIVERED}


def can_change_address(status: OrderStatus) -> Decision:
    if status in ADDRESS_LOCKED:
        return Decision(
            allowed=False,
            code=ResultCode.ORDER_ALREADY_SHIPPED,
            detail=(
                f"Pesanan sudah berstatus '{status.value}', jadi alamat pengiriman tidak bisa "
                "diubah lagi."
            ),
        )
    if status is OrderStatus.CANCELLED:
        return Decision(
            allowed=False,
            code=ResultCode.ORDER_CANCELLED,
            detail="Pesanan sudah dibatalkan, alamat pengiriman tidak bisa diubah.",
        )
    return Decision(allowed=True, code=ResultCode.OK, detail="Alamat pengiriman bisa diperbarui.")
