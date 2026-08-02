# WORKFLOW.md — the main agent's turn

One governing rule:

> **The model decides what to *say*. Code decides what is *allowed* and what is *true*.**

Everything below follows from it. The prompt (`agents/support/instructions.py`) carries only
judgment and posture — three principles, no procedure. Every rule the system actually *guarantees* is a
deterministic step outside the model, either before it runs, around each tool call, or after
it answers. Restating those rules in prose would only give them a second, drifting definition
— which is precisely how the "always call `get_customer` first" bug happened.

A turn has four phases. Three of them contain no model at all.

---

## The shape

```mermaid
flowchart TD
    REQ["POST /chat · POST /chat/stream"] --> P0

    subgraph P0["① INTAKE — deterministic, no model"]
        V["Validate<br/><i>api/app.py::ChatRequest</i>"] --> ID["Resolve identity<br/><i>runner.resolve_customer:<br/>email/phone verifies;<br/>order_id only narrows</i>"]
        ID --> SIG["Classify message<br/><i>tickets/policies.detect_signals</i>"]
        SIG --> INC["Cross-check record vs claim<br/><i>delivered but 'belum sampai'</i>"]
        INC --> HIST["Load history<br/><i>shared/message_store.py</i>"]
    end

    P0 --> DEPS(["<b>SupportDeps</b> — the turn's contract<br/>db · services · customer · escalation_signals"])
    DEPS --> P1

    subgraph P1["② GATING — deterministic, pre-model"]
        PT["IdentityGate.prepare_tools<br/><i>tools needing a customer are<br/>absent until there is one</i>"]
        DI["Dynamic instructions<br/><i>PELANGGAN line · mandatory escalation</i>"]
    end

    P1 --> P2

    subgraph P2["③ AGENT LOOP — model judgment"]
        M{"Model chooses"} -->|tool call| W["IdentityGate.wrap_tool_execute<br/><b>hard gate</b>"]
        W -->|refused| M
        W -->|allowed| T["Tool → service<br/><i>capability policy · typed outcome</i>"]
        T -->|ModelRetry| M
        T -->|data or ActionResult refusal| AF["IdentityGate.after_tool_execute<br/><i>lookup returned a Customer<br/>⇒ promote the session</i>"]
        AF --> M
        M -->|final answer| OUT["plain text<br/><i>no output tool</i>"]
    end

    OUT --> P3

    subgraph P3["④ VERIFY & COMMIT — deterministic, post-model"]
        OV{"guardrails/escalation.py<br/><i>must this turn reach a human,<br/>and did it?</i>"}
        OV -->|"must, didn't"| RETRY["ModelRetry"]
        OV -->|honoured| RD["Read the outcome<br/><i>transcript.outcome:<br/>escalated · ticket_id</i>"]
        RD --> C["Persist conversation + ticket_messages<br/>Record span attributes"]
    end

    RETRY -.->|back to the model| M
    C --> RESP["<b>AgentReply</b> assembled by the runner<br/>message from the model;<br/>the rest from the transcript"]

    P2 -.->|any exception| FB["Graceful fallback reply<br/><i>logged + span marked</i>"]
    FB --> RESP
```

`/chat/stream` runs the same four phases; the only difference is that phase ③ also emits `tool`
and `delta` events as it goes, and phase ④'s facts arrive in a final `done` event.

---

## ① Intake — establish the facts before the model sees anything

Four deterministic steps produce `SupportDeps`, which is the only thing the model's world is
built from. Each is a pure function of the request, so each is unit-testable without an API key.

| Step | Where | Why it is here and not in the prompt |
|---|---|---|
| Validate | `api/app.py::ChatRequest` | Malformed input never reaches an LLM. |
| Resolve identity | `runner.resolve_customer` | Email/phone verifies; an order id is printed on the parcel, so it narrows context but never authorises. |
| Classify escalation signals | `tickets/policies.py::detect_signals` | Keyword detection over the raw message. Deterministic, testable, costs zero tokens, and biased toward false positives on purpose. |
| Cross-check record vs claim | `tickets/policies.py::claims_not_received` + order status | "Delivered" in our data against "belum sampai" from the customer is a contradiction only a human can settle. |

`SupportDeps` is the turn's contract: the database handle and the services built over it, who we
believe the caller is, and whether this turn is already obliged to escalate. Services are
constructed there rather than reached for globally, so a test can build a turn against a
throwaway database without patching anything.

## ② Gating — shape what is even possible

Two things happen before the first token, both derived from `SupportDeps`:

**The tool surface is computed, not requested.** `IdentityGate.prepare_tools` removes every tool
that needs a verified customer while `deps.customer is None`. The model does not decline to use
them — it never sees them. That is cheaper (no tokens spent on a refusal it must then explain)
and stronger (it cannot choose what is not on the menu).

**Per-turn facts are injected**, not baked into the static prompt: who the caller is (or that
they are not yet known, and what to do about it), and — when intake found signals — a standing
instruction that this turn must be handed to a human. These are the only place turn-specific
instruction text exists.

## ③ Agent loop — the only phase with judgment in it

The model picks tools and writes prose. Around every call it makes:

- **`wrap_tool_execute`** re-checks whether the tool needs a customer and refuses before the
  function body runs. Deliberately redundant with `prepare_tools`: that one is ergonomics, this
  one is the control, and it still holds for replayed history or a future capability re-adding a
  tool.
