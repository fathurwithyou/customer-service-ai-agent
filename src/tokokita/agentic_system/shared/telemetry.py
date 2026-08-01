"""Tracing into Logfire and Phoenix from one tracer provider: `OpenInferenceSpanProcessor`
enriches spans in place and exports nothing itself (docs/STACK_NOTES.md section 9), so
registration order is the contract -- enrich, repair, export.

PII: redaction here is load-bearing, not belt-and-braces. Logfire's scrubber is *intentionally
disabled for LLM message attributes*, and OpenInference's own masking (`TraceConfig`,
`OPENINFERENCE_HIDE_*`) only applies to OITracer-based instrumentors -- the pydantic-ai
integration is a post-hoc span translator and never reads it. So nothing masks these spans
except us: `customer_id` is recorded, never the contact used to look someone up.
"""

from __future__ import annotations

import json

import logfire
from fastapi import FastAPI
from openinference.instrumentation.pydantic_ai import OpenInferenceSpanProcessor
from openinference.semconv.resource import ResourceAttributes
from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes
from opentelemetry import trace as otel_trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from pydantic_ai.usage import RunUsage

from .settings import Settings

PROJECT_NAME = "tokokita-cs-agent"

_configured = False


class ToolCallInput(SpanProcessor):
    """Phoenix parses `tool.parameters` into an object on ingest and then crashes rendering it,
    and rebuilds it from `gen_ai.tool.call.arguments`, so both must go. The same JSON belongs in
    `input.value`, or a tool span arrives with an output and no input at all.
    """

    _ARGUMENT_KEYS = ("tool.parameters", "gen_ai.tool.call.arguments")

    def on_end(self, span: ReadableSpan) -> None:
        attributes = span.attributes or {}
        arguments = next((attributes[k] for k in self._ARGUMENT_KEYS if k in attributes), None)
        if arguments is None:
            return
        kept = {k: v for k, v in attributes.items() if k not in self._ARGUMENT_KEYS}
        kept.setdefault("input.value", arguments)
        kept.setdefault("input.mime_type", "application/json")
        span._attributes = kept


def describe_turn(
    *,
    session_id: str,
    customer_id: int | None,
    message: str,
    signals: list[str],
    model: str,
) -> None:
    """Make the turn span the readable root of its trace.

    Without `openinference.span.kind` Phoenix files it as UNKNOWN and previews the trace as an
    opaque HTTP row; with input/output values it previews the actual conversation.

    Written to the OTel span rather than the logfire wrapper: the wrapper JSON-encodes anything
    that is not a scalar, which would turn `tag.tags` into one opaque string instead of the
    list of chips Phoenix filters on.
    """
    span = otel_trace.get_current_span()
    span.set_attribute(
        SpanAttributes.OPENINFERENCE_SPAN_KIND, OpenInferenceSpanKindValues.CHAIN.value
    )
    span.set_attribute(SpanAttributes.SESSION_ID, session_id)
    span.set_attribute(SpanAttributes.INPUT_VALUE, message)
    span.set_attribute(SpanAttributes.INPUT_MIME_TYPE, "text/plain")
    span.set_attribute(SpanAttributes.LLM_MODEL_NAME, model)
    span.set_attribute(
        SpanAttributes.TAG_TAGS, signals or (["verified"] if customer_id else ["anonymous"])
    )
    span.set_attribute(
        SpanAttributes.METADATA,
        json.dumps(
            {
                "verified": customer_id is not None,
                "escalation_signals": signals,
                "escalation_required": bool(signals),
                "model": model,
            }
        ),
    )
    if customer_id is not None:
        span.set_attribute(SpanAttributes.USER_ID, str(customer_id))


def record_answer(
    reply_text: str, *, escalated: bool, ticket_id: int | None, usage: RunUsage | None = None
) -> None:
    """Token counts use the OpenInference names rather than anything of our own: those are what
    Phoenix aggregates, prices, and lets you filter and sort a project by.
    """
    span = otel_trace.get_current_span()
    span.set_attribute(SpanAttributes.OUTPUT_VALUE, reply_text)
    span.set_attribute(SpanAttributes.OUTPUT_MIME_TYPE, "text/plain")
    span.set_attribute("escalated", escalated)
    if ticket_id is not None:
        span.set_attribute("ticket_id", ticket_id)
    if usage is not None:
        span.set_attribute(SpanAttributes.LLM_TOKEN_COUNT_PROMPT, usage.input_tokens)
        span.set_attribute(SpanAttributes.LLM_TOKEN_COUNT_COMPLETION, usage.output_tokens)
        span.set_attribute(
            SpanAttributes.LLM_TOKEN_COUNT_TOTAL, usage.input_tokens + usage.output_tokens
        )
        span.set_attribute("model_requests", usage.requests)


def span_processors(settings: Settings) -> list[SpanProcessor]:
    if not settings.phoenix_endpoint:
        return []
    exporter = OTLPSpanExporter(endpoint=f"{settings.phoenix_endpoint.rstrip('/')}/v1/traces")
    return [OpenInferenceSpanProcessor(), ToolCallInput(), BatchSpanProcessor(exporter)]


def keep_session_id(match: logfire.ScrubMatch) -> str | None:
    """`session.id` matches the "session" scrub pattern but is our own chat id, not a
    credential -- and the only thing grouping a multi-turn conversation."""
    if match.path == ("attributes", "session.id"):
        return match.value
    return None


def setup_observability(settings: Settings, app: FastAPI) -> None:
    """Configure the exporter once per process, instrument every app: the test suite builds many
    apps in one process, and only the FastAPI part may repeat.
    """
    global _configured
    if not _configured:
        logfire.configure(
            token=settings.logfire_token.get_secret_value() if settings.logfire_token else None,
            send_to_logfire="if-token-present",
            service_name=PROJECT_NAME,
            environment=settings.logfire_environment,
            # Warnings and errors still reach the terminal; without this a failed turn is
            # invisible to whoever is running the server, since the traceback goes only to
            # the span.
            console=logfire.ConsoleOptions(min_log_level="warn", verbose=False),
            # Phoenix files spans by this *resource* attribute, normally set by phoenix.otel
            # .register(). We use Logfire's provider, so without this every trace lands in
            # Phoenix's "default" project.
            resource_attributes={ResourceAttributes.PROJECT_NAME: PROJECT_NAME},
            scrubbing=logfire.ScrubbingOptions(callback=keep_session_id),
            additional_span_processors=span_processors(settings),
        )
        logfire.instrument_pydantic_ai(version=5)
        # httpx makes the Groq SDK's own 429 retries visible -- exactly what was invisible
        # while a rate limit was being misread as a connection error. (instrument_sqlite3 was
        # tried and dropped: it emits nothing for aiosqlite, which runs sqlite3 on a worker
        # thread, and nothing for plain sqlite3 here either.)
        logfire.instrument_httpx(capture_headers=False)
        # "failure", not "all": a successful validation says nothing, and at one span each they
        # bury the model and tool spans that carry the actual story. Failures still surface --
        # that is the signal worth a span.
        logfire.instrument_pydantic(record="failure")
        _configured = True
    logfire.instrument_fastapi(app, excluded_urls="/health")
