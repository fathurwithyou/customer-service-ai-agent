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

    # parallel_tool_calls: every tool shares one aiosqlite connection, so calls must not overlap.
    # reasoning_format: a thinking model left to itself writes `<think>` and Hermes-style
    # `<tool_call>` blocks into the *text* channel, where they never parse as tool calls and burn
    # the retry budget. GroqModel is used over the OpenAI-compatible path because this knob is
    # typed here -- and omitted entirely for a model that would reject it.
    model_settings = GroqModelSettings(parallel_tool_calls=False)
    if settings.reasoning_format:
        model_settings["groq_reasoning_format"] = settings.reasoning_format

    # The SDK's own retry, not a transport of ours. Raising from inside a custom transport
    # hides the response from the SDK, which then reports a 429 as "Connection error" -- the
    # rate limit becomes invisible. AsyncGroq honours `Retry-After` and maps 429 to a proper
    # RateLimitError, so there is nothing left for us to add.
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
