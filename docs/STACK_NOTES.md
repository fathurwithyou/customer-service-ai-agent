# STACK_NOTES.md — Step 0 research

Every fact below was verified against the live docs (fetched July 2026) **and** by
introspecting the actually-installed packages in `.venv` (`inspect.signature`, reading
site-packages source). Where the published docs disagree with the installed code, the
installed code wins and the discrepancy is called out.

This is a record of Step 0 research, kept as written. Where a decision recorded here was later
reversed, the reversal is marked **⟲** rather than the paragraph being rewritten — the research
was real and re-doing it would cost the same day twice.

## Versions researched

| Package | Version | Notes |
|---|---|---|
| `pydantic-ai-slim[groq]` | **2.21.0** | V2 line. `pydantic-ai` (full) pulls every provider; slim + one extra is enough. ⟲ pinned `>=2.22.0`; **2.22.0** is what is installed now. Every signature below was re-checked against it and none moved. |
| `pydantic-ai-harness` | **0.14.0** | Separate package, 0.x — APIs still stabilising. ⟲ researched only; never used, and the dependency has since been removed (DESIGN.md §5.4). |
| `pydantic` | **2.13.4** | |
| `pydantic-settings` | **2.14.2** | |
| `fastapi[standard]` | **0.141.1** | Starlette 1.3.1, uvicorn 0.52.0. |
| `logfire[fastapi]` | **4.39.0** | ⟲ the extra is now `logfire[fastapi,httpx,sqlalchemy]` — `instrument_httpx` and `instrument_sqlalchemy` earn their place, `instrument_sqlite3` did not (§8). |
| `arize-phoenix-otel` | **0.16.1** | Only the client; the server runs in Docker. |
| `openinference-instrumentation-pydantic-ai` | **0.1.18** | |
| `asyncpg` | 0.31.1 | ⟲ replaced `aiosqlite`. The driver, never imported by our code. |
| `sqlalchemy[asyncio]` | 2.0.51 | ⟲ added late; it replaced a hand-rolled `Database` class. See DESIGN §7. |
| `groq` | 1.6.0 | Transitive via the `[groq]` extra. |

⟲ There is no `tenacity` and no `[retries]` extra in the installed set any more: the only thing
either was for was the custom retry transport, removed in §7.

Python pinned to **3.12** (`.python-version`). `arize-phoenix*` declares
`requires_python = <3.15,>=3.10`; the machine's system Python is 3.14.4, which resolves,
but 3.12 has the widest wheel coverage across this dependency set.

---

## 1. Breaking changes vs. what I remembered

These are the things that would have been wrong if I had coded from memory.

1. **The docs moved.** `ai.pydantic.dev` and `logfire.pydantic.dev` now 301-redirect to
   `pydantic.dev/docs/ai/` and `pydantic.dev/docs/logfire/`. The old `llms.txt` URLs in the
   task brief still work only via redirect.

2. **Pydantic AI V2 introduced "capabilities".** `Agent.__init__` now takes a
   `capabilities: Sequence[AgentCapability[AgentDepsT]] | None` parameter. This is described
   in the docs as *"the primary extension point for Pydantic AI"*. It did not exist in the
   1.x API I remembered.

3. **`Agent.instrument_all()` / `instrument=True` are not in the 2.21.0 `Agent.__init__`
   signature.** The verified signature has no `instrument` parameter. Instrumentation is now
   the `Instrumentation` capability, or `logfire.instrument_pydantic_ai()`. **The task
   brief's Appendix B is out of date on this point** — see §6.

4. **`pydantic_ai_harness.Guardrails` does not exist.** The docs index lists a "Guardrails"
   capability; the installed package exports `InputGuardrail` and `OutputGuardrail` as two
   *separate* capabilities. Verified: `getattr(pydantic_ai_harness, 'Guardrails')` → missing.

5. **`system_prompt` is legacy-ish; `instructions` is the current parameter.** Both exist on
   `Agent.__init__`. `instructions` is not carried over from message history between runs,
   which is what you want for a multi-turn chat endpoint.

6. **`InstrumentationSettings(version=...)` accepts `Literal[2, 3, 4, 5]` and defaults to
   `5`.** The Phoenix docs example still shows `version=2`.

