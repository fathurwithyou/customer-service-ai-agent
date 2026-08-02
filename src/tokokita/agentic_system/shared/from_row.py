"""The base for every model a tool hands back, validated straight off an ORM row.

What these omit is the point: `Customer` has no `email` or `phone`, and that absence is what
keeps a contact detail out of the transcript.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class FromRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
