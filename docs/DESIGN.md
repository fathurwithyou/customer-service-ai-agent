# DESIGN.md — TokoKita customer service agent

Written before the code. Its job is to argue the *shape* of the system: which abstractions
exist, where the boundaries are, and which alternatives were rejected and why.

Framework facts referenced here were verified against the installed packages — see
[`STACK_NOTES.md`](STACK_NOTES.md).

---

## 1. The failure mode this design exists to prevent

The obvious implementation is nine flat `@agent.tool` functions, each opening with

```python
if not ctx.deps.verified_customer:
    return "Maaf, saya belum bisa memverifikasi identitas Anda."
```

plus a system prompt listing the escalation rules. It demos fine. It is wrong in three ways,
and every structural decision below follows from one of them.

**(a) A copy-pasted check is advisory.** Nine pastes today, a tenth tool next sprint, one
forgotten paste, and the agent hands one customer another customer's shipping address. The
check is correct in every place it appears and useless in the place it doesn't.

**(b) A prompt rule is a suggestion.** "Escalate when the refund exceeds Rp 1.000.000" in the
system prompt is a request to a sampler. It will mostly be honoured. "Mostly" is not a control
for a rule about money.

**(c) A verified customer is not an authorised one.** Even with verification working,
`get_order_detail(order_id)` accepts an arbitrary integer. Andi verifies as Andi and then asks
for order 3, which belongs to Bunga. Identity was checked; *ownership* never was. These are
different questions and conflating them is the actual leak.

The design turns each of these from a thing that is *checked* into a thing that is *structurally
impossible* — or, where that is not achievable, into a thing that is decided by deterministic
code rather than by the model.

---

## 2. Layers

Each layer is replaceable without touching its neighbours. Dependencies point strictly downward.

| Layer | Module | Owns | Knows nothing about |
|---|---|---|---|
| Transport | `api/app.py` | HTTP, DI, status codes, the chat UI | agents, SQL |
| Turn lifecycle | `agents/support/runner.py` | intake, the run, persistence, the fallback reply | SQL, HTTP |
| Agent brain | `agents/support/` — `agent.py`, `instructions.py`, `output.py`, `deps.py` | model, instructions, run loop, output contract | SQL, HTTP |
| Enforcement | `guardrails/` | cross-cutting access and escalation rules | any one capability |
| Capabilities | `capabilities/*/capability.py`, `tools.py` | what the agent *can do*, and at which access level | HTTP, SQL |
| Services | `capabilities/*/services.py` | queries and business logic | the model, HTTP |
| Domain | `capabilities/*/policies.py`, `schemas.py` | business rules, vocabulary | I/O of any kind |
| Data | `shared/database.py`, `data/schema.sql`, `data/seed.sql` | persistence, ownership scoping | the agent |
| Shared | `shared/` — `results.py`, `message_store.py`, `transcript.py`, `settings.py`, `model_factory.py` | outcome vocabulary, conversation state, configuration, the model seam | any one capability |
| Observability | `shared/telemetry.py` | tracing, redaction | everything else |

The unit of structure is the **capability**: one folder per domain ability, holding its own tools,
service, schemas, and — where it has rules — its policies. `guardrails/` holds what belongs to no
single one of them.

**The scoping rule.** A capability owns a *domain ability* (a noun: orders, returns). A guardrail
owns a *cross-cutting rule* (a verb applied to everything: authorise, escalate). If a thing has to
know about every capability, it is not a capability. That is why the identity gate (§4) and the
escalation validator (§5.3) live in `guardrails/`, and why each capability declares its own tools'
access level instead of one global table knowing about all of them.

**Tools are thin adapters.** A tool converts the model's arguments into a service call and the
service's answer into something the model can narrate. SQL and business logic live in
`services.py`; rules live in `policies.py`.