---

## 2. Pydantic AI — tools

Verified from `pydantic.dev/docs/ai/tools-toolsets/tools/`.

```python
from pydantic_ai import Agent, RunContext, Tool

@agent.tool                       # receives RunContext as 1st arg
def get_player_name(ctx: RunContext[str]) -> str:
    """Get the player's name."""  # docstring -> tool description
    return ctx.deps

@agent.tool_plain                 # no RunContext
def roll_dice() -> str: ...
```

- Docstrings become the tool description; **`Args:` entries become per-parameter
  descriptions** in the JSON schema. Google/NumPy/Sphinx styles supported via
  `@agent.tool_plain(docstring_format='google', require_parameter_descriptions=True)`.
- Tools may return Pydantic models — serialised to JSON automatically.
- Constructor registration: `Agent(..., tools=[fn, Tool(fn, takes_ctx=False)])`.
- `FunctionToolset` groups tools into a reusable unit: `toolset.tool` / `toolset.tool_plain`.
- **`raise ModelRetry("...")`** sends a correction back to the model and consumes retry budget.

### `ToolDefinition.metadata` — verified by `dataclasses.fields()`

```
name, parameters_json_schema, description, outer_typed_dict_key, strict, sequential,
kind, metadata, timeout, defer_loading, unless_native, with_native, tool_kind,
return_schema, include_return_schema, toolset_id, capability_id
```

`metadata: dict[str, Any] | None` is the hook that lets a *generic* capability read
per-tool policy without knowing anything about the domain.

⟲ Not used in the end. `IdentityGate` keys its access map by `tool_def.name`, merged from the
`ACCESS` map each capability declares (DESIGN.md §4). Same property — the gate knows no domain —
without threading metadata through every tool registration.

---

## 3. Pydantic AI — typed dependencies

```python
@dataclass
class MyDeps:
    api_key: str
    http_client: httpx.AsyncClient

agent = Agent('groq:openai/gpt-oss-120b', deps_type=MyDeps)   # the TYPE, not an instance
result = await agent.run('...', deps=MyDeps(...))
```

(The model id here is incidental to the `deps_type` point — ⟲ the shipped default is
`openai/gpt-oss-20b`, see §7.)

`RunContext[MyDeps]` as the first parameter of tools, instructions, output validators and
guardrails gives `ctx.deps`. Verified `RunContext` fields include:

```
deps, model, usage, agent, prompt, messages, tracer, retries, tool_call_id, tool_name,
run_step, partial_output, run_id, conversation_id, metadata, capabilities, ...
```

**`ctx.messages`** is the live message history. That is what lets an output validator verify
what the model *actually did* rather than what it *claims* it did (DESIGN.md §5.3).

---

## 4. Pydantic AI — capabilities (the V2 extension point)

A capability is *"a reusable, composable unit of agent behavior"* that can contribute tools,
instructions, model settings, model selection, **and lifecycle hooks** — as opposed to a
tool, which is a single function exposed to the model, or a toolset, which is just a
collection of tools.

```python
from pydantic_ai.capabilities import Thinking, WebSearch, Instrumentation
agent = Agent('...', capabilities=[Thinking(effort='high'), WebSearch(local='duckduckgo')])
```

Built-ins (verified from `dir(pydantic_ai.capabilities)`): `Thinking`, `Hooks`,
`Instrumentation`, `SelectModel`, `ResolveModelId`, `WebSearch`, `WebFetch`,
`ImageGeneration`, `XSearch`, `MCP`, `ToolSearch`, `PrepareTools`, `PrepareOutputTools`,
`PrefixTools`, `NativeTool`, `Capability`, `Toolset`, `IncludeToolReturnSchemas`,
`SetToolMetadata`, `RaiseContentFilterError`, `ReinjectSystemPrompt`,
`HandleDeferredToolCalls`, `ProcessHistory`, `ProcessEventStream`, `UseThreadExecutor`.

### Custom capabilities — `AbstractCapability`

```python
from pydantic_ai.capabilities import AbstractCapability

@dataclass
class MyCapability(AbstractCapability[MyDeps]):
    ...
```

