"""Build the chat model. One seam, so swapping provider is a change here and nowhere else."""

from __future__ import annotations

from typing import Any

from groq import AsyncGroq
from pydantic_ai.models.groq import GroqModel, GroqModelSettings
from pydantic_ai.providers.groq import GroqProvider

from .settings import Settings


def build_model(settings: Settings) -> Any:
    if settings.groq_api_key is None:
        return "test"

    # No overlap: every tool shares one aiosqlite connection.
    # reasoning_format keeps a thinking model's analysis out of the text channel, where it
    # never parses as a tool call. GroqModel is chosen because this knob is typed here.
    model_settings = GroqModelSettings(parallel_tool_calls=False)
    if settings.reasoning_format:
        model_settings["groq_reasoning_format"] = settings.reasoning_format

    # The SDK's own retry: raising from a custom transport hides the response, so a 429
    # surfaces as "Connection error". AsyncGroq honours Retry-After and maps it properly.
    return GroqModel(
        settings.model_name,
        provider=GroqProvider(
            groq_client=AsyncGroq(
                api_key=settings.groq_api_key.get_secret_value(),
                max_retries=settings.http_retries,
                timeout=settings.request_timeout,
            )
        ),
        settings=model_settings,
    )
