"""The column that makes a Pydantic model the payload's Python type."""

from __future__ import annotations

from pydantic import BaseModel
from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart

from tokokita.data.pydantic_column import PydanticJson


class Other(BaseModel):
    x: int


def test_two_payload_types_do_not_share_a_cache_key() -> None:
    """`cache_ok = True` promises the column's state is part of its cache key. SQLAlchemy builds
    that key from `__init__` parameter names that are *also* instance attributes, so holding the
    model privately collapses the key to `(PydanticJson,)` and makes every PydanticJson column
    compare equal to every other.
    """
    assert PydanticJson(ModelMessage)._static_cache_key != PydanticJson(Other)._static_cache_key


def test_a_message_survives_the_round_trip_the_column_performs() -> None:
    """`process_bind_param` runs before the JSONB impl, `process_result_value` after it, so the
    value at this boundary is a Python dict -- not the JSON bytes it would be a layer lower.
    """
    column = PydanticJson(ModelMessage)
    message = ModelRequest(parts=[UserPromptPart(content="halo")], run_id="r1")

    stored = column.process_bind_param(message, None)
    assert isinstance(stored, dict)

    assert column.process_result_value(stored, None) == message
    assert column.process_bind_param(None, None) is None
    assert column.process_result_value(None, None) is None