Contribution methods: `get_instructions`, `get_model_settings`, `get_model`,
`get_toolset`, `get_native_tools`, `get_wrapper_toolset`, `get_ordering`, `for_agent`,
`for_run` (per-run state isolation — return a fresh instance).

Lifecycle hooks, all `async`, verified present on the installed class:

| Stage | `before_` | `after_` | `wrap_` | `on_*_error` |
|---|---|---|---|---|
| run | ✓ | ✓ | ✓ | ✓ |
| node run | ✓ | ✓ | ✓ | ✓ |
| model request | ✓ | ✓ | ✓ | ✓ |
| tool validate | ✓ | ✓ | ✓ | ✓ |
| **tool execute** | ✓ | ✓ | **✓** | ✓ |
| output validate | ✓ | ✓ | ✓ | ✓ |
| output process | ✓ | ✓ | ✓ | ✓ |

Plus `prepare_tools(ctx, tool_defs) -> list[ToolDefinition]` and `prepare_output_tools`.

```python
async def wrap_tool_execute(self, ctx, *, call, tool_def, args, handler) -> Any: ...
async def prepare_tools(self, ctx, tool_defs: list[ToolDefinition]) -> list[ToolDefinition]: ...
```

`wrap_tool_execute` + `prepare_tools` + `tool_def.metadata` is exactly the pair needed to
enforce an access policy in one place for all current and future tools.

⟲ The shipped `IdentityGate` uses `wrap_tool_execute` + `prepare_tools` but not `metadata` — it
keys on `tool_def.name` instead. Nothing in the codebase sets `ToolDefinition.metadata`. See the
⟲ in §2.

---

## 5. Pydantic AI Harness — guardrails

⟲ **Research only.** None of this shipped: the package was never used and is no longer a
dependency, so the enforcement it describes is done by `agent.output_validator` instead
(DESIGN.md §5.4). The findings below stand for the day a second agent makes reuse worth a
`0.x` dependency.

`pydantic-ai-harness` 0.14.0. Verified signatures (`inspect.signature`):

```python
from pydantic_ai_harness import (
    InputGuardrail, OutputGuardrail, GuardrailResult,
    InputBlocked, OutputBlocked, GuardrailError,
)

InputGuardrail(guard, parallel: bool = False, *, id=None, description=None, defer_loading=False)
OutputGuardrail(guard, *, id=None, description=None, defer_loading=False)
GuardrailResult(*, action: Literal['allow','block','replace','retry'], message=None, replacement=None)
```

Constructed via classmethods:

```python
GuardrailResult.allow()
GuardrailResult.block(message: str | None = None)
GuardrailResult.replace(value: object)
GuardrailResult.retry(message: str)      # OutputGuardrail only
```

Verified from `guardrails/_capability.py`:

- A guard returns `bool | GuardrailResult` (or an awaitable of either). Bare `True` = allow.
- **`_takes_ctx(func)` inspects the signature** — a guard *may* take `RunContext` as its
  first parameter and the framework detects it. Line 170:
  `outcome = guard(ctx, value) if _takes_ctx(guard) else guard(value)`.
- `InputGuardrail` may **not** return `.retry()` (line 309 raises `UserError`).
- `InputGuardrail(parallel=True)` is incompatible with `.replace()` (line 318).
- `OutputGuardrail` receives the **typed output object unchanged** — not stringified — so a
  guard can inspect an `AgentReply` model's fields directly.
- `OutputGuardrail.retry()` sends the output back to the model for another attempt. This is
  the mechanism for *deterministically enforcing* a business rule that the model must act on.
- Streaming caveat: `OutputGuardrail` inspects the final output only; with `run_stream()`
  chunks already reached the caller, so `block`/`replace` cannot un-send them.

Registration is via `capabilities=[...]`, same as any capability:

```python
agent = Agent('...', capabilities=[InputGuardrail(guard=no_secrets), OutputGuardrail(guard=no_pii)])
```

### Other Harness capabilities considered