**`policies.py` is the load-bearing module.** It is pure — no DB, no network, no model, no
`async`. Every business rule that the acceptance criteria name lives in one as a total function
over plain values: the address lock in `orders/`, the refund ceiling in `returns/`, escalation
signal detection in `tickets/`. This is what makes the guarantees testable in milliseconds
without a fixture, a mock, or an API key, and it is why `tests/test_guardrails.py` can assert the
*rules* rather than assert that some LLM happened to comply on one sampled run.

---

## 3. Ownership as a data-layer invariant

**Decision.** Every `Database` method that touches customer data takes `customer_id` as a
required parameter and emits `... AND customer_id = ?`. There is no method that fetches an order,
shipment, payment, return, or ticket without a customer scope, and the services above it carry
the same parameter through.

```python
async def order_row(self, order_id: int, customer_id: int) -> Row | None:
    # customer_id is not a filter that callers may pass -- it is part of the identity of the
    # question. "Show me order 3" is not answerable; "show me Bunga's order 3" is.
```

**Why this and not a check in the tool.** A check in the tool is a statement about one call
site. A required parameter is a statement about the type of every call site, and the type checker
enforces it on code that does not exist yet. Failure (a) and failure (c) both die here: an
unscoped read is not a bug you can write and forget to guard, it is a query the data layer
cannot express.

The cost is real and accepted: `get_order_detail` returns `None` for both "no such order" and
"not your order", so the tool cannot tell the customer which. That is the correct behaviour
anyway — distinguishing them is an enumeration oracle that confirms which order IDs exist.

**The two deliberate exceptions**, listed because an unaudited exception is how invariants rot:

- `customer_row(email | phone)` — unscoped by necessity: it is the primitive that
  *establishes* the scope. It is the sole entry point to identity and is reachable only through
  the `IDENTIFYING` access level in §4.
- `product_row(product_id | name)` — the catalog is public. Stock and price are not
  anyone's private data, and requiring verification to ask a product's price would be
  security theatre that damages the product.

---

## 4. Identity and authorisation as one cross-cutting rule

**Decision.** `guardrails/access_levels.py` holds the vocabulary and nothing else:

```python
class AccessLevel(StrEnum):
    PUBLIC = "public"              # catalog -- no identity needed
    IDENTIFYING = "identifying"    # establishes identity; cannot presuppose it
    CUSTOMER_SCOPED = "scoped"     # requires a verified customer
```

Each capability classifies **its own** tools, in its `capability.py`, next to the tools it is
classifying:

```python
# capabilities/orders/capability.py
ACCESS = {tool.__name__: AccessLevel.CUSTOMER_SCOPED for tool in TOOLS}
```

`agents/support/agent.py` merges the five maps into `TOOL_ACCESS` and hands the result to
`IdentityGate(AbstractCapability[SupportDeps])` in `guardrails/identity_gate.py`, which enforces
at two depths:

1. **`prepare_tools`** — scoped tools are removed from the tool list before the model sees them.
   The model cannot choose a tool that is not on the menu. This is the same idiom as
   `ReadOnlyShell.prepare_tools` in `crayon-rm-library`: *structurally absent* beats *instructed
   not to*.
2. **`wrap_tool_execute`** — a scoped call with no verified customer is refused before the
   function body runs. Redundant with (1) by design: (1) is ergonomics and token economy, (2) is
   the control. History replay, a deferred call, or a future capability re-adding a tool all
   route through (2).

**Why per-capability declarations and not one global table.** A single table would have to name
every tool in every domain — exactly the thing §2's scoping rule says is not a capability's
business, and one more file to remember when adding a domain. Declaring `ACCESS` beside the tools
keeps a capability self-contained: a new one is a folder, and the gate learns about it by being
handed the merged map.

**Unknown tool ⇒ deny.** A tool absent from `TOOL_ACCESS` is treated as `CUSTOMER_SCOPED`. Adding
a tool and forgetting to classify it makes it unavailable, never accidentally public — the
failure mode points at safety. A test asserts every registered tool has an explicit entry, so the
omission is caught at development time rather than silently degrading the tool surface.

