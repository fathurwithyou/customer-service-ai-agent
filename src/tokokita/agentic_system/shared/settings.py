"""Runtime settings, env-configurable via TOKOKITA_* or a .env file."""

from __future__ import annotations

from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TOKOKITA_", env_file=".env", extra="ignore")

    # Any Groq model id. No key falls back to the keyless `test` model, so the service boots.
    model_name: str = "openai/gpt-oss-120b"

    # Ordered by grounded replies over three runs each: 120b 3/3, qwen 3/3, 20b 2/3. The llamas
    # scored 1/3 and 0/3 and stay out: 3.3 writes `<function=...>` into the text channel rather
    # than calling a tool, and Groq sometimes returns that as content -- raising nothing, so a
    # fallback chain cannot see it.
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