`CodeMode` (Monty Rust-sandboxed Python that orchestrates tools in one call), `Subagents`,
`FileSystem`, `Shell`, `Memory`, `Planning`, `Compaction`, `ToolOutputLimits`,
`StepPersistence`, `ConversationSearch`, `RepoContext`, `Skills`, `ExaSearch`,
`DynamicWorkflow`, `ManagedPrompt`. Why each is *not* used here → DESIGN.md §7.

---

## 6. Structured output

⟲ **Research only — none of this is used.** `output_type` is plain `str` and the agent has no
output tool at all. Read to the end of the section for why.

```python
agent = Agent('...', output_type=AgentReply)
result = await agent.run(prompt, deps=deps)
result.output          # AgentReply
result.usage           # RunUsage: input_tokens, output_tokens, requests
result.all_messages()  # full message history
```

Modes: `ToolOutput` (default, via tool call), `NativeOutput` (provider structured-output
feature), `PromptedOutput` (schema injected into instructions, model returns JSON text).

`@agent.output_validator` runs after parsing and may `raise ModelRetry(...)`. Check
`ctx.partial_output` to skip side effects while streaming.

**Groq note:** not every Groq model supports native structured output; `ToolOutput` (the
default) is the portable choice and is what this project uses.

⟲ `PromptedOutput`, behind an `output_mode` setting, was tried and reverted. With the schema in
the instructions, `gpt-oss` invented a tool named `json` / `agent_reply` and called that instead
of answering. `ToolOutput` is reliable on the same model once `parallel_tool_calls=False` and
`groq_reasoning_format="hidden"` are set on `GroqModelSettings` — the failure was never the
output mode.

⟲⟲ Both halves of that sentence have since reversed, and the whole of §6 is now research only.

- **`output_type` is plain `str`.** There is no output tool at all — not `PromptedOutput`, not
  `ToolOutput`, not an `AgentReply` output type. Every mode above still works as documented;
  none of them is used. Measured on the failing scenario: `AgentReply` behind an output tool
  succeeded 2/4, plain `str` 4/4. `AgentReply` survives as an ordinary response model assembled
  by the runtime after the run — `message` from `result.output`, the rest read off the
  transcript — so it is no longer something the model has to call correctly.
- **`groq_reasoning_format` is `"parsed"`, not `"hidden"`.** See §7.

`@agent.output_validator` still applies with `output_type=str`, and is what enforces escalation
(`escalation_is_honoured`).

---

## 7. Models — Groq

```bash
uv add "pydantic-ai-slim[groq]"
export GROQ_API_KEY=...
```

```python
from pydantic_ai import Agent
agent = Agent('groq:llama-3.3-70b-versatile')

# or explicitly
from pydantic_ai.models.groq import GroqModel
from pydantic_ai.providers.groq import GroqProvider
model = GroqModel('llama-3.3-70b-versatile', provider=GroqProvider(api_key='...'))
```

`GroqModelName` (verified via `typing.get_args`) is a `Literal[...] | str` union, so any
Groq model id is accepted. The enumerated names are:

```
llama-3.1-8b-instant            llama-3.3-70b-versatile
openai/gpt-oss-120b             openai/gpt-oss-20b
meta-llama/llama-4-maverick-17b-128e-instruct
meta-llama/llama-guard-4-12b    openai/gpt-oss-safeguard-20b
meta-llama/llama-prompt-guard-2-22m / -86m
whisper-large-v3 / -turbo       playai-tts / playai-tts-arabic
```

**Chosen default: `groq:openai/gpt-oss-120b`** — the strongest tool-caller in the list.
`llama-3.3-70b-versatile` is the documented fallback. Read from the `MODEL_NAME` env var.

⟲ The shipped default is **`openai/gpt-oss-20b`**, read from `TOKOKITA_MODEL_NAME`
(`Settings.model_name`). Chosen on measurement, not on the paper ranking above — run against the
real scenarios: `gpt-oss-20b` 4/4, `llama-3.3-70b-versatile` 3/4 (failed a public-catalog
question), `gpt-oss-120b` and `qwen3.6-27b` untestable that day, daily token quota exhausted.
`GroqModelName` is still a `Literal[...] | str` union, so 120b remains one env var away.

### `groq_reasoning_format` — ⟲ `"parsed"`, not `"hidden"`