**Why a capability rather than a decorator on each tool.** A decorator is still per-tool: it must
be applied, and it can be omitted. A capability is registered once on the agent and observes
every tool call including ones added later, which is precisely the scope of the rule. This is the
altitude question from `STACK_NOTES.md` §11 — *does this behaviour belong to one action or to
every action?* Identity belongs to every action. (It is an `AbstractCapability` in the framework's
sense — that is the only mechanism with the reach — but in this codebase's vocabulary it is a
guardrail, because it has to know about every capability.)

**Why `prepare_tools` + `wrap_tool_execute` and not `before_tool_execute`.** `wrap_` can decline
to call the handler at all and substitute a result. `before_` can only transform arguments; it
cannot stop the call.

**Honest limitation — this is identification, not authentication.** The schema has no password,
no OTP, no session token. Presenting an email address proves knowledge of an email address.
Accordingly:

- email or phone **verifies** (matches exactly one customer row),
- `order_id` **narrows context but does not verify** — an order number is printed on a package
  and is not a secret, and treating it as a credential would make a shipping label a password,
- verification is granted in exactly one place (`capabilities/identity/tools.py::get_customer`
  sets `deps.customer`), so swapping in a real OTP or session-token check touches that function
  and `runner.resolve_customer` — no other tool changes.

Documenting this beats pretending the demo is an auth system.

---

## 5. Escalation: policy decides, the model executes, the validator verifies

The five escalation triggers are not one kind of thing, and treating them uniformly is what
produces mush. They split cleanly:

**Computable from data** — refund value over Rp 1.000.000; data inconsistency (shipment
`delivered` while the customer says it never arrived); a request whose tool does not exist.

**Inferable from the message** — fraud, legal threats, safety issues, strong negative sentiment,
an explicit request for a human.

### 5.1 The refund ceiling: remove the model from the arithmetic

The important decision is what `create_return` does *not* accept:

```python
async def create_return(ctx, order_id: int, product_id: int, reason: str) -> ReturnRequest | ActionResult:
    #                                       ^ no refund_amount parameter, on purpose
```

If the refund amount were a tool argument, the model could name Rp 900.000 for a Rp 2.000.000
item and walk under the ceiling — the guard would be checking a number the guarded party chose.
The amount is instead derived by `ReturnService.request` from `order_items.quantity *
unit_price`. The threshold is then applied by `returns/policies.py::requires_escalation(amount)`
to a number that came from the database.

Over the ceiling, the service **does not create the return**. It returns a refusal carrying the
computed amount and the reason, which is both the honest result and the material the model needs
to write the Indonesian explanation. The tool then sets `deps.forced_escalation`, which makes the
handoff mandatory under §5.3 rather than optional. The rule is enforced at the point of action,
not at the point of narration.

### 5.2 Message-inferred triggers: classify before the run, not during it

`tickets/policies.py::detect_signals(message)` runs in `runner.classify` *before* `agent.run`,
and the signals it finds are placed on `SupportDeps`. An `@agent.instructions` fragment then
states, per turn, that escalation is mandatory and why.

**Why pre-run rather than a hook.** Detection is a pure function of the user's text. Running it
before the agent makes it deterministic, unit-testable without a model, costs zero tokens, and
does not depend on capability ordering. Signal detection is keyword- and regex-based over
Indonesian and English terms — crude, and deliberately biased toward false positives, because the
cost of a needless escalation is a slightly annoyed human agent and the cost of a miss is a fraud
report answered by a chatbot.

### 5.3 The output validator: reconcile the claim against the evidence

`AgentReply.escalated` is a claim the model makes about itself. `ctx.messages` is the record of
what it actually did. `guardrails/escalation.py` compares them, and `agent.py` registers it with
`agent.output_validator(escalation_is_honoured)` — the function is a plain function so that the
rule is testable, and importable, without an agent:

```python
async def escalation_is_honoured(ctx: RunContext[SupportDeps], reply: AgentReply) -> AgentReply:
    called = {
        part.tool_name
        for message in ctx.messages if isinstance(message, ModelResponse)
        for part in message.parts if isinstance(part, ToolCallPart)
    }
    if ctx.deps.escalation_required and "escalate_ticket" not in called:
        raise ModelRetry("Kasus ini wajib dieskalasi. Panggil escalate_ticket lebih dulu.")
    if reply.escalated and "escalate_ticket" not in called:
        raise ModelRetry("Jangan menyatakan sudah dieskalasi kalau escalate_ticket belum dipanggil.")
    return reply
```

Both directions matter. The first stops a required escalation being skipped. The second stops the
agent *reporting* an escalation it never performed — a failure that is worse than not escalating,
because it closes the loop with a human who believes a ticket is waiting for them.

`ModelRetry` sends the model back with the correction rather than failing the request, so the
common case is that the second attempt complies and the customer never sees an error.

A second validator checking that any tracking number in the reply appears verbatim in a tool
result was designed and then **cut** to keep the demo small. It remains the obvious next
addition: a fabricated tracking number is a specific, high-cost hallucination, and it is the one
grounding rule that is cheaply checkable without an LLM judge. For now that risk is carried by
the instructions and by `track_shipment` being the only source of the number.

### 5.4 Why output validators rather than Harness guardrails

`pydantic-ai-harness` ships `InputGuardrail` / `OutputGuardrail`, which were researched
(`STACK_NOTES.md` §5) and are a good fit on paper: `GuardrailResult.retry()` does what
`ModelRetry` does here.

They were **never used, and the dependency has been removed** — the package appears nowhere in
`pyproject.toml`. Nothing is lost in guarantees: `agent.output_validator` is core Pydantic AI,
receives the typed `AgentReply` unchanged, has access to `ctx.messages` and `ctx.deps`, and
drives the same retry loop. What the Harness would have added is reusability *across agents* and
a declarative registration site — worth having with a second agent, unjustified with one. The
seam is small: `escalation_is_honoured` is a plain function registered in one line, so wrapping
it in `OutputGuardrail(guard=...)` later is a one-line change. Dropping the package also removes
a `0.x`-versioned dependency from the critical path.

The name `guardrails/` in this codebase is the design vocabulary of §2, not a reference to that
package.

---

## 6. Tool results: a refusal is an answer, not an error

Write tools can fail for reasons that are *correct business outcomes*: the order already shipped,
the refund exceeds the ceiling, the order is already cancelled. These are not exceptions and must
not be raised.

- **Policy refusal → a typed result.** `ActionResult` is a `ResultCode` enum plus a human
  `detail`, and nothing else — `success` is a property derived from `code is ResultCode.OK`
  rather than a stored field, because two fields for one fact can disagree and then the
  interesting question becomes which one the caller read. The model receives a fact it can
  explain in Indonesian; the enum gives tests something exact to assert on.
- **Model error → `ModelRetry`** — a bad ID, a stale reference, a malformed argument. Recoverable
  in one more step, so it goes back to the model rather than ending the turn (the
  `crayon-rm-library` `_STALE_SLUG_HINT` pattern, in Indonesian).
- **Infrastructure failure → caught, logged, returned as a refusal** offering escalation. A
  `sqlite3.Error` must not become a 500 that strands the customer; the constraint is "handle
  tool/DB failures gracefully: acknowledge the limitation and offer escalation".

`update_shipping_address` is the canonical case. `orders/policies.py::can_change_address(status)`
returns a `Decision`; `shipped` and `delivered` are refused with
`ResultCode.ORDER_ALREADY_SHIPPED`, and `Decision.as_result()` turns it into the `ActionResult`
the tool hands back. The rule is a pure function over a status, so the test asserts it directly
and needs no agent, model, or database.

