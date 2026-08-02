"""Build the chat model. One seam, so swapping provider is a change here and nowhere else.

A `FallbackModel`: configured model first, then the rest on `ModelAPIError`, which
`ModelHTTPError` subclasses -- so a Groq 429 moves on instead of ending the turn.
"""

from __future__ import annotations

from typing import Any

from groq import AsyncGroq
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.groq import GroqModel, GroqModelSettings
from pydantic_ai.providers.groq import GroqProvider

from .settings import Settings

# Measured, not assumed: Groq answers 400 `reasoning_format is not supported with this model`
# for these families. One global setting would make every llama fallback fail on its first
# request -- exactly when the fallback is the thing being relied on.
REJECTS_REASONING_FORMAT = ("llama-3.1", "llama-3.3")


def model_settings(model_name: str, settings: Settings) -> GroqModelSettings:
    # No overlap: every tool in a turn shares one AsyncSession, which is not concurrency-safe.
    values = GroqModelSettings(parallel_tool_calls=False)
    # reasoning_format keeps a thinking model's analysis out of the text channel, where it never
    # parses as a tool call. GroqModel is chosen because this knob is typed here.
    if settings.reasoning_format and not model_name.startswith(REJECTS_REASONING_FORMAT):
        values["groq_reasoning_format"] = settings.reasoning_format
    return values


def build_model(settings: Settings) -> Any:
    if settings.groq_api_key is None:
        return "test"

    # The SDK's own retry: raising from a custom transport hides the response, so a 429
    # surfaces as "Connection error". AsyncGroq honours Retry-After and maps it properly.
    # One client for the whole chain, so they share a connection pool.
    provider = GroqProvider(
        groq_client=AsyncGroq(
            api_key=settings.groq_api_key.get_secret_value(),
            max_retries=settings.http_retries,
            timeout=settings.request_timeout,
        )
    )
    chain = [
        settings.model_name,
        *(name for name in settings.fallback_models if name != settings.model_name),
    ]
    return FallbackModel(
        *(GroqModel(name, provider=provider, settings=model_settings(name, settings))
          for name in chain)
    )
