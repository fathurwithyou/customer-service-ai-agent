from __future__ import annotations

from pydantic_ai import RunContext

from ...agents.support.deps import SupportDeps
from .schemas import Product


async def get_product(
    ctx: RunContext[SupportDeps], product_id: int | None = None, name: str | None = None
) -> Product | None:
    """Info katalog: harga, stok, dan deskripsi produk. Isi salah satu argumen saja.

    Args:
        product_id: Id produk kalau pelanggan menyebutnya.
        name: Sebagian nama produk, dicocokkan tanpa membedakan huruf besar/kecil.
    """
    return await ctx.deps.catalog.find(product_id=product_id, name=name)
