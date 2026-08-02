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
| Web | `frontend/` (React + Vite, built into `api/static/`) | rendering, SSE consumption | SQL, the agent's internals |
| Transport | `api/app.py` | HTTP, DI, status codes, SSE framing, serving the SPA | agents, SQL |
| Turn lifecycle | `agents/support/` — `runner.py`, `streaming.py`, `output.py` | intake, the run, the assembled turn result, persistence, the fallback reply | SQL, HTTP |
| Agent brain | `agents/support/` — `agent.py`, `instructions.py`, `deps.py` | model, instructions, run loop, capability wiring | SQL, HTTP |
| Enforcement | `guardrails/` | cross-cutting access and escalation rules | any one capability |
| Capabilities | `capabilities/*/capability.py`, `tools.py` | what the agent *can do*, whether it needs a verified customer, and what the customer is told while it runs | HTTP, SQL |
| Services | `capabilities/*/services.py` | queries and business logic | the model, HTTP |
| Domain | `capabilities/*/policies.py`, `schemas.py` | business rules, vocabulary | I/O of any kind |
| Data | `shared/database.py`, `data/tables.py`, `data/seed.py` | engine, session scope, the schema itself | the agent |
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

The five folders are `customers`, `catalog`, `orders`, `returns`, `tickets`. `customers` was
called `identity` — the one abstract name in a list of concrete ones, and a name that described a
*concern* the guardrail layer actually owns rather than the table the folder reads. The folder
looks customers up; `guardrails/identity_gate.py` is what decides what identity means. Names that
sort into the same list should be the same kind of word. `IdentityService` became `CustomerLookup`
for the same reason — it has one method and it finds a customer.

Ruff enforces `PLC0415` (no imports inside functions), which is a structural rule rather than a
style one: an import buried in a function body is a dependency that does not appear in the file's
header, and the claim that "dependencies point strictly downward" is only checkable if every
dependency is declared where it can be read.

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

**Decision.** Every service method that touches customer data takes `customer_id` as a required
parameter and puts it in the `WHERE` clause. There is no method that fetches an order, shipment,
payment, return, or ticket without a customer scope.

⟲ This used to be structurally enforced: a `Database` class with no unscoped method to call.
Moving to SQLAlchemy sessions (§7) gave that up — a service holds an `AsyncSession` and could
write an unscoped `select()`. The guarantee is now a convention plus `OrderService._owned`, and
`tests/test_services.py` asserts the isolation directly rather than trusting it.

```python
def _owned(self, order_id: int, customer_id: int):
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
  *establishes* the scope. It is the sole entry point to identity, and the tool above it is
  classified `OPEN` for the same reason: a caller cannot be required to be verified in order to
  become verified (§4).
- `product_row(product_id | name)` — the catalog is public. Stock and price are not
  anyone's private data, and requiring verification to ask a product's price would be
  security theatre that damages the product.

---

## 4. Identity and authorisation as one cross-cutting rule

**Decision.** `guardrails/access_levels.py` holds the vocabulary and nothing else:

```python
class AccessLevel(StrEnum):
    OPEN = "open"
    VERIFIED_CUSTOMER = "verified_customer"
