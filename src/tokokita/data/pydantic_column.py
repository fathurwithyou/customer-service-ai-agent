"""A column whose Python value is a Pydantic model.

`TypeDecorator` is SQLAlchemy's own extension point for this, so validation happens at the
column and no layer above it ever touches JSON. `JSONB` rather than `JSON`: it stores parsed,
so the message body is queryable (`payload -> 'parts'`) and indexable without a second copy.
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
        self._adapter: TypeAdapter[Any] = TypeAdapter(model)

    def process_bind_param(self, value: Any, dialect: Dialect) -> Any:
        return None if value is None else self._adapter.dump_python(value, mode="json")

    def process_result_value(self, value: Any, dialect: Dialect) -> Any:
        return None if value is None else self._adapter.validate_python(value)