The default is **`"parsed"`** (`Settings.reasoning_format`, `Literal["hidden","raw","parsed"] |
None`, empty string means off for a non-reasoning model that would reject the parameter).
Measured on `gpt-oss-20b`: parsed 3/3, hidden 1/3.

`"hidden"` only *suppresses* the reasoning. The model still writes its analysis into the
**content** channel whenever it decides no tool is needed, and Groq then rejects the response
with a 400 `output_parse_failed`. `"parsed"` gives the reasoning its own field, which
pydantic-ai maps to a `ThinkingPart` — out of the content channel entirely. Anywhere above or in
§6 that recommends `"hidden"`, read `"parsed"`.

`parallel_tool_calls=False` is unchanged and still required: every tool shares one
connection.

### Free-tier limits

Per model: **200,000 tokens/day** and 8,000 tokens/minute (12,000 for
`llama-3.3-70b-versatile`). One turn costs roughly 2k tokens, so heavy testing exhausts a model
for the day. The per-minute 429 is what SDK retry is for; **the daily-quota 429 is not
retryable inside a request** — the only move is a different model id.

⟲ A tenacity retry transport (`AsyncTenacityTransport`) under the Groq client was written and
removed. Raising from inside an httpx transport hides the response from the SDK, which then
reports a 429 as `APIConnectionError: Connection error` — the rate limit becomes invisible,
which is the one thing you need to see on a 200k/day quota.
`AsyncGroq(max_retries=settings.http_retries)` honours `Retry-After` and maps 429 to a proper
`RateLimitError`, so there is nothing left to add and the `[retries]` extra is no longer
installed.

---

## 8. Logfire

Verified `logfire.configure()` signature (installed 4.39.0), abridged to what matters:

```python
logfire.configure(
    local: bool = False,
    send_to_logfire: bool | Literal['if-token-present'] | None = None,
    token: str | list[str] | None = None,
    service_name: str | None = None,
    service_version: str | None = None,
    environment: str | None = None,
    console: ConsoleOptions | Literal[False] | None = None,
    additional_span_processors: Sequence[SpanProcessor] | None = None,   # <-- key
    metrics: MetricsOptions | Literal[False] | None = None,
    scrubbing: ScrubbingOptions | Literal[False] | None = None,
    sampling: SamplingOptions | None = None,
    min_level: int | LevelName | None = None,
    distributed_tracing: bool | None = None,
    advanced: AdvancedOptions | None = None,
)
```

`additional_span_processors` is a **top-level parameter**, not inside `AdvancedOptions`.
(`AdvancedOptions` holds `base_url`, `id_generator`, `ns_timestamp_generator`,
`log_record_processors`, `exception_callback`, `resource_detectors`, …)

`send_to_logfire='if-token-present'` is the exact value that makes cloud export optional
without any try/except.

Instrumentors present in 4.39.0 (verified from `dir(logfire)`), signatures checked:

```python
logfire.instrument_fastapi(app, *, capture_headers=False, request_attributes_mapper=None,
                           excluded_urls=None, record_send_receive=False, extra_spans=False)
logfire.instrument_pydantic(record='all', include=(), exclude=())
logfire.instrument_pydantic_ai(obj=None, *, include_content=None, version=None, ...)
logfire.instrument_sqlite3(conn=None)
```

⟲ `instrument_sqlalchemy()` replaced this and does emit query spans (`connect`, `SELECT ...`),
verified with an in-memory exporter before being wired in.

⟲ `instrument_sqlite3` was wired up and removed: it emitted **zero spans** — none for
`aiosqlite`, which runs `sqlite3` on a worker thread, and none for plain `sqlite3` in this
environment either. The `conn=None` global-patch form was the one tried.

`instrument_httpx(capture_headers=False)` is the one that earns its place and is verified
working: **3 spans per turn**. It is what makes the Groq SDK's own 429 retries visible — exactly
what was invisible while a rate limit was being misread as a connection error (§7).

### Scrubbing / PII

```python
logfire.configure(scrubbing=logfire.ScrubbingOptions(
    extra_patterns=[...],            # regexes, combined with the defaults
    callback=fn,                     # (ScrubMatch) -> None to redact | value to keep
))
```

