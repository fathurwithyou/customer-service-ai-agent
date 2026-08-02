"""A column whose Python value is a Pydantic model. JSONB, so the body stays queryable.

The value at this boundary is a dict, not JSON bytes -- hence `dump_python`, not `dump_json`.
`tests/test_pydantic_column.py` holds that to be true. DESIGN §10.
"""

from __future__ import annotations

from typing import Any

from pydantic import TypeAdapter
from sqlalchemy import Dialect
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import TypeDecorator


class PydanticJson(TypeDecorator[Any]):
    impl = JSONB
    cache_ok = True

    def __init__(self, model: Any) -> None:
        super().__init__()
        # Not `_model`: `cache_ok` requires an attribute named for the __init__ parameter, or
        # the cache key drops it and every PydanticJson column compares equal.
        self.model = model
        self._adapter: TypeAdapter[Any] = TypeAdapter(model)

    def process_bind_param(self, value: Any, dialect: Dialect) -> Any:
        return None if value is None else self._adapter.dump_python(value, mode="json")

    def process_result_value(self, value: Any, dialect: Dialect) -> Any:
        return None if value is None else self._adapter.validate_python(value)