```

**Two members, not three.** An earlier version had a third, `IDENTIFYING`, for `get_customer` —
the tool that establishes identity and therefore cannot presuppose it. But the gate only ever
asks one question: *does this tool need a verified customer?* `IDENTIFYING` and the open level
answered that question identically and differed only in *why*, so the third member named a
justification, not a behaviour — and a distinction the code never branches on is a distinction
that will eventually be read as one it does. Why `get_customer` is open is a fact about the
domain (§3), not a level in an enum.

Each capability classifies **its own** tools, in its `capability.py`, next to the tools it is
classifying, and beside each tool's customer-facing activity phrase:

```python
# capabilities/orders/capability.py
ACCESS = {tool.__name__: AccessLevel.VERIFIED_CUSTOMER for tool in TOOLS}
ACTIVITY = {"track_shipment": "Melacak posisi paket", ...}
```

`ACTIVITY` is what the customer is shown while that tool runs (§11). It sits here because the
capability is the only place that knows both that the tool exists and what it does in the
customer's words — a central table would drift from the tools it describes, and the tool's own
name ("track_shipment") is not a sentence anyone should be shown.

`agents/support/agent.py` merges the five maps into `TOOL_ACCESS` and hands the result to
`IdentityGate(AbstractCapability[SupportDeps])` in `guardrails/identity_gate.py`, which owns
three hooks:

1. **`prepare_tools`** — tools needing a customer are removed from the tool list before the model
   sees them. The model cannot choose a tool that is not on the menu, and no tokens go on a
   refusal it would then have to explain. Same idiom as `ReadOnlyShell.prepare_tools` in
   `crayon-rm-library`: *structurally absent* beats *instructed not to*.
2. **`wrap_tool_execute`** — a call needing a customer is refused before the function body runs
   when there is none. Redundant with (1) by design: (1) is ergonomics and token economy, (2) is
   the control. History replay, a deferred call, or a future capability re-adding a tool all
   route through (2).
3. **`after_tool_execute`** — the privilege transition. When the configured lookup tool
   (`verifies_with`, default `get_customer`) returns a `Customer`, the gate promotes the session
   by setting `ctx.deps.customer`.

**Why the transition moved into the gate.** `get_customer` used to set `ctx.deps.customer`
itself. That put a security decision — *this session is now verified* — inside the capability
layer, in a tool whose job is a database read. Two things follow from moving it: the lookup tool
goes back to being a plain domain read that a test can call without granting anything, and the
only way a *tool result* can raise a session's privilege is one line in the module whose stated
subject is authorisation. Which tool is trusted to verify is now `verifies_with` on the gate,
rather than a fact scattered in a capability.

**Why per-capability declarations and not one global table.** A single table would have to name
every tool in every domain — exactly the thing §2's scoping rule says is not a capability's
business, and one more file to remember when adding a domain. Declaring `ACCESS` beside the tools
keeps a capability self-contained: a new one is a folder, and the gate learns about it by being
handed the merged map.

**Unknown tool ⇒ deny.** `needs_customer(name)` returns `True` for any tool absent from
`TOOL_ACCESS`. Adding a tool and forgetting to classify it makes it unavailable, never
accidentally public — the failure mode points at safety. A test asserts every registered tool has
an explicit entry, so the omission is caught at development time rather than silently degrading
the tool surface.

**Why a capability rather than a decorator on each tool.** A decorator is still per-tool: it must
be applied, and it can be omitted. A capability is registered once on the agent and observes
every tool call including ones added later, which is precisely the scope of the rule. This is the
altitude question from `STACK_NOTES.md` §11 — *does this behaviour belong to one action or to
every action?* Identity belongs to every action. (It is an `AbstractCapability` in the framework's
sense — that is the only mechanism with the reach — but in this codebase's vocabulary it is a
guardrail, because it has to know about every capability.)

**Why `wrap_tool_execute` and not `before_tool_execute` for the refusal.** `wrap_` can decline to
call the handler at all and substitute a result. `before_` can only transform arguments; it
cannot stop the call. The promotion is the mirror case and uses `after_`, because it is a
function of the tool's *return value*.

**Honest limitation — this is identification, not authentication.** The schema has no password,
no OTP, no session token. Presenting an email address proves knowledge of an email address.
Accordingly:

- email or phone **verifies** (matches exactly one customer row),
- `order_id` **narrows context but does not verify** — an order number is printed on a package
  and is not a secret, and treating it as a credential would make a shipping label a password,
- a session becomes verified in exactly two places, neither of them a tool:
  `runner.resolve_customer` seeds `SupportDeps.customer` from a contact the channel already
  carried, and `IdentityGate.after_tool_execute` promotes mid-run when the lookup tool returns
  one. Swapping in a real OTP or session-token check touches those two and nothing else.

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

### 5.3 The turn result is read, not claimed — and the validator enforces what is left

The agent's `output_type` is **plain `str`**. There is no output tool, and the model is asked for
one thing: the sentence the customer reads.

`AgentReply` still exists, but it is now the *turn result assembled by the runner*, not the
model's output. `message` comes from the model. `escalated` and `ticket_id` are read from the
transcript by `shared/transcript.py::outcome` — the first from whether `escalate_ticket` was
called, the second from what `create_ticket` returned. `customer_name` is read from
`deps.customer` *after* the run, not from the value the turn opened with, because the gate may
have promoted the session mid-run. `action_taken` was deleted: nothing consumed it, and a field
only the model writes and only a log reads is a place for a claim to go unchecked.

**Why this and not a structured output tool.** Two reasons, one measured and one structural.

Measured: on the case that fails hardest — the customer is unverified and the correct behaviour
is to *ask* for a contact rather than call anything — the `AgentReply` output tool succeeded
2 runs in 4, plain `str` 4 in 4. With no output tool, the entire class of "model failed to
produce `final_result`" errors cannot occur: a model that decides no tool is needed and simply
writes text is now producing the output, not failing to.

Structural: asking the model to report `escalated` was asking it to restate a fact the runtime
already held, and a restatement can disagree with the fact. The **second branch of the escalation
guardrail is gone** as a consequence — "claimed an escalation that never happened" is no longer a
condition that can be checked, because it is no longer a condition that can arise. That is the
better outcome by the standard of §1: a rule that was *verified* became a rule that is
*impossible to break*.

What is left for `guardrails/escalation.py` is the direction the transcript cannot settle by
itself — a turn that *must* reach a human and didn't. `agent.py` registers it with
`agent.output_validator(escalation_is_honoured)`; it is a plain function so the rule is testable,
and importable, without an agent:

```python
async def escalation_is_honoured(ctx: RunContext[SupportDeps], reply: str) -> str:
    called = {
        part.tool_name
        for message in ctx.messages if isinstance(message, ModelResponse)
        for part in message.parts if isinstance(part, ToolCallPart)
    }
    if ctx.deps.escalation_required and "escalate_ticket" not in called:
        raise ModelRetry("Kasus ini wajib dieskalasi ke manusia. Panggil create_ticket bila ...")
    return reply
