"""Create the SQLite file and load the dummy data."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from ..agentic_system.shared.database import Database
from ..agentic_system.shared.settings import Settings


async def main() -> int:
    path = Path(Settings().database_path)
    if path.exists():
        print(f"{path} sudah ada -- hapus dulu kalau ingin data ulang.", file=sys.stderr)
        return 1
    db = await Database.connect(str(path), seed_if_empty=False)
    await db.bootstrap()
    await db.close()
    print(f"Seeded {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
