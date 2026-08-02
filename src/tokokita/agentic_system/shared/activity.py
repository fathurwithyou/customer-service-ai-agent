"""What the customer is told while a tool runs.

Declared beside the tools it names, so the phrase and the glyph travel together and the
frontend never has to know a tool name to draw the right icon.
"""

from __future__ import annotations

from pydantic import BaseModel


class Activity(BaseModel):
    label: str  # read by the customer, in the language the agent answers in
    icon: str   # a name the UI resolves; unknown names fall back to a neutral dot
