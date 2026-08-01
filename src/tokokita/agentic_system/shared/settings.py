"""Runtime settings, env-configurable via TOKOKITA_* or a .env file."""

from __future__ import annotations

from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TOKOKITA_", env_file=".env", extra="ignore")

    # Any Groq model id. No key falls back to the keyless `test` model, so the service boots.
    model_name: str = "openai/gpt-oss-20b"
    groq_api_key: SecretStr | None = None

    # Room to recover from a stale order id, not enough for a runaway loop.
    tool_retries: int = 2

    # Handed to the Groq SDK, which retries 429/5xx with backoff and honours `Retry-After`.
    http_retries: int = 3
    request_timeout: float = 60.0

    # "parsed" gives reasoning its own field; "hidden" leaks analysis into content, which Groq
    # fails to parse (gpt-oss-20b: 3/3 vs 1/3). Empty for a non-reasoning model.
    reasoning_format: Literal["hidden", "raw", "parsed"] | None = "parsed"

    database_path: str = "./tokokita.db"

    # Both optional: the stack runs with no credentials.
    logfire_token: SecretStr | None = None
    phoenix_endpoint: str = "http://localhost:6006"
    logfire_environment: str = "development"

    @field_validator("reasoning_format", mode="before")
    @classmethod
    def _blank_is_off(cls, value: object) -> object:
        # An empty env var is how you spell "off"; without this it is a startup crash.
        return None if value == "" else value
