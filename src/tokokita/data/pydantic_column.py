"""A column whose Python value is a Pydantic model.

`TypeDecorator` is SQLAlchemy's own extension point for this, so validation happens at the
column and no layer above it ever touches JSON. The ordering is what makes the pairing right:
`process_bind_param` runs *before* the `JSONB` impl's own bind processor, and
`process_result_value` *after* its result processor -- so the value crossing this boundary is
already a Python dict, which is `dump_python(mode="json")` / `validate_python`, not the bytes
that `dump_json` / `validate_json` handle. `JSONB` rather than `JSON`: it stores parsed,
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
        # Stored under the __init__ parameter's own name, and not underscored, because that is
        # how `_static_cache_key` finds it: it reads `get_cls_kwargs(cls)` and keeps only the
        # names that are also instance attributes. Held privately, the key would collapse to
        # `(PydanticJson,)` and two columns carrying different models would compare equal.
        self.model = model
        self._adapter: TypeAdapter[Any] = TypeAdapter(model)

    def process_bind_param(self, value: Any, dialect: Dialect) -> Any:
        return None if value is None else self._adapter.dump_python(value, mode="json")

    def process_result_value(self, value: Any, dialect: Dialect) -> Any:
        return None if value is None else self._adapter.validate_python(value)
