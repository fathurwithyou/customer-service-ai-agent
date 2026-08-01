# TokoKita — Customer Service AI Agent

A customer service agent for an Indonesian marketplace, served as a REST API with a small
React chat UI on top of it.
FastAPI + Pydantic AI (Groq) + Pydantic v2, traced into Logfire and Arize Phoenix at once.

The agent answers in Indonesian, grounds every factual claim in a tool call, and refuses to
open a customer's data before that customer has been identified.

- **[`docs/DESIGN.md`](docs/DESIGN.md)** — the abstractions, the layer boundaries, and what was
  rejected and why.
- **[`docs/WORKFLOW.md`](docs/WORKFLOW.md)** — one turn end to end, and where each requirement is
  actually enforced.
- **[`docs/STACK_NOTES.md`](docs/STACK_NOTES.md)** — the Step 0 research: verified versions and
  API signatures, and the tool-vs-capability-vs-MCP-vs-sub-agent decision framework.

---

## Setup

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/). The web UI additionally needs Node
and [pnpm](https://pnpm.io/).

```bash
uv sync                       # install
cp .env.example .env          # then put your Groq key in it
uv run python -m tokokita.data.seed   # create ./tokokita.db with the dummy data

pnpm --dir frontend install   # the UI
pnpm --dir frontend build     # -> src/tokokita/api/static/
```

`src/tokokita/api/static/` is a build artefact and is **gitignored**, so a fresh clone has no
UI at all until you run `pnpm build`: `GET /` 404s and every other route works exactly as
before. The mount is conditional on the directory existing, which is what keeps the API usable
without Node installed.

Get a Groq key at [console.groq.com/keys](https://console.groq.com/keys). Without one the
service still boots on Pydantic AI's keyless `test` model — enough for `/health` and the test
suite, not enough for a real conversation.

## Environment variables

All are optional except the Groq key, and all are prefixed `TOKOKITA_`.

| Variable | Default | What it does |
|---|---|---|
| `TOKOKITA_GROQ_API_KEY` | — | Groq API key. Unset ⇒ keyless `test` model. |
| `TOKOKITA_MODEL_NAME` | `openai/gpt-oss-20b` | Any Groq model id. |
| `TOKOKITA_REASONING_FORMAT` | `parsed` | `parsed` \| `hidden` \| `raw`. `parsed` gives the reasoning its own field, which becomes a `ThinkingPart`; `hidden` only suppresses it, and the model still writes analysis into the text channel where a tool call then fails to parse. Leave **empty** for a non-reasoning model, which would reject the parameter. |
| `TOKOKITA_DATABASE_PATH` | `./tokokita.db` | SQLite file. |
| `TOKOKITA_PHOENIX_ENDPOINT` | `http://localhost:6006` | Empty string disables the Phoenix exporter. |
| `TOKOKITA_LOGFIRE_TOKEN` | — | Set ⇒ traces also go to Logfire cloud. |
| `TOKOKITA_LOGFIRE_ENVIRONMENT` | `development` | Logfire environment tag. |
| `TOKOKITA_TOOL_RETRIES` | `2` | Retries per tool call before the turn aborts. |
| `TOKOKITA_HTTP_RETRIES` | `3` | Passed to the Groq SDK, which honours `Retry-After`. |
| `TOKOKITA_REQUEST_TIMEOUT` | `60.0` | Seconds, per Groq request. |

## Running

```bash
# 1. Phoenix (optional but recommended -- this is where the traces are readable)
docker run -d --rm -p 6006:6006 -p 4317:4317 --name tokokita-phoenix \
  arizephoenix/phoenix:latest

# 2. The API, with the built UI served from it
uv run uvicorn tokokita.api.app:create_app --factory --reload
```

`create_app` is a factory on purpose: importing the module must not configure an exporter or
open a database, which is what `--factory` respects.

Chat UI: <http://localhost:8000> — **only if you ran `pnpm --dir frontend build`**.
Interactive API docs: <http://localhost:8000/docs>.

For frontend work, run Vite instead and leave uvicorn up: `pnpm --dir frontend dev` serves on
:5173 with `/chat` and `/health` proxied to :8000, so the UI hot-reloads against the real agent.

## Dashboards

**Arize Phoenix** — <http://localhost:6006>. Traces land under the project
**`tokokita-cs-agent`**. Open a trace to see the agent span, each model call, and each tool call
with its arguments and result.

**Pydantic Logfire** — <https://logfire.pydantic.dev>, in the project your
`TOKOKITA_LOGFIRE_TOKEN` belongs to. Without a token nothing is sent and nothing breaks.

Both read the *same* spans from one tracer provider: `OpenInferenceSpanProcessor` enriches each
span in place for Phoenix without removing the `gen_ai.*` attributes Logfire renders. See
`shared/telemetry.py` and `docs/STACK_NOTES.md` §9.

Each turn arrives as a `CHAIN` span named **chat turn** — the readable root of the trace — with
the conversation on it rather than an opaque HTTP row:

| Attribute | Carries |
|---|---|
| `input.value` / `output.value` | the customer's message and the agent's reply |
| `session.id` | groups a multi-turn conversation |
| `user.id` | the customer **id** — never the email or phone used to look them up |
| `tag.tags` | `verified` / `anonymous`, or the escalation signals found |
| `metadata` | verified, escalation signals, whether escalation was required, model |
| `escalated`, `ticket_id` | the outcome |
| `llm.token_count.{prompt,completion,total}`, `model_requests` | cost of the turn |

Beneath it: `AGENT` for the run, `LLM` per model call, and `TOOL` per tool call with its
arguments as `input.value`.

## API

### `POST /chat`

```bash
curl -s localhost:8000/chat -H 'content-type: application/json' -d '{
  "session_id": "demo-1",
  "customer_hint": "andi@example.com",
  "message": "Pesanan 1 saya sudah sampai mana ya?"
}' | jq
```

```json
{
  "message": "Pesanan 1 Anda sedang dalam perjalanan dengan JNE, nomor resi JNE0012345678...",
  "customer_name": "Andi Wijaya",
  "escalated": false,
  "ticket_id": null
}
```

The agent's `output_type` is plain `str`, so there is no output tool and `message` is the whole
of what the model produced. `AgentReply` is assembled by the runner: `customer_name` is who the
gate ended the turn holding, and `escalated` / `ticket_id` are read back out of the transcript
by looking for `escalate_ticket` and `create_ticket`. A model cannot report an escalation that
never ran, because it is never asked to.

`customer_hint` accepts an email, a phone number, or an order id — but **only email or phone
verify**. An order number is printed on the parcel, so treating it as a credential would make a
shipping label a password. The turn history is persisted per `session_id` to the `conversations`
table (the framework's own wire format, last 40 messages, system prompts stripped) and replayed
on the next request; turns are additionally written to `ticket_messages` when the customer has
an open ticket.

### `POST /chat/stream`

The same body, as server-sent events:

| Event | Data | When |
|---|---|---|
| `start` | `{customer_name}` | immediately, before the model runs |
| `tool` | `{label}` | a tool call started |
| `delta` | `{text}` | a chunk of the answer, coalesced to whole words |
| `done` | the full `AgentReply` | the run finished |

`label` is the phrase the customer reads while they wait — "Melacak posisi paket", "Menyiapkan
pengajuan pengembalian" — declared per capability as `ACTIVITY` next to the tools it names, in
the same language the agent answers in. `escalated` and `ticket_id` cannot be streamed (they are
read from the finished transcript), which is why `done` exists at all.

### `GET /chat/{session_id}`

The conversation so far, reduced to readable turns: `role` (`customer` / `agent`), `text`, and
the tools that ran. A tool call that drew a retry is omitted, because it never returned.

### `GET /`

The built SPA, mounted last so every API route above wins. Absent until `pnpm build` has run.

### `GET /health`

Liveness. `{"status": "ok"}`.

### `GET /orders/{order_id}?customer_hint=...`

Debug read, behind the same verification and the same customer scoping as the agent. `401`
unverified, `404` for an order that is not yours.

## Things to try

Andi is `andi@example.com` (orders 1, 2, 4, 5, 6, 7), Bunga is `bunga@example.com` (orders 3
and 8), Citra is `citra@example.com` and has none.

| Ask | What should happen |
|---|---|
| "Pesanan 1 saya sudah sampai mana?" (with hint) | Calls `get_order_detail` + `track_shipment`, quotes the real JNE resi `JNE0012345678`. |
| Same question with **no** `customer_hint` | Asks for an email or phone — the scoped tools are not even in the list the model is shown. |
| "Berapa harga Sepatu Sneakers?" with no hint | Answered. The catalog is `OPEN`, so identity is demanded only where it buys something. |
| "Tolong ubah alamat pesanan 4 ke Jl. Baru No. 5" | Succeeds. Order 4 is still `processing`. |
| The same for pesanan 1 | Refused: already `shipped`, and the address the courier holds is no longer ours to edit. |
| The same for pesanan 7 | Refused too, but with its own code — order 7 was cancelled. |
| "Saya mau retur jam tangan di pesanan 5" | Refused **and** escalated: Rp 2.500.000 is over the Rp 1.000.000 ceiling. The refund is derived from `order_items`, so the model cannot name a smaller figure to get under it. |
| "Kenapa pesanan 6 belum diproses?" | Payment is still `pending` — the order is unpaid, not stuck. |
| As Bunga: "Pesanan 8 katanya terkirim tapi belum sampai" | Escalates on `data_inconsistency`: our row says delivered, hers says otherwise, and only a human can find out which is wrong. |
| "Saya mau bicara dengan manusia" | Opens a ticket and escalates it before answering. |
| "Saya merasa ditipu, uang saya hilang" | Escalates — fraud is not a chatbot's call. |
| Ask Andi's session about pesanan 3 | Not found. Order 3 is Bunga's, and the query cannot reach it. |
| As Citra: "Mana pesanan saya?" | An empty list, answered as an empty list. |

## Tests

```bash
uv run pytest          # 53 tests, no API key needed, ~0.3s
uv run ruff check .
```

`tests/conftest.py` sets `models.ALLOW_MODEL_REQUESTS = False`, so an accidental real Groq call
fails the suite instead of billing you. Model behaviour is scripted with `FunctionModel`, and
the business rules are tested directly as pure functions.

- `test_services.py` — customer scoping, refund derivation, policy refusals, validation, and the
  seed cases the demo depends on (order 4 editable, order 5 over the ceiling, order 6 unpaid,
  order 7 cancelled, Citra empty). No model.
- `test_guardrails.py` — the address-change decision table, the refund ceiling, escalation
  signal detection, and the identity gate: which tools are offered, that a scoped tool is
  refused even if reached anyway, that an unclassified tool fails closed, and that only
  `get_customer` promotes a session.
- `test_api.py` — the HTTP surface end to end with a scripted model, including that the outcome
  fields are read from the transcript rather than claimed by the model.

## Layout

Follows the Pydantic AI structure in `docs/context/development-wisdom.md`: a model becomes a
service, a service is wrapped by a thin tool, tools are packaged into a capability, capabilities
are composed by an agent, and a runner drives the turn.

```
src/tokokita/
  agentic_system/
    agents/support/       agent.py (composition root) deps.py output.py
                          instructions.py runner.py (the turn lifecycle)
                          streaming.py (the same turn, as SSE)
    capabilities/         one folder per domain ability, each self-contained:
      customers/          capability.py tools.py services.py schemas.py
      catalog/            capability.py tools.py services.py schemas.py
      orders/             + policies.py  (address lock)
      returns/            + policies.py  (refund ceiling)
      tickets/            + policies.py  (escalation signals)
    guardrails/           rules that apply across every capability:
                          access_levels.py identity_gate.py escalation.py
    shared/               settings.py telemetry.py database.py model_factory.py
                          results.py message_store.py transcript.py
  api/app.py              FastAPI: create_app factory, /chat, /chat/stream,
                          /chat/{session_id}, /health, /orders/{id}, SPA at /
  api/static/             the built UI -- gitignored, produced by `pnpm build`
  data/                   schema.sql seed.sql seed.py
frontend/                 React 19 + Vite, TypeScript:
  src/conversation/       Conversation.tsx (owns turn state, the only thing that knows the
                          transport) stream.ts (SSE parsing) Turns/Composer/Header
  src/Markdown.tsx        react-markdown + remark-gfm + rehype-sanitize
tests/                    conftest.py test_services.py test_guardrails.py test_api.py
```

**The scoping rule:** a capability owns a *domain ability* (a noun — orders, returns). A
guardrail owns a *cross-cutting rule* (a verb applied to everything). If a thing has to know
about every capability, it is not a capability. That is why the identity gate and the escalation
validator live in `guardrails/`, and why each capability declares its own tools' access level
instead of one global table knowing about all of them.

`AccessLevel` has exactly two members — `OPEN` and `VERIFIED_CUSTOMER` — because the gate only
ever asks one question: does this tool need a verified customer? An undeclared tool is treated
as needing one, so forgetting to classify a new tool makes it unavailable rather than public.

Tools are thin adapters. SQL and business logic live in `services.py`; rules live in
`policies.py` as pure functions, which is what makes `tests/test_services.py` run without a
model, a mock, or an API key.