---

## 7. What was rejected

| Rejected | Why it looked right | Why not |
|---|---|---|
| **Sub-agents** (`Subagents`) | The brief invites considering one; "escalation specialist" sounds tidy. | One cohesive domain, nine tools, one short conversation. Every delegation is an extra model round-trip plus a context hand-off, and the sub-agent would need the same DB scope and the same identity gate — so it duplicates the hard part and adds latency. Sub-agents earn their cost when contexts genuinely diverge; these don't. |
| **MCP** | The tool layer is cleanly separable. | MCP buys a *process boundary*. Here the tools are local functions over a local SQLite file. Adding MCP adds serialisation, a server lifecycle, and a new failure mode, and buys nothing. It becomes right the day the marketplace DB belongs to another team behind a service. |
| **CodeMode** | Fewer round-trips is appealing. | It pays off when tool calls fan out combinatorially. A turn here is 2–4 calls. The Monty sandbox would be a dependency and a debugging surface with no round-trips to save. |
| **Harness guardrails** | Purpose-built for exactly this. | Researched, never used, dependency removed; `agent.output_validator` provides the same enforcement. See §5.4. |
| **SQLAlchemy** | Postgres portability, pooling. | The whole persistence seam is ~10 queries. The ORM layer would duplicate models that already exist as Pydantic models, and pooling is meaningless against local SQLite. `aiosqlite` + a repository *is* the swappable seam; the SQL is standard enough that Postgres is a driver change plus the dialect notes in the brief's appendix. |
| **A `verified: bool` flag on `SupportDeps`, checked in tools** | Simplest thing that could work. | This is failure (a) verbatim. The flag is fine — `SupportDeps.customer` carries it — but the *checking* must not be per-tool. |
| **LLM-judge grounding on every reply** | Would catch all hallucination, not just tracking numbers. | A second model call per turn, non-deterministic, and unaffordable in the request path. Belongs in an offline eval suite (as in `crayon-rm-library/evals/`), not in `/chat`. Noted as future work. |

### Tried, then reverted

These were built and removed. Recorded so they are not rediscovered as good ideas.

| Reverted | Why it failed |
|---|---|
| **`PromptedOutput`**, behind an `output_mode` setting | Injecting the schema into the instructions made `gpt-oss` invent a tool named `json` / `agent_reply` and call *that* instead of answering. The default `ToolOutput` is correct here once `parallel_tool_calls=False` and `groq_reasoning_format="hidden"` are set on `GroqModelSettings`. |
| **A tenacity retry transport** under the Groq client | Raising from inside an httpx transport hides the response from the SDK, so a 429 surfaced as "Connection error" and the rate limit became invisible. `AsyncGroq(max_retries=...)` honours `Retry-After` and raises a real `RateLimitError`. |
| **`logfire.instrument_sqlite3`** | Zero spans: `aiosqlite` runs `sqlite3` on a worker thread. `instrument_httpx` is instrumented instead, and it is what makes the Groq SDK's own retries legible. |

---

## 8. Observability

One tracer provider serves both backends, because `OpenInferenceSpanProcessor` **enriches spans
in place and additively without exporting them** (source read in `STACK_NOTES.md` §9):

```python
logfire.configure(
    send_to_logfire="if-token-present",
    additional_span_processors=[OpenInferenceSpanProcessor(), ToolCallInput(), BatchSpanProcessor(otlp)],
)
```

Registration order is the contract: enrich, then repair, then export. Because the enrichment
merges rather than replaces, Logfire still renders the original `gen_ai.*` attributes, so the
same span is legible in both dashboards without a second provider fighting over the global one.

`ToolCallInput` is carried over from `crayon-rm-library`: Phoenix parses `tool.parameters` into an
object on ingest and then crashes rendering it, and moves the same JSON to `input.value` where
Phoenix renders it and its evaluators read it. Rediscovering that would have cost an afternoon.

