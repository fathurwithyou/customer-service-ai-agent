"""Conversation persistence, one row per message. Columns are the fields every message has;
the message itself goes in `payload`, so nothing here serialises anything.

This keeps everything, including a run that died -- it is the audit record. What the *model*
sees is `history.py`'s job.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel
from pydantic_ai.messages import ModelMessage, sanitize_messages
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...data import tables


class Conversation(BaseModel):
    """One row in the picker: enough to recognise a conversation, nothing more."""

    session_id: str
    opened_at: datetime | None = None
    last_at: datetime | None = None
    messages: int
    opening: str | None = None


class MessageStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def load(self, session_id: str) -> list[ModelMessage]:
        rows = await self._session.scalars(
            select(tables.ConversationMessage)
            .where(tables.ConversationMessage.session_id == session_id)
            .order_by(tables.ConversationMessage.seq)
        )
        return [row.payload for row in rows]

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
                    created_at=message.timestamp,
                    payload=message,
                )
            )
        await self._session.commit()

    async def conversations(self) -> list[Conversation]:
        """The picker's list. `opening` is read out of the payload itself -- a JSONB column is
        queryable in place, so recognising a conversation costs no extra table.
        """
        rows = tables.ConversationMessage
        stats = (
            select(
                rows.session_id,
                func.min(rows.created_at).label("opened_at"),
                func.max(rows.created_at).label("last_at"),
                func.count().label("messages"),
            )
            .group_by(rows.session_id)
            .subquery()
        )
        opening = (
            select(rows.session_id, rows.payload["parts"][0]["content"].astext.label("opening"))
            .where(rows.kind == "request")
            .distinct(rows.session_id)
            .order_by(rows.session_id, rows.seq)
            .subquery()
        )
        result = await self._session.execute(
            select(stats, opening.c.opening)
            .join(opening, opening.c.session_id == stats.c.session_id)
            .order_by(stats.c.last_at.desc().nullslast())
        )
        return [Conversation.model_validate(row, from_attributes=True) for row in result]

    async def drop(self, session_id: str) -> int:
        result = await self._session.execute(
            delete(tables.ConversationMessage).where(
                tables.ConversationMessage.session_id == session_id
            )
        )
        await self._session.commit()
        return result.rowcount
