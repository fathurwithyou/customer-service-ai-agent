"""Load the dummy data. `seed.sql` is the client brief's Appendix A verbatim, so it stays SQL
rather than being retyped as ORM objects; only the DDL moved into `tables.py`.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine

from ..agentic_system.shared.database import create_engine, create_schema
from ..agentic_system.shared.settings import Settings
from . import tables

SEED = Path(__file__).parent / "seed.sql"
COMMENT = re.compile(r"--[^\n]*")


def statements(sql: str) -> list[str]:
    """DBAPI drivers take one statement per call, and aiosqlite's adapter hides executescript."""
    return [s for part in COMMENT.sub("", sql).split(";") if (s := part.strip())]


async def seed_if_empty(engine: AsyncEngine) -> bool:
    async with engine.begin() as conn:
        if await conn.scalar(select(func.count()).select_from(tables.Customer)):
            return False
        for statement in statements(SEED.read_text()):
            await conn.execute(text(statement))
        return True


async def main() -> int:
    engine = create_engine(Settings().database_url)
    await create_schema(engine)
    print("Seeded." if await seed_if_empty(engine) else "Sudah ada isinya, dilewati.")
    await engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
