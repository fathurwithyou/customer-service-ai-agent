"""Runtime settings, env-configurable via TOKOKITA_* or a .env file."""

from __future__ import annotations

from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TOKOKITA_", env_file=".env", extra="ignore")

    # Any Groq model id. No key falls back to the keyless `test` model, so the service boots.
    model_name: str = "openai/gpt-oss-120b"

    # Tried in order after `model_name`, on a model-side failure. Ordered by measurement, not by
    # size: three runs each of "Pesanan 1 saya statusnya apa?" as a verified customer, scored on
    # whether the reply called a tool and quoted that order's real resi.
    #
    #   openai/gpt-oss-120b       3/3
    #   qwen/qwen3.6-27b          3/3
    #   openai/gpt-oss-20b        2/3   the previous default
    #   llama-3.1-8b-instant      1/3   excluded
    #   llama-3.3-70b-versatile   0/3   excluded -- see below
    #
    # The llama models are left out on purpose. 3.3 never emits a tool call with this tool
    # surface: it writes `<function=get_order_detail{...}</function>` into the text channel, so
    # the customer is handed protocol noise as an answer. Groq sometimes rejects that as
    # `tool_use_failed` (400) and sometimes returns it as content -- and the second case raises
    # nothing, which a fallback chain cannot see. A model that fails loudly is recoverable; one
    # that answers confidently and wrongly is not.
    fallback_models: list[str] = ["qwen/qwen3.6-27b", "openai/gpt-oss-20b"]
    groq_api_key: SecretStr | None = None

    # Room to recover from a stale order id, not enough for a runaway loop.
    tool_retries: int = 2

    # A support turn that needs more than this is looping, not working.
    request_limit: int = 8
    total_tokens_limit: int = 60_000

    # Handed to the Groq SDK, which retries 429/5xx with backoff and honours `Retry-After`.
    http_retries: int = 3
    request_timeout: float = 60.0

    # "parsed" gives reasoning its own field; "hidden" leaks analysis into content, which Groq
    # fails to parse (gpt-oss-20b: 3/3 vs 1/3). Empty for a non-reasoning model.
    reasoning_format: Literal["hidden", "raw", "parsed"] | None = "parsed"

    database_url: str = "postgresql+asyncpg://tokokita:tokokita@localhost:5433/tokokita"

    # Both optional: the stack runs with no credentials.
    logfire_token: SecretStr | None = None
    phoenix_endpoint: str = "http://localhost:6006"
    logfire_environment: str = "development"

    @field_validator("reasoning_format", mode="before")
    @classmethod
    def _blank_is_off(cls, value: object) -> object:
        # An empty env var is how you spell "off"; without this it is a startup crash.
        return None if value == "" else value