Defaults already cover `password`, `secret`, `credential`, `api[._ -]?key`, `session`,
`cookie`, `credit[._ -]?card`, `jwt`, `ssn`, … matching both keys and values.

⚠ **Critical, from the scrubbing docs:** *"scrubbing is intentionally disabled for LLM
message attributes to prevent false positives."* So Logfire's built-in scrubber will **not**
redact PII inside `gen_ai.*` prompt/completion attributes. Redacting customer email/phone in
traces therefore has to be done by the application before the data reaches a span — it
cannot be delegated to `ScrubbingOptions`. This is why `shared/telemetry.py` records
`customer_id` and never the contact used to look someone up (DESIGN.md §8).

---

## 9. Arize Phoenix + OpenInference

```bash
docker run -p 6006:6006 -p 4317:4317 arizephoenix/phoenix:latest
```

Verified signatures:

```python
from phoenix.otel import register
register(*, endpoint=None, project_name=None, batch=False, set_global_tracer_provider=True,
         headers=None, protocol=None, verbose=True, auto_instrument=False, api_key=None)

from openinference.instrumentation.pydantic_ai import OpenInferenceSpanProcessor
OpenInferenceSpanProcessor(span_filter: Callable[[ReadableSpan], bool] | None = None)
```

### The important finding — read the source, not the docs

`openinference/instrumentation/pydantic_ai/span_processor.py` (0.1.18):

```python
def on_end(self, span: ReadableSpan) -> None:
    openinference_attributes = dict(get_attributes(span.attributes))
    span._attributes = {**span.attributes, **openinference_attributes}   # additive, in-place
    if not span.status.status_code == StatusCode.ERROR:
        span._status = Status(status_code=StatusCode.OK)
    if should_export_span(span, self._span_filter):
        super().on_end(span)
```

Its own docstring: *"this processor only modifies span attributes in-place without
exporting them — it's designed to work alongside other processors."*

Three consequences that decide the whole observability wiring:

1. It **enriches, does not export**. It must be paired with a real exporting processor.
2. The merge is **additive** — original `gen_ai.*` attributes survive, so enrichment does
   not damage Logfire's own rendering of the same span.
3. It must be registered **before** the exporting processor. Ordering within
   `additional_span_processors` is registration order, and `BatchSpanProcessor` exports
   asynchronously afterwards, so the mutation is always already applied.