- **Each capability enforces its own policy** in its service, and the tool returns a *typed
  outcome*. A refusal is an `ActionResult(code=…, detail=…)` — a correct business answer, not an
  exception, and `success` is derived from the code rather than stored beside it. A refusal also
  carries the evidence it refers to: an address change refused because the parcel has shipped
  names *that order's* courier and resi, because a gap the model can see is a gap it will fill
  from an earlier turn. A recoverable mistake (stale order id) raises `ModelRetry` and goes back
  for one more try. An infrastructure failure is caught and returned as a refusal that offers
  escalation.
- **`after_tool_execute`** promotes the session when the configured lookup tool returns a
  `Customer`. This is the only place in the run where privilege increases. The lookup tool used
  to set `deps.customer` itself; that put a security decision inside a capability whose job is a
  database read, so it moved to the gate — the same module that decides what the privilege
  unlocks. From the next model step onward the full tool surface is present.

The load-bearing example: `create_return` takes **no `refund_amount` parameter**. `ReturnService`
derives the value from `order_items` and applies the ceiling to a number the model never touched.
Had the amount been an argument, the guard would be checking a figure chosen by the guarded party.

## ④ Verify and commit — read the evidence

The model produces one thing: text. There is no output tool, so there is nothing for it to claim
about itself.

`ctx.messages` is the evidence. The output validator in `guardrails/escalation.py` enforces the
one direction the transcript cannot settle by itself: a turn intake marked as requiring a human,
with no `escalate_ticket` call in it, raises `ModelRetry`. That returns the model to phase ③ with
the correction, so the usual outcome is a compliant second attempt the customer never notices.

The validator used to have a second branch — "claimed an escalation that never happened" — which
mattered more than it looked, because reporting an escalation that did not occur closes the loop
with a human who believes a ticket is waiting. It is gone, and that is the point: `escalated` and
`ticket_id` are now *read* from the transcript by `shared/transcript.py::outcome`, so the failure
it guarded against cannot be expressed. `runner.run_turn` assembles the `AgentReply` from the
model's text plus those facts.

Then: persist the conversation through `MessageStore` — the framework's own message format, into
`conversation_messages`, one row per message, system prompts stripped — write the turn into `ticket_messages`, and
record `escalated`, token counts, and request count on the span.

## Failure path

Any exception escaping phase ③ — provider quota exhausted, retries spent, an unanticipated
tool error — produces the fallback `AgentReply`: an honest sentence plus the offer of a human.
A customer-facing chat endpoint must never answer with a stack trace or a bare 503. The
failure is not swallowed: it is logged with its traceback and the span is marked `failed`.

---

## Where each requirement is actually enforced

The point of the table: not one of these lives in the prompt.

| Requirement | Enforced by | Phase |
|---|---|---|
| No cross-customer data | `WHERE customer_id = ?` in every scoped query in `shared/database.py` | ③ (data layer) |
| Verify before sensitive data | `guardrails/identity_gate.py` — `prepare_tools` + `wrap_tool_execute` | ② and ③ |
| Only the gate grants verification | `guardrails/identity_gate.py::after_tool_execute` | ③ |
| Refund > Rp 1.000.000 escalates | `ReturnService` derives the amount; `returns/policies.py::requires_escalation` | ③ |
| No address change once shipped | `orders/policies.py::can_change_address` | ③ |
| A refusal names its own order's courier | `OrderService.change_address` appends that order's shipment | ③ |
| Escalate on fraud/legal/safety/human | `tickets/policies.py::detect_signals` → `guardrails/escalation.py` | ① and ④ |
| Escalate on inconsistent data | `tickets/policies.py::claims_not_received` + order status | ① |
| Never claim a false escalation | not enforced — impossible: `escalated` is read from the transcript by `shared/transcript.py::outcome`, never stated by the model | ④ |
| Graceful tool/DB failure | typed `ActionResult` + `runner.FALLBACK` reply | ③ and ④ |

## What the prompt is left holding

Only what code cannot express: tone, language, and the judgment keyword detection misses — say a
refusal as it is, never promise compensation no tool returned, hand off when the case needs a
human. Per-tool specifics live in the tool docstrings, which are the descriptions the model
reads. There is no output contract to state: the model writes the reply and nothing else. Each
fact has exactly one home.

## What this shape buys

- **Guarantees are testable without a model.** `tests/test_guardrails.py` asserts the *rules*,
  in milliseconds, with no API key — rather than sampling an LLM and hoping.
- **The prompt can change without weakening a guarantee.** Rewriting the instructions to be
  high-level, as they now are, moved no enforcement.
- **Adding a scenario is composition.** A new tool needs one entry in its own capability's
  `ACCESS` map, one in its `ACTIVITY` map (what the customer is told while it runs), and, if it
  carries a rule, one function in that capability's `policies.py`. A new domain is a folder. The
  gate, the validator, and the fallback already cover it — and an unclassified tool fails closed.

## Deliberate limits

- **Identification, not authentication.** The schema has no OTP or password, so a matching
  email proves knowledge of an email. Documented in `DESIGN.md` §4 rather than dressed up.
- **Conversation history is a row per message in Postgres**, with the model's view trimmed to
  a trailing window by a `ProcessHistory` capability. It
  survives a redeploy and a second worker, which an in-process dict does not; what it does not
  do is summarise, so a very long conversation loses its oldest turns outright.
- **Grounding is enforced by construction, not verified per claim.** Tools are the only route
  to data, but nothing checks each sentence against the tool results. Where that has already
  bitten — a refusal that mentioned a courier without naming one — the fix was to put the fact in
  the result, one gap at a time. The general answer is an offline eval suite with an LLM judge,
  not a second model call in the request path.
