"""Conversation persistence, one row per message.

Only the fields pydantic-ai puts on every `ModelMessage` become columns; the message itself
stays in the framework's own format, so a new part type needs no migration. A turn appends its
new messages instead of rewriting a growing blob.

The store keeps everything, including the messages of a run that died -- that is the audit
record. Deciding what the *model* sees is a different job, and it lives in `history.py`.
"""

from __future__ import annotations

from pydantic import TypeAdapter
from pydantic_ai.messages import ModelMessage, sanitize_messages
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...data import tables

MESSAGE = TypeAdapter(ModelMessage)


class MessageStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def load(self, session_id: str) -> list[ModelMessage]:
        rows = await self._session.scalars(
            select(tables.ConversationMessage)
            .where(tables.ConversationMessage.session_id == session_id)
            .order_by(tables.ConversationMessage.seq)
        )
        return [MESSAGE.validate_json(row.payload) for row in rows]

    async def append(self, session_id: str, messages: list[ModelMessage]) -> None:
        kept = sanitize_messages(messages)
        if not kept:
            return
        seq = await self._session.scalar(
            select(func.coalesce(func.max(tables.ConversationMessage.seq), 0)).where(
                tables.ConversationMessage.session_id == session_id
            )
        )
        for offset, message in enumerate(kept, start=1):
            self._session.add(
                tables.ConversationMessage(
                    session_id=session_id,
                    seq=seq + offset,
                    kind=message.kind,
                    run_id=message.run_id,
                    state=message.state,
                    created_at=message.timestamp.isoformat() if message.timestamp else None,
                    payload=MESSAGE.dump_json(message).decode(),
                )
            )
        await self._session.commit()
