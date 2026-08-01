# TokoKita — Customer Service AI Agent

A customer service agent for an Indonesian marketplace, served as a REST API.
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

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync                       # install
cp .env.example .env          # then put your Groq key in it
uv run python -m tokokita.data.seed   # create ./tokokita.db with the dummy data
```

Get a Groq key at [console.groq.com/keys](https://console.groq.com/keys). Without one the
service still boots on Pydantic AI's keyless `test` model — enough for `/health` and the test
suite, not enough for a real conversation.

## Environment variables

All are optional except the Groq key, and all are prefixed `TOKOKITA_`.

| Variable | Default | What it does |
|---|---|---|
| `TOKOKITA_GROQ_API_KEY` | — | Groq API key. Unset ⇒ keyless `test` model. |
| `TOKOKITA_MODEL_NAME` | `openai/gpt-oss-20b` | Any Groq model id. |
| `TOKOKITA_DATABASE_PATH` | `./tokokita.db` | SQLite file. |
| `TOKOKITA_PHOENIX_ENDPOINT` | `http://localhost:6006` | Empty string disables the Phoenix exporter. |
| `TOKOKITA_LOGFIRE_TOKEN` | — | Set ⇒ traces also go to Logfire cloud. |
| `TOKOKITA_LOGFIRE_ENVIRONMENT` | `development` | Logfire environment tag. |
| `TOKOKITA_TOOL_RETRIES` | `2` | Retries per tool call before the turn aborts. |
| `TOKOKITA_REASONING_FORMAT` | `hidden` | Keeps a thinking model's `<think>` out of the text channel. Leave **empty** for a non-reasoning model, which would reject it. |
| `TOKOKITA_HTTP_RETRIES` | `3` | Passed to the Groq SDK, which honours `Retry-After`. |

## Running

```bash
# 1. Phoenix (optional but recommended -- this is where the traces are readable)
docker run -d --rm -p 6006:6006 -p 4317:4317 --name tokokita-phoenix \
  arizephoenix/phoenix:latest

# 2. The API
uv run uvicorn tokokita.api.app:create_app --factory --reload
```

`create_app` is a factory on purpose: importing the module must not configure an exporter or
open a database, which is what `--factory` respects.

Interactive API docs: <http://localhost:8000/docs>

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
| `input_tokens`, `output_tokens`, `requests` | cost of the turn |

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
  "action_taken": null,
  "escalated": false,
  "ticket_id": null
}
```

`customer_hint` accepts an email, a phone number, or an order id — but **only email or phone
verify**. An order number is printed on the parcel, so treating it as a credential would make a
shipping label a password. The turn history is persisted per `session_id` to the `conversations`
table and replayed on the next request; turns are additionally written to `ticket_messages` when
the customer has an open ticket.

### `GET /chat/{session_id}`

The conversation so far, reduced to readable turns: `role`, `text`, and the tools that ran.

### `GET /`

A minimal chat UI — the same endpoint, without curl.

### `GET /health`

Liveness. `{"status": "ok"}`.

### `GET /orders/{order_id}?customer_hint=...`

Debug read, behind the same verification and the same customer scoping as the agent. `401`
unverified, `404` for an order that is not yours.

## Things to try

| Ask | What should happen |
|---|---|
| "Pesanan 1 saya sudah sampai mana?" (with hint) | Calls `get_order_detail` + `track_shipment`, quotes the real JNE resi. |
| Same question with **no** `customer_hint` | Refuses and asks for an email or phone — the data tools are not even offered to the model. |
| "Tolong ubah alamat pesanan 1 ke Jl. Baru No. 5" | Refused: order 1 is already `shipped`. |
| "Saya mau bicara dengan manusia" | Opens a ticket and escalates it before answering. |
| "Saya merasa ditipu, uang saya hilang" | Escalates — fraud is not a chatbot's call. |
| Ask Andi's session about order 3 | Not found. Order 3 is Bunga's, and the query cannot reach it. |

## Tests

```bash
uv run pytest          # 43 tests, no API key needed, ~0.3s
uv run ruff check .
```

`tests/conftest.py` sets `models.ALLOW_MODEL_REQUESTS = False`, so an accidental real Groq call
fails the suite instead of billing you. Model behaviour is scripted with `TestModel` /
`FunctionModel`, and the business rules are tested directly as pure functions.

- `test_services.py` — customer scoping, refund derivation, policy refusals, validation. No model.
- `test_guardrails.py` — the address-change decision table, the refund ceiling, escalation
  signal detection, and the identity gate's effect on the offered tool surface.
- `test_api.py` — the HTTP surface end to end with a scripted model.

## Layout

Follows the Pydantic AI structure in `docs/context/development-wisdom.md`: a model becomes a
service, a service is wrapped by a thin tool, tools are packaged into a capability, capabilities
are composed by an agent, and a runner drives the turn.

```
src/tokokita/
  agentic_system/
    agents/support/       agent.py (composition root) deps.py output.py
                          instructions.py runner.py (the turn lifecycle)
    capabilities/         one folder per domain ability, each self-contained:
      identity/           capability.py tools.py services.py schemas.py
      catalog/            capability.py tools.py services.py schemas.py
      orders/             + policies.py  (address lock)
      returns/            + policies.py  (refund ceiling)
      tickets/            + policies.py  (escalation signals)
    guardrails/           rules that apply across every capability:
                          access_levels.py identity_gate.py escalation.py
    shared/               settings.py telemetry.py database.py model_factory.py
                          results.py message_store.py transcript.py
  api/app.py              FastAPI: create_app factory, /chat, /health, /orders/{id}
  api/static/index.html   minimal chat UI, served at /
  data/                   schema.sql seed.sql seed.py
```

**The scoping rule:** a capability owns a *domain ability* (a noun — orders, returns). A
guardrail owns a *cross-cutting rule* (a verb applied to everything). If a thing has to know
about every capability, it is not a capability. That is why the identity gate and the escalation
validator live in `guardrails/`, and why each capability declares its own tools' access level
instead of one global table knowing about all of them.

Tools are thin adapters. SQL and business logic live in `services.py`; rules live in
`policies.py` as pure functions, which is what makes `tests/test_services.py` run without a
model, a mock, or an API key.
