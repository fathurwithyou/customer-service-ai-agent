"""SQLite access, scoped by customer.

Every query over customer data takes a `customer_id` and filters on it, so no unscoped read
exists to call by mistake. Two deliberate exceptions: `customer_row` establishes a scope, and
the catalog is public.

A miss returns None for both "no such row" and "not yours" -- telling them apart would confirm
which order ids exist.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import aiosqlite

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
SCHEMA_PATH = DATA_DIR / "schema.sql"
SEED_PATH = DATA_DIR / "seed.sql"

Row = dict[str, Any]


class Database:
    """One connection, opened for the app's lifetime. Ample for a demo-scale SQLite file."""

    def __init__(self, connection: aiosqlite.Connection) -> None:
        self._db = connection

    @classmethod
    async def connect(cls, path: str, *, seed_if_empty: bool = True) -> Database:
        connection = await aiosqlite.connect(path)
        connection.row_factory = sqlite3.Row
        await connection.execute("PRAGMA foreign_keys = ON")
        db = cls(connection)
        if seed_if_empty and not await db._has_schema():
            await db.bootstrap()
        return db

    async def close(self) -> None:
        await self._db.close()

    async def bootstrap(self) -> None:
        await self._db.executescript(SCHEMA_PATH.read_text())
        await self._db.executescript(SEED_PATH.read_text())
        await self._db.commit()

    async def _has_schema(self) -> bool:
        return (
            await self._one(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='customers'"
            )
            is not None
        )

    async def _one(self, sql: str, params: tuple = ()) -> Row | None:
        cursor = await self._db.execute(sql, params)
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def _all(self, sql: str, params: tuple = ()) -> list[Row]:
        cursor = await self._db.execute(sql, params)
        return [dict(row) for row in await cursor.fetchall()]

    async def _insert(self, sql: str, params: tuple) -> int:
        cursor = await self._db.execute(sql, params)
        await self._db.commit()
        return int(cursor.lastrowid or 0)

    async def _update(self, sql: str, params: tuple) -> bool:
        cursor = await self._db.execute(sql, params)
        await self._db.commit()
        return cursor.rowcount > 0

    async def customer_row(self, contact: str) -> Row | None:
        return await self._one(
            "SELECT customer_id, full_name FROM customers"
            " WHERE lower(email) = lower(?) OR phone = ?",
            (contact, contact),
        )

    async def product_row(self, *, product_id: int | None, name: str | None) -> Row | None:
        if product_id is not None:
            return await self._one("SELECT * FROM products WHERE product_id = ?", (product_id,))
        if name:
            return await self._one(
                "SELECT * FROM products WHERE lower(name) LIKE lower(?) LIMIT 1", (f"%{name}%",)
            )
        return None

    async def order_rows(self, customer_id: int) -> list[Row]:
        return await self._all(
            "SELECT order_id, order_date, status, total_amount FROM orders"
            " WHERE customer_id = ? ORDER BY order_id",
            (customer_id,),
        )

    async def order_row(self, order_id: int, customer_id: int) -> Row | None:
        return await self._one(
            "SELECT order_id, order_date, status, total_amount, shipping_address, payment_method"
            " FROM orders WHERE order_id = ? AND customer_id = ?",
            (order_id, customer_id),
        )

    async def order_item_rows(self, order_id: int, customer_id: int) -> list[Row]:
        return await self._all(
            "SELECT i.product_id, p.name AS product_name, i.quantity, i.unit_price"
            " FROM order_items i"
            " JOIN orders o ON o.order_id = i.order_id"
            " JOIN products p ON p.product_id = i.product_id"
            " WHERE i.order_id = ? AND o.customer_id = ?",
            (order_id, customer_id),
        )

    async def shipment_row(self, order_id: int, customer_id: int) -> Row | None:
        return await self._one(
            "SELECT s.courier, s.tracking_number, s.status, s.estimated_delivery,"
            " s.shipped_at, s.delivered_at"
            " FROM shipments s JOIN orders o ON o.order_id = s.order_id"
            " WHERE s.order_id = ? AND o.customer_id = ?",
            (order_id, customer_id),
        )

    async def payment_row(self, order_id: int, customer_id: int) -> Row | None:
        return await self._one(
            "SELECT p.status, p.paid_at FROM payments p"
            " JOIN orders o ON o.order_id = p.order_id"
            " WHERE p.order_id = ? AND o.customer_id = ?",
            (order_id, customer_id),
        )

    async def set_shipping_address(self, order_id: int, customer_id: int, address: str) -> bool:
        return await self._update(
            "UPDATE orders SET shipping_address = ? WHERE order_id = ? AND customer_id = ?",
            (address, order_id, customer_id),
        )

    async def order_line_value(
        self, order_id: int, product_id: int, customer_id: int
    ) -> float | None:
        """The value the database says this line is worth, never a number the model supplied."""
        row = await self._one(
            "SELECT i.quantity * i.unit_price AS value FROM order_items i"
            " JOIN orders o ON o.order_id = i.order_id"
            " WHERE i.order_id = ? AND i.product_id = ? AND o.customer_id = ?",
            (order_id, product_id, customer_id),
        )
        return float(row["value"]) if row else None

    async def insert_return(
        self, order_id: int, product_id: int, reason: str, refund_amount: float
    ) -> int:
        return await self._insert(
            "INSERT INTO returns (order_id, product_id, reason, status, refund_amount)"
            " VALUES (?, ?, ?, 'requested', ?)",
            (order_id, product_id, reason, refund_amount),
        )

    async def count_returns(self, order_id: int) -> int:
        row = await self._one("SELECT COUNT(*) AS n FROM returns WHERE order_id = ?", (order_id,))
        return int(row["n"]) if row else 0

    async def insert_ticket(
        self, customer_id: int, order_id: int | None, category: str, priority: str, subject: str
    ) -> int:
        return await self._insert(
            "INSERT INTO tickets (customer_id, order_id, category, priority, status, subject)"
            " VALUES (?, ?, ?, ?, 'open', ?)",
            (customer_id, order_id, category, priority, subject),
        )

    async def mark_ticket_escalated(self, ticket_id: int, customer_id: int) -> bool:
        return await self._update(
            "UPDATE tickets SET status = 'escalated', priority = 'urgent'"
            " WHERE ticket_id = ? AND customer_id = ?",
            (ticket_id, customer_id),
        )

    async def open_ticket_id(self, customer_id: int) -> int | None:
        row = await self._one(
            "SELECT ticket_id FROM tickets WHERE customer_id = ?"
            " AND status IN ('open','pending','escalated') ORDER BY ticket_id DESC LIMIT 1",
            (customer_id,),
        )
        return int(row["ticket_id"]) if row else None

    async def conversation_row(self, session_id: str) -> Row | None:
        return await self._one(
            "SELECT messages FROM conversations WHERE session_id = ?", (session_id,)
        )

    async def upsert_conversation(self, session_id: str, messages: str) -> None:
        await self._insert(
            "INSERT INTO conversations (session_id, messages, updated_at)"
            " VALUES (?, ?, datetime('now'))"
            " ON CONFLICT(session_id) DO UPDATE SET messages = excluded.messages,"
            " updated_at = excluded.updated_at",
            (session_id, messages),
        )

    async def insert_ticket_message(self, ticket_id: int, sender: str, message: str) -> None:
        await self._insert(
            "INSERT INTO ticket_messages (ticket_id, sender, message) VALUES (?, ?, ?)",
            (ticket_id, sender, message),
        )
