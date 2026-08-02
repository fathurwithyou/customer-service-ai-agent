"""One provider feeds Logfire and Phoenix. Order is enrich, repair, export.

Nothing else masks these spans -- Logfire's scrubber skips LLM attributes, OpenInference's
masking needs an OITracer -- so we record customer_id, never the contact.
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
    """Phoenix crashes rendering `tool.parameters` and rebuilds it from the gen_ai key, so both
    must go; the JSON belongs in `input.value`."""

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


class LabelHttpSpans(SpanProcessor):
    """Phoenix draws its icons from `openinference.span.kind`, so HTTP spans arrive iconless.
    CHAIN is OpenInference's generic step, which is what both of these are.

    Client spans are also renamed: the SDK retries a 429 itself, so a bare "POST" hides the
    only place those retries are visible.
    """

    def on_end(self, span: ReadableSpan) -> None:
        attributes = dict(span.attributes or {})
        if SpanAttributes.OPENINFERENCE_SPAN_KIND in attributes or "http.method" not in attributes:
            return
        attributes[SpanAttributes.OPENINFERENCE_SPAN_KIND] = OpenInferenceSpanKindValues.CHAIN.value
        span._attributes = attributes
        if "http.route" not in attributes:
            host = str(attributes.get("http.url", "")).split("/")[2:3]
            span._name = f"{attributes['http.method']} {host[0] if host else '?'} {attributes.get('http.status_code', '')}".strip()


def describe_turn(
    *,
    session_id: str,
    customer_id: int | None,
    message: str,
    signals: list[str],
    model: str,
) -> None:
    """Without span.kind Phoenix files the trace as UNKNOWN and previews an opaque HTTP row.

    Set on the OTel span, not the logfire wrapper: the wrapper JSON-encodes non-scalars, which
    would flatten tag.tags into one string.
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
    # OpenInference names, not ours: those are what Phoenix aggregates and prices.
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
    return [
        OpenInferenceSpanProcessor(),
        ToolCallInput(),
        LabelHttpSpans(),
        BatchSpanProcessor(exporter),
    ]


def keep_session_id(match: logfire.ScrubMatch) -> str | None:
    """Our chat id, not a credential -- and the only thing grouping a conversation."""
    if match.path == ("attributes", "session.id"):
        return match.value
    return None


def setup_observability(settings: Settings, app: FastAPI) -> None:
    """Exporter once per process; the FastAPI part repeats because tests build many apps."""
    global _configured
    if not _configured:
        logfire.configure(
            token=settings.logfire_token.get_secret_value() if settings.logfire_token else None,
            send_to_logfire="if-token-present",
            service_name=PROJECT_NAME,
            environment=settings.logfire_environment,
            # Without this a failed turn is invisible in the terminal: the traceback goes
            # only to the span.
            console=logfire.ConsoleOptions(min_log_level="warn", verbose=False),
            # Phoenix files spans by this resource attribute, normally set by its own
            # register(); without it every trace lands in the "default" project.
            resource_attributes={ResourceAttributes.PROJECT_NAME: PROJECT_NAME},
            scrubbing=logfire.ScrubbingOptions(callback=keep_session_id),
            additional_span_processors=span_processors(settings),
        )
        logfire.instrument_pydantic_ai(version=5)
        # Makes the SDK's 429 retries visible. instrument_sqlite3 was dropped: it emits
        # nothing for aiosqlite, which runs on a worker thread.
        logfire.instrument_httpx(capture_headers=False)
        # "failure", not "all": successful validations say nothing and bury the real spans.
        logfire.instrument_pydantic(record="failure")
        _configured = True
    logfire.instrument_fastapi(app, excluded_urls="/health")