Beyond Pydantic AI and FastAPI the only instrumentor enabled is `instrument_httpx`, because it
makes the Groq SDK's own 429 retries visible — precisely what was missing while a rate limit was
being misread as a connection error (§7). `instrument_sqlite3` was tried and dropped.

One non-obvious consequence of not using `phoenix.otel.register()`: it is what normally sets the
`openinference.project.name` **resource** attribute, so without setting it ourselves every trace
lands in Phoenix's `default` project. `logfire.configure(resource_attributes=...)` supplies it.

**Verified, not assumed:** with Phoenix running, one `/chat` turn produced ten spans in the
`tokokita-cs-agent` project with the correct OpenInference kinds (`agent`, `llm`, `tool`) — which
is itself the evidence that the enrichment processor ran — and the same spans were observed in
Logfire's own export pipeline. Logfire *cloud* ingestion is unverified: it needs a token, and
there is none in this environment.

**PII redaction cannot be delegated to Logfire.** Its scrubber is *intentionally disabled for LLM
message attributes* to avoid false positives, so customer emails and phone numbers inside
`gen_ai.*` prompts are not covered by `ScrubbingOptions`. Redaction therefore happens in
application code before values reach a span, and the customer identifier recorded on spans is
`customer_id`, never the email or phone used to look them up. `send_to_logfire="if-token-present"`
keeps the whole stack runnable with no credentials at all.

---

## 9. Testing strategy

The point of §3–§5 is that the guarantees are testable without an LLM. 43 tests, no API key,
under a second.

- **`test_services.py`** — the service layer with no model in sight: customer scoping (Bunga's
  order is invisible to Andi), refund derived from `order_items`, Pydantic validation rejecting
  bad input, policy refusals. Tools are adapters, so testing them would test the adapter; the
  logic under test lives here.
- **`test_guardrails.py`** — the four acceptance rules as *rules*: the address-change decision
  table, the refund ceiling, escalation signal detection, and the identity gate's effect on the
  offered tool surface.
- **`test_api.py`** — the HTTP surface end to end, with `FunctionModel` scripting the tool calls
  so the assertions are about our code rather than about what a sampled completion happened to
  say.

The tool surface assertion uses `TestModel(call_tools=[])` plus
`model.last_model_request_parameters.function_tools` to check *which tools were offered* before
and after verification — the `crayon-rm-library` `test_approval_mode.py` pattern. It tests the
structural claim in §4 rather than a sampled behaviour.

`models.ALLOW_MODEL_REQUESTS = False` in `conftest.py` makes an accidental real Groq call a test
failure rather than a bill. No test needs `GROQ_API_KEY`.

---

## 10. Conversation state

**Decision.** `shared/message_store.py` persists the whole turn history to a `conversations`
table through `ModelMessagesTypeAdapter` — the framework's own wire format — rather than a shape
of our own that would need migrating every time a part type changes. `sanitize_messages` strips
system prompts before saving: instructions are re-injected on every run, so keeping them only
grows the row and risks replaying a stale prompt. A trailing window is kept, not the full
history, because context is finite.

An in-process dict would have been shorter and is what the demo started with. It loses every
conversation on redeploy and is wrong the moment there is a second worker, and SQLite is already
open — so the cheap version costs a table, not a service.

Reading it back is a separate concern: `shared/transcript.py` reduces the stored messages to
`(role, text, tools)` turns, which is what `GET /chat/{session_id}` returns. Nothing in a message
marks the output tool, so the agent's reply is located by the output tool's name with a
`TextPart` fallback, and tool calls that drew a retry are excluded — they never ran.

The chat UI at `/` (`api/static/index.html`) is one static file with no build step, deliberately:
it exists so the agent can be tried without curl, and it appends each exchange to the page rather
than re-reading the transcript endpoint.
