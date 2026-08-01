"""Transcript persistence in the framework's own format, so a new part type needs no migration.

Identity is not stored: it arrives as injected context each request, and a server-side copy
would be a second source of truth. System prompts are stripped -- instructions are re-injected
every run.
"""

from __future__ import annotations

from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter, sanitize_messages

from .database import Database

MAX_MESSAGES = 40


class MessageStore:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def load(self, session_id: str) -> list[ModelMessage]:
        row = await self._db.conversation_row(session_id)
        if row is None:
            return []
        return ModelMessagesTypeAdapter.validate_json(row["messages"])

    async def save(self, session_id: str, messages: list[ModelMessage]) -> None:
        kept = sanitize_messages(messages)[-MAX_MESSAGES:]
        await self._db.upsert_conversation(
            session_id, ModelMessagesTypeAdapter.dump_json(kept).decode()
        )
