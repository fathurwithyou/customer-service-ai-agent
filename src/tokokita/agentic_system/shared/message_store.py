"""Conversation persistence, one row per message.

Only the fields pydantic-ai puts on every `ModelMessage` become columns; the message itself
stays in the framework's own format, so a new part type needs no migration. A turn appends its
new messages instead of rewriting a growing blob.

The window is counted in runs, not messages: cutting mid-run would separate a tool call from
its return. System prompts are stripped -- instructions are re-injected every run.
"""

from __future__ import annotations

from pydantic import TypeAdapter
from pydantic_ai.messages import ModelMessage, sanitize_messages

from .database import Database

MESSAGE = TypeAdapter(ModelMessage)
MAX_RUNS = 12


class MessageStore:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def load(self, session_id: str) -> list[ModelMessage]:
        rows = await self._db.recent_messages(session_id, MAX_RUNS)
        return [MESSAGE.validate_json(row["payload"]) for row in rows]

    async def append(self, session_id: str, messages: list[ModelMessage]) -> None:
        rows = [
            (
                message.kind,
                message.run_id,
                message.timestamp.isoformat() if message.timestamp else None,
                MESSAGE.dump_json(message).decode(),
            )
            for message in sanitize_messages(messages)
        ]
        if rows:
            await self._db.append_messages(session_id, rows)
