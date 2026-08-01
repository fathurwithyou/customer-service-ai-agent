"""Runtime settings, env-configurable via TOKOKITA_* or a .env file."""

from __future__ import annotations

from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TOKOKITA_", env_file=".env", extra="ignore")

    # Any Groq model id. Without a key the agent falls back to Pydantic AI's keyless `test`
    # model so the service still boots and /health answers.
    model_name: str = "openai/gpt-oss-20b"
    groq_api_key: SecretStr | None = None

    # 2 gives the model room to recover from a stale order id without letting a loop run away.
    tool_retries: int = 2

    # Handed to the Groq SDK, which retries 429/5xx with backoff and honours `Retry-After`.
    http_retries: int = 3
    request_timeout: float = 60.0

    # "parsed" gives the reasoning its own field, which pydantic-ai maps to a ThinkingPart.
    # "hidden" only suppresses it, and a thinking model still writes analysis into the content
    # channel when it decides no tool is needed -- Groq then fails to parse the tool call
    # (measured on gpt-oss-20b: parsed 3/3, hidden 1/3). Empty for a non-reasoning model,
    # which would reject the parameter.
    reasoning_format: Literal["hidden", "raw", "parsed"] | None = "parsed"

    database_path: str = "./tokokita.db"

    # A Logfire cloud token is optional; Phoenix is the local default, so the whole stack runs
    # with no credentials at all.
    logfire_token: SecretStr | None = None
    phoenix_endpoint: str = "http://localhost:6006"
    logfire_environment: str = "development"

    @field_validator("reasoning_format", mode="before")
    @classmethod
    def _blank_is_off(cls, value: object) -> object:
        # An empty env var is how you spell "off" in a .env file; without this it is a crash.
        return None if value == "" else value