```

`ModelRetry` sends the model back with the correction rather than failing the request, so the
common case is that the second attempt complies and the customer never sees an error.

A second validator checking that any tracking number in the reply appears verbatim in a tool
result was designed and then **cut** to keep the demo small. It remains the obvious next
addition: a fabricated tracking number is a specific, high-cost hallucination, and it is the one
grounding rule that is cheaply checkable without an LLM judge. For now that risk is carried by
the instructions, by `track_shipment` being the only source of the number, and by refusals
carrying their own evidence (§6).

### 5.4 Why output validators rather than Harness guardrails

`pydantic-ai-harness` ships `InputGuardrail` / `OutputGuardrail`, which were researched
(`STACK_NOTES.md` §5) and are a good fit on paper: `GuardrailResult.retry()` does what
`ModelRetry` does here.

They were **never used, and the dependency has been removed** — the package appears nowhere in
`pyproject.toml`. Nothing is lost in guarantees: `agent.output_validator` is core Pydantic AI,
receives the output unchanged, has access to `ctx.messages` and `ctx.deps`, and drives the same
retry loop. What the Harness would have added is reusability *across agents* and
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
  `detail`, and nothing else. No `success` boolean beside the code: two fields for one fact can
  disagree, and then the interesting question becomes which one the caller read. A caller that
  wants the boolean writes `code is ResultCode.OK` where it needs it. The model receives a fact
  it can explain in Indonesian; the enum gives tests something exact to assert on.
- **Model error → `ModelRetry`** — a bad ID, a stale reference, a malformed argument. Recoverable
  in one more step, so it goes back to the model rather than ending the turn (the
  `crayon-rm-library` `_STALE_SLUG_HINT` pattern, in Indonesian).
- **Infrastructure failure → caught, logged, returned as a refusal** offering escalation. A
  dropped database connection must not become a 500 that strands the customer; the constraint is
  "handle tool/DB failures gracefully: acknowledge the limitation and offer escalation".

`update_shipping_address` is the canonical case. `orders/policies.py::can_change_address(status)`
returns a `Decision`; `shipped` and `delivered` are refused with
`ResultCode.ORDER_ALREADY_SHIPPED` and `cancelled` with `ResultCode.ORDER_CANCELLED`; the
service turns that decision into the `ActionResult` the tool hands back, appending the shipment
evidence where it has any. The rule is a pure function over a status, so the test asserts it
directly and needs no agent, model, or database.

**A refusal must carry its own evidence.** The refusal used to read "the parcel is already with
the courier, contact them" while supplying no courier and no tracking number. Observed in a real
conversation: the model filled the gap from earlier context and quoted the customer a **different
order's** tracking number. Nothing lied — the tool returned a true refusal and the model returned
a true fact about the wrong order. `OrderService.change_address` now looks up *that order's*
shipment and appends its courier and resi to the detail.

This is the grounding failure mode in miniature, and it generalises: an instruction that implies
a fact the tool result does not contain is an invitation to hallucinate, and the fix belongs in
the result rather than in a warning added to the prompt. A gap the model can see is a gap the
model will fill.

---

## 7. What was rejected

| Rejected | Why it looked right | Why not |
|---|---|---|
| **Sub-agents** (`Subagents`) | The brief invites considering one; "escalation specialist" sounds tidy. | One cohesive domain, nine tools, one short conversation. Every delegation is an extra model round-trip plus a context hand-off, and the sub-agent would need the same DB scope and the same identity gate — so it duplicates the hard part and adds latency. Sub-agents earn their cost when contexts genuinely diverge; these don't. |
| **MCP** | The tool layer is cleanly separable. | MCP buys a *process boundary*. Here the tools are local functions over a local database. Adding MCP adds serialisation, a server lifecycle, and a new failure mode, and buys nothing. It becomes right the day the marketplace DB belongs to another team behind a service. |
| **CodeMode** | Fewer round-trips is appealing. | It pays off when tool calls fan out combinatorially. A turn here is 2–4 calls. The Monty sandbox would be a dependency and a debugging surface with no round-trips to save. |
| **Harness guardrails** | Purpose-built for exactly this. | Researched, never used, dependency removed; `agent.output_validator` provides the same enforcement. See §5.4. |
| ~~**SQLite**~~ ⟲ **reversed** | Zero setup, one file, right for a demo. | It has no `JSONB`, so the message payload was `TEXT` that every reader re-parses and no index can reach into — and the payload is the one column worth querying into. It was also hiding two real defects that Postgres surfaced on the first run: tz-aware timestamps written into a naive column, and `TestClient` driving an asyncpg connection from a foreign event loop. The demo cost is one `docker compose up -d db`. |
| ~~**SQLAlchemy**~~ ⟲ **reversed** | Originally rejected: ~10 queries, and pooling is meaningless against local SQLite. | The argument was about query volume and missed the real cost — a hand-rolled `Database` class is a persistence interface nobody else knows, and `schema.sql` was a second declaration of the same tables that could silently drift from the code reading them. SQLAlchemy 2.0 async is the interface people already know: `Base.metadata` *is* the schema, `session_scope` *is* the transaction boundary, and `instrument_sqlalchemy` gives DB spans that `instrument_sqlite3` never could. The price is stated in §3 — scoping is no longer structurally unreachable. |
| **A `verified: bool` flag on `SupportDeps`, checked in tools** | Simplest thing that could work. | This is failure (a) verbatim. The flag is fine — `SupportDeps.customer` carries it — but the *checking* must not be per-tool. |
| **A structured `output_type` for the whole reply** | One typed object, validated by the framework, is the Pydantic AI house style. | An output tool is one more thing the model can fail to call, and every field but `message` was the model restating what the runtime already knew. Measured worse on the hardest case; see §5.3. Structure that is *derived* costs the model nothing and cannot disagree with the run. |
| **LLM-judge grounding on every reply** | Would catch all hallucination, not just tracking numbers. | A second model call per turn, non-deterministic, and unaffordable in the request path. Belongs in an offline eval suite (as in `crayon-rm-library/evals/`), not in `/chat`. Noted as future work. |

### Tried, then reverted

These were built and removed. Recorded so they are not rediscovered as good ideas.

| Reverted | Why it failed |
|---|---|
| **`PromptedOutput`**, behind an `output_mode` setting | Injecting the schema into the instructions made `gpt-oss` invent a tool named `json` / `agent_reply` and call *that* instead of answering. Superseded anyway: there is no structured output left to prompt for (§5.3). |
| **The `AgentReply` output tool** | On the turn where the model must ask for a contact instead of answering, it produced no `final_result` half the time (2/4 vs 4/4 for plain `str`). The reply is now `str` and the structure is assembled from the transcript. |
| **`AgentReply.action_taken`** | A free-text field the model wrote and nothing read. Unread output is unverified output; deleting it removed a claim rather than adding a check. |
| **`AccessLevel.IDENTIFYING`** | A third level the gate treated exactly like `OPEN`. It documented why a tool was open, in a type whose only job is to decide whether a tool is open. §4. |
| **`get_customer` setting `ctx.deps.customer`** | A domain tool granting its own session the privilege it needs. Moved to `IdentityGate.after_tool_execute` so the security decision lives in the security layer. §4. |
| **The llama models as fallbacks** | Two more families means the rate limits exhaust separately, which is exactly what a fallback is for. | `llama-3.3-70b-versatile` never emits a tool call against this tool surface — it writes `<function=get_order_detail{...}</function>` into the *text* channel. Groq sometimes rejects that as `tool_use_failed` (400) and sometimes hands it back as content, and the second case **raises nothing**, so `FallbackModel` cannot see it and the customer is handed protocol noise as an answer. `llama-3.1-8b-instant` does call tools but grounded only 1/3. Measured on the real agent, then excluded. |
| **`groq_reasoning_format="hidden"`** | "hidden" only suppresses the reasoning; a thinking model still writes its analysis into the *content* channel when it decides no tool is needed, and Groq then fails to parse the response. `"parsed"` gives reasoning its own field and maps to a `ThinkingPart` (measured on `gpt-oss-20b`: parsed 3/3, hidden 1/3). |
| **A tenacity retry transport** under the Groq client | Raising from inside an httpx transport hides the response from the SDK, so a 429 surfaced as "Connection error" and the rate limit became invisible. `AsyncGroq(max_retries=...)` honours `Retry-After` and raises a real `RateLimitError`. |
| **`logfire.instrument_sqlite3`** | Zero spans: `aiosqlite` runs `sqlite3` on a worker thread. `instrument_sqlalchemy` replaces it now that the engine is SQLAlchemy's, and it does emit real query spans. |
| **`metadata=` on `agent.run` as a message field** | It reaches `RunContext.metadata` and the `invoke_agent` span, but `ModelMessage.metadata` stays `null` — so it is telemetry, not a substitute for the store's own columns. Verified against 2.22.0, not assumed. |
| **Trusting `state == 'interrupted'` to mark a dead run** | The framework writes it when a *tool* is cancelled, not when the model call raises. A crashed run therefore looks `complete`. The window instead drops any run holding a tool call with no return. |
| **An in-process dict for conversation history** | Lost every conversation on redeploy and wrong with a second worker. The durable version costs one table (§10). |

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

Beyond Pydantic AI and FastAPI, `instrument_httpx` is enabled because it makes the Groq SDK's own
429 retries visible — precisely what was missing while a rate limit was being misread as a
connection error (§7) — and `instrument_sqlalchemy` for query spans. `instrument_sqlite3` was
tried and dropped before the move to SQLAlchemy.

`conversation_id=session_id` on every run means the `session_id` column in the database and
`gen_ai.conversation.id` on the span are the same string, so a row and its trace are one lookup
apart.

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

The point of §3–§5 is that the guarantees are testable without an LLM. 62 tests, no API key,
a few seconds. They need Postgres up (`docker compose up -d db`) and own their own database:
the suite drops and recreates its schema, so it must never point at the demo data.

- **`test_services.py`** — the service layer with no model in sight: customer scoping (Bunga's
  order is invisible to Andi), refund derived from `order_items`, Pydantic validation rejecting
  bad input, policy refusals, and the refusal that must name its own order's courier (§6). Tools
  are adapters, so testing them would test the adapter; the logic under test lives here — which
  is why there is no `test_tools.py`.
- **`test_guardrails.py`** — the acceptance rules as *rules*: the address-change decision table,
  the refund ceiling, escalation signal detection, the gate's effect on the offered tool surface,
  its refusal when a scoped tool is reached anyway, and the promotion — that `after_tool_execute`
  verifies the session on the lookup tool's result and on nothing else.
- **`test_api.py`** — the HTTP surface end to end, with `FunctionModel` scripting the tool calls
  so the assertions are about our code rather than about what a sampled completion happened to
  say. One test scripts a model that escalates but never says so, and asserts the response
  reports `escalated=True` and the right `ticket_id` anyway — the §5.3 claim, at the HTTP layer.
  Another crashes the model mid-conversation and asserts the salvaged run is stored once rather
  than re-inserting the history it was handed.
- **`test_message_store.py`** — the persistence contract: append rather than rewrite, round-trip
  through the framework's own format, sessions kept apart, system prompts stripped.
- **`test_history.py`** — the model-facing window: whole runs only, and never a run holding a
  tool call with no return (§10).

The tool surface assertion uses `TestModel(call_tools=[])` plus
`model.last_model_request_parameters.function_tools` to check *which tools were offered* before
and after verification — the `crayon-rm-library` `test_approval_mode.py` pattern. It tests the
structural claim in §4 rather than a sampled behaviour.

The seed carries eight orders because several rules are otherwise unreachable: an order that is
still editable (4), one over the refund ceiling (5), an unpaid one (6), a cancelled one (7), one
marked delivered that the customer says never arrived (8), and a customer with no orders at all.
Orders 1–3 are fixed and asserted on; everything above is what makes the remaining paths — and a
demo — reachable.

`models.ALLOW_MODEL_REQUESTS = False` in `conftest.py` makes an accidental real Groq call a test
failure rather than a bill. No test needs `GROQ_API_KEY`.

---

## 10. Conversation state

**Decision.** One row per `ModelMessage` in `conversation_messages`, with the message itself
kept in the framework's own format.

The columns are only the fields pydantic-ai puts on *every* message — `kind`, `run_id`,
`state`, `timestamp`, and the `conversation_id` we key on. `payload` is a `JSONB` column declared
as `Mapped[ModelMessage]`: a `TypeDecorator` binds a Pydantic `TypeAdapter` to it, so validation
happens *at the column* and no layer above ever sees JSON. The store hands SQLAlchemy a
`ModelMessage` and gets a `ModelMessage` back. Everything below that (`parts`, and the
eleven part types under them) stays in `payload`, serialised by `TypeAdapter(ModelMessage)`.
That line is the whole design: **the framework owns the message shape, the database owns only
what we query on.** Normalising parts into tables would buy nothing and cost a migration every
time pydantic-ai adds a part type — and it has eleven already, including `ThinkingPart`,
`CompactionPart` and `NativeToolCallPart`.

Rows are appended from `result.new_messages()`, not rewritten from `all_messages()`. The blob
version rewrote the entire growing history on every turn.

`sanitize_messages` strips system prompts before saving: instructions are re-injected on every
run, so keeping them only grows the row and risks replaying a stale prompt.

**The store keeps everything; the window is a capability.** Trimming used to happen in the load
query, which quietly made the persistence layer responsible for a prompting decision. It is now
`ProcessHistory(recent_runs)` in `agents/support/history.py` — the framework's own seam for
"the database has the full history, the model sees part of it". The store is the audit record;
`agent.py` decides what is worth sending.

**The window is counted in runs, not messages.** Cutting at the 40th message can land between a
tool call and its return and leave the model a dangling reference; a run is atomic, so dropping
whole runs cannot.

A run that *died* is dropped for the same reason. `capture_run_messages` lets a crashed turn be
persisted instead of vanishing, but its last response can hold a tool call with no return, and
replaying that is a malformed request. `state == 'interrupted'` does not identify it — the
framework writes that only when a tool was cancelled, so a run whose model call raised still
reads `complete`. The window tests the thing that actually matters: every call in the run has a
matching return.

`UsageLimits(request_limit, total_tokens_limit)` bounds a single turn. A support turn that needs
more than eight model requests is looping, and the ceiling is a configured number rather than a
surprise on the Groq bill.

`ModelRequest.timestamp` is `datetime | None` — a request carries no timestamp until the model
answers — so `created_at` is nullable rather than invented. A test found this, not a reading of
the code.

### SQL or a document store

The access pattern — fetch every message for one key, append to one key, never join on message
content — is exactly what a document store is for, and MongoDB or DynamoDB would model it
without complaint.

SQL wins here on three specific grounds, none of them "we already had SQL":

- **Atomicity across domains.** A turn writes conversation messages *and* `ticket_messages`, and
  an escalating turn also writes `tickets`. Splitting the transcript into a second store means
  those stop being one transaction, and the failure it admits — a ticket with no conversation
  attached to it — is the one a support system cannot afford.
- **The questions the PRD actually asks** are joins. Containment rate is turns-per-conversation
  against escalations; CSAT is a rating against a customer. Both cross from conversation data
  into marketplace data.
- **`JSONB` is the document store.** It indexes inside the document and queries into it, so
  choosing SQL costs nothing on the document side. `payload -> 'parts'` is a real query against
  parsed JSON rather than a string every reader must re-parse — which is why the column is
  `JSONB` and, in turn, why the database is Postgres.

A second datastore for one table is operational surface with no compensating gain at this size.
The point at which that flips is volume: when transcripts outgrow the transactional store, the
right move is to keep the *columns* here and move `payload` to object storage or a document
store, which the split above already makes possible.

An in-process dict was the first version. It loses every conversation on redeploy and is wrong
the moment there is a second worker.

Only the transcript is stored. Who the customer is arrives as injected context on every request,
so a server-side copy of it would be a second source of truth that can drift from the one the
caller actually sent.

Reading it back is a separate concern, and it has two shapes. `transcript.read()` reduces the
stored messages to `(role, text, tools)` turns — what `GET /chat/{session_id}` returns so a
reloaded page can rebuild the conversation. `transcript.outcome()` extracts `escalated` and
`ticket_id` from what ran, which is what makes §5.3 possible. Both exclude tool calls that drew a
retry: those never executed. With no output tool the agent's reply is a `TextPart`; `read()` also
still recognises a `final_result` call, so a transcript stored before §5.3 remains readable.

---

## 11. The chat surface

**Decision.** `POST /chat/stream` returns server-sent events — `start`, `tool`, `delta`, `done` —
and is what the UI uses. `POST /chat` still answers a whole turn in one response, because a
programmatic caller wants the assembled `AgentReply` and not a parser.

`agents/support/streaming.py` is a plain `async for` over `agent.run_stream_events`, and the SSE
generator yields straight out of that loop.

⟲ It used to feed an `asyncio.Queue` from an `event_stream_handler`, because that handler is a
*callback* and cannot yield into a response. `run_stream_events` is the framework's own answer to
exactly that problem: it wraps `run`, hands back an async iterator, and ends with an
`AgentRunResultEvent` carrying the result. Adopting it deleted the queue, the background task,
and its sentinel — machinery that existed only to re-invert an inversion the library had already
undone. It is an async *context manager* for a reason worth keeping: a customer who closes the
tab stops the iteration, and the run is then torn down deterministically instead of leaking.

Two things cannot be streamed and arrive in the final `done` event: `escalated` and `ticket_id`
are read from the transcript once the run is over (§5.3), so there is no moment during the run at
which they are known.

Tool activity is reported using each capability's `ACTIVITY` phrase (§4) — "Melacak posisi
paket", never `track_shipment`. The tool name is an implementation detail of ours and reads to a
customer as a leak, not as progress.

Text deltas are coalesced to whole words before being sent. Character-level deltas flicker;
word-level deltas read.

The UI is a React 19 + Vite app in `frontend/`, built into `src/tokokita/api/static/` and served
by the same FastAPI app, mounted last so the API routes win. The build output is gitignored: it
is derived, and a checked-in bundle is a second copy of the frontend that can disagree with the
source.