⇒ **One tracer provider (Logfire's) can serve both backends.** No second provider, no
`register()` fighting `logfire.configure()` over the global provider:

```python
logfire.configure(
    service_name='tokokita-cs-agent',
    send_to_logfire='if-token-present',
    additional_span_processors=[
        OpenInferenceSpanProcessor(),                                    # 1. enrich
        BatchSpanProcessor(OTLPSpanExporter(f'{PHOENIX}/v1/traces')),    # 2. export to Phoenix
    ],
)
```

Attribute keys the enricher reads (grepped from `semantic_conventions.py`): `gen_ai.*`
(`system.message`, `user.message`, `assistant.message`, `choice`, `tool.message`,
`tool.call.arguments`, `tool.call.result`, `conversation.id`), `events`,
`all_messages_events`, `pydantic_ai.all_messages`, `model_request_parameters`.

It reads **both** the v2 shape (`events` / `all_messages_events`) and the v3+ shape
(`pydantic_ai.all_messages`), so it is not pinned to `version=2` as the Phoenix docs imply.
`InstrumentationSettings` defaults to `version=5`; the project pins it explicitly and the
setting is exposed as an env var so it can be dropped to `2` if a Phoenix release regresses.

⟲ No env var in the end: `logfire.instrument_pydantic_ai(version=5)` is a literal in
`shared/telemetry.py`. A knob nobody has ever turned, for a regression that has not happened, is
one more setting to keep true.

Use HTTP/protobuf on port **6006** (`/v1/traces`), not gRPC 4317 — that is what
`opentelemetry-exporter-otlp-proto-http` speaks.

### Cost is Phoenix's job, not ours

Phoenix computes cost itself from `llm.token_count.*` + `llm.model_name` + `llm.provider`, and
Groq models are in its built-in pricing table. So recording token counts under the OpenInference
names is the whole of it — no manual price entry, and nothing to keep in sync when Groq
repricing lands.

---

## 10. Testing

```python
from pydantic_ai import models, capture_run_messages
from pydantic_ai.models.test import TestModel
from pydantic_ai.models.function import FunctionModel, AgentInfo
from pydantic_ai.messages import ModelResponse, ToolCallPart, TextPart

models.ALLOW_MODEL_REQUESTS = False          # hard stop on accidental real API calls

with agent.override(model=TestModel()):      # also overrides deps= and toolsets=
    ...

def scripted(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    if len(messages) == 1:
        return ModelResponse(parts=[ToolCallPart('track_shipment', {'order_id': 1})])
    return ModelResponse(parts=[TextPart('...')])

with agent.override(model=FunctionModel(scripted)):
    ...

with capture_run_messages() as messages:      # assert on the real conversation
    ...
```

`TestModel` auto-calls every registered tool and synthesises valid structured output —
good for smoke tests. `FunctionModel` scripts exact tool calls — required for asserting
guardrail and escalation behaviour. `TestModel` cannot emulate provider-executed native
tools (`override(native_tools=[])` if that ever matters here; it does not).

---

## 11. Decision framework: plain tool / capability / MCP / sub-agent / structured output

Derived from the above; applied concretely in DESIGN.md §7.

| Reach for | When | Why not the others |
|---|---|---|
| **Plain tool** (`@toolset.tool`) | One verb, one side effect or one lookup, the model decides *when* to call it and can handle the result on its own. | Anything less is over-engineering. Start here and only escalate when a *cross-cutting* concern appears. |
| **Capability** (`AbstractCapability`) | The behaviour is **cross-cutting**: it applies to *every* tool / *every* run / *every* output, and must keep applying to tools that don't exist yet. Needs lifecycle hooks, or bundles tools+instructions+settings as one installable unit. | A tool can't intercept other tools. Copy-pasting an `if` into each tool is the failure mode capabilities exist to remove — one forgotten paste is a security hole. |
| **Guardrail** (`InputGuardrail` / `OutputGuardrail`) | Screening **unstructured** input before spending tokens, or validating output before the caller sees it — especially when a violation should force the model to *retry* rather than fail. ⟲ Costs a `0.x` dependency, so not taken here. | A capability hook is the general form; a guardrail is the pre-built specialisation for the input/output boundary. Use the specialisation when it fits — less code to own. |
| **Output validator** (`@agent.output_validator`) | Validation that is purely a function of the output value and needs `ModelRetry`. | `OutputGuardrail` when the check needs run context (`ctx.messages`) or should be reusable across agents; a validator when it's local to this one agent's output type. |
| **MCP** (`capabilities=[MCP(...)]`) | Tools live in **another process or another team's service**, or you want to swap tool providers without redeploying. | Pure overhead when the tools are local functions over a local DB — you'd add a process boundary, serialisation, and a failure mode for nothing. |
| **Sub-agent** (`Subagents`) | Genuinely distinct *specialisations* with their own tool sets and instructions, where the parent's context would otherwise blow up, or you need per-delegate usage budgets and isolated history. | Every delegation costs a full extra model round-trip plus context hand-off. With <15 cohesive tools in one domain, a sub-agent buys latency and cost, not clarity. |
| **CodeMode** | Tool-call counts explode combinatorially (fan-out, loops over N items) and round-trips dominate latency. | With 2–4 tool calls per turn, the Monty sandbox is a dependency and a debugging surface with nothing to pay for it. |
| **Plain structured output** (`output_type=`) | The model just has to *report* — no side effect, no external state. | Don't invent a tool for something that is really the shape of the answer. |

**The governing question:** *does this behaviour belong to one action, or to every action?*
One action → tool. Every action → capability. The moment the answer is "every action" and
the implementation is a copy-pasted `if`, the abstraction is at the wrong altitude.

---

## 12. Message history, persistence, streaming — verified later

Researched after the sections above, once the code needed them. Same rules: signatures taken
from the installed `pydantic-ai-slim` 2.22.0.

### Transcript serialisation

```python
from pydantic_ai.messages import ModelMessagesTypeAdapter, sanitize_messages

ModelMessagesTypeAdapter.dump_json(messages) -> bytes
ModelMessagesTypeAdapter.validate_json(data)  -> list[ModelMessage]

sanitize_messages(messages, *, strip_system_prompts: bool = True,
                  allowed_file_url_schemes=('http','https'),
                  allowed_file_url_force_download=(), allow_uploaded_files=False,
                  resolved_tool_call_ids=()) -> list[ModelMessage]
```

`ModelMessagesTypeAdapter` is the canonical serialiser — a `TypeAdapter` over the message
union, so a part type added by a future release round-trips without a schema migration of ours.
`sanitize_messages` exists for exactly the persistence case, and `strip_system_prompts` already
defaults to `True`: instructions are re-injected on every run, so a stored copy only grows the
row and risks replaying a stale prompt.

### Nothing in a message marks the output tool

```python
typing.get_args(pydantic_ai.messages.ToolPartKind)   # ('tool-search', 'capability-load')
```

`ToolPartKind` covers those two and nothing else — there is no `'output'` kind. A transcript
reader therefore has to identify the agent's reply by the **output tool's name** (`final_result`
unless renamed) and fall back to a `TextPart`. With `output_type=str` (§6) it is always the
`TextPart` branch; the name branch is kept for the day an output tool comes back.

### `conversation_id` is what Phoenix files as `session.id`

```python
await agent.run(prompt, deps=deps, message_history=history, conversation_id=session_id)
await agent.run_stream(..., conversation_id=session_id)
```

Both accept it, and every child span reports it as `session.id`. Without it Phoenix files every
turn as its own session and multi-turn conversations cannot be read back as conversations —
which is most of what the Sessions view is for. Note that `session.id` matches Logfire's
`session` scrub pattern, so it needs a `ScrubbingOptions(callback=...)` that returns the value
for that path or it is redacted before export (§8).

### `event_stream_handler` is a callback, not a generator

```python
EventStreamHandler = Callable[[RunContext[AgentDepsT], AsyncIterable[Event]], Awaitable[None]]
```

It returns `Awaitable[None]`, so it **cannot yield into a response**. Streaming to SSE means the
handler pushes onto an `asyncio.Queue` while the run executes as a task, and the endpoint drains
the queue — which is also what keeps tool activity and text deltas in the order the run produced
them.

---

## Sources

- [Pydantic AI docs index (`llms.txt`)](https://pydantic.dev/docs/ai/llms.txt)
- [Tools](https://pydantic.dev/docs/ai/tools-toolsets/tools/index.md) ·
  [Dependencies](https://pydantic.dev/docs/ai/core-concepts/dependencies/index.md) ·
  [Output](https://pydantic.dev/docs/ai/core-concepts/output/index.md)
- [Capabilities overview](https://pydantic.dev/docs/ai/capabilities/overview/index.md) ·
  [Custom capabilities](https://pydantic.dev/docs/ai/capabilities/custom/index.md) ·
  [Instrumentation](https://pydantic.dev/docs/ai/capabilities/instrumentation/index.md)
- [Harness overview](https://pydantic.dev/docs/ai/harness/) ·
  [Guardrails](https://pydantic.dev/docs/ai/harness/guardrails/) ·
  [Subagents](https://pydantic.dev/docs/ai/harness/subagents/index.md)
- [Groq model](https://pydantic.dev/docs/ai/models/groq/) ·
  [Testing](https://pydantic.dev/docs/ai/guides/testing/index.md)
- [Logfire configuration](https://pydantic.dev/docs/logfire/manage/configuration/) ·
  [Scrubbing](https://pydantic.dev/docs/logfire/instrument/scrubbing/index.md) ·
  [Alternative backends](https://pydantic.dev/docs/logfire/guides/alternative-backends/index.md)
- [Phoenix — Pydantic AI tracing](https://arize.com/docs/phoenix/integrations/python/pydantic/pydantic-tracing) ·
  [OpenInference pydantic-ai instrumentation](https://github.com/Arize-ai/openinference/tree/main/python/instrumentation/openinference-instrumentation-pydantic-ai)
