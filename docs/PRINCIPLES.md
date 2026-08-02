# Principles

**A guideline for writing code that stays clean, and for not drifting away from it.**

Clean code is not code that looks tidy. It is code that *applies principles* — clear
abstraction, SOLID, DRY, low coupling, high cohesion — so that the next change is cheap and the
wrong change is hard. Tidiness is a side effect of that; it is not the goal, and chasing it
directly produces code that reads well and breaks often.

This document is organised around those principles. Each one is stated generally, illustrated
with a **framework that gets it right** — Pydantic above all, plus SQLAlchemy, FastAPI and
pydantic-ai — and then grounded in code from this repository, including the places where we got
it wrong first. Frameworks are the best teachers available: they are abstractions that survived
thousands of users pulling on them, which is a level of evidence no internal codebase reaches.

A note on audience. This is written for whoever works on this next, human or model. A model
drifts in a particular direction: it optimises for *appearing* thorough, and appearing thorough
is cheap to fake with more prose, more layers and more machinery. A large part of what follows is
a defence against that specific failure.

---

## Contents

**Part I — Abstraction**
1. [What an abstraction actually is](#1-what-an-abstraction-actually-is)
2. [Why Pydantic's abstraction is good, in detail](#2-why-pydantics-abstraction-is-good-in-detail)
3. [Leaky, premature, and one-implementation abstractions](#3-leaky-premature-and-one-implementation-abstractions)
4. [Parse, don't validate](#4-parse-dont-validate)

**Part II — SOLID**
5. [S — One reason to change](#5-s--one-reason-to-change)
6. [O — Open for extension, closed for modification](#6-o--open-for-extension-closed-for-modification)
7. [L — Substitutability is what makes tests possible](#7-l--substitutability-is-what-makes-tests-possible)
8. [I — Narrow interfaces, and interfaces as enforcement](#8-i--narrow-interfaces-and-interfaces-as-enforcement)
9. [D — Depend on abstractions, inject the concrete](#9-d--depend-on-abstractions-inject-the-concrete)

**Part III — DRY and its counterfeits**
10. [DRY is about knowledge, not text](#10-dry-is-about-knowledge-not-text)
11. [The wrong DRY: coupling things that merely rhyme](#11-the-wrong-dry-coupling-things-that-merely-rhyme)

**Part IV — Coupling and cohesion**
12. [Coupling is the cost of every change](#12-coupling-is-the-cost-of-every-change)
13. [Tell, don't ask](#13-tell-dont-ask)
14. [Composition over inheritance](#14-composition-over-inheritance)

**Part V — Design in the small**
15. [Make illegal states unrepresentable](#15-make-illegal-states-unrepresentable)
16. [Errors have three shapes](#16-errors-have-three-shapes)
17. [Derive, don't restate](#17-derive-dont-restate)
18. [Own your resources explicitly](#18-own-your-resources-explicitly)

**Part VI — Restraint**
19. [YAGNI, and the cost of a knob](#19-yagni-and-the-cost-of-a-knob)
20. [Reach for the framework's seam before writing machinery](#20-reach-for-the-frameworks-seam-before-writing-machinery)
21. [Helpers, and the ones that want to be methods](#21-helpers-and-the-ones-that-want-to-be-methods)
22. [Delete what nothing calls — after checking who calls](#22-delete-what-nothing-calls--after-checking-who-calls)

**Part VII — Communication**
23. [Naming: one name, one meaning](#23-naming-one-name-one-meaning)
24. [Comments carry four things and nothing else](#24-comments-carry-four-things-and-nothing-else)
25. [Record reversals and costs, not just decisions](#25-record-reversals-and-costs-not-just-decisions)

**Part VIII — Evidence**
26. [Verify against the installed version](#26-verify-against-the-installed-version)
27. [Measure before you order things](#27-measure-before-you-order-things)
28. [Tests are design feedback, not a chore](#28-tests-are-design-feedback-not-a-chore)

**Closing**
29. [The drift checklist](#29-the-drift-checklist)

---

# Part I — Abstraction

## 1. What an abstraction actually is

An abstraction is **a boundary that hides a decision likely to change.** That is Parnas's
definition from 1972 and nothing better has replaced it. Note what it is *not*: it is not a layer,
not a base class, not a file that ends in `_service.py`. Those are structures. An abstraction is a
promise about what you no longer need to know.

Three properties tell you whether you have one:

**It hides a decision, and the decision is one that changes.** `list` hides how elements are
stored. `dict` hides hashing. A `Session` hides connection handling and transaction bookkeeping.
Each hides something that has changed, repeatedly, without users caring.

**Its interface is smaller than its implementation.** If the interface has as many concepts as
the thing behind it, you have a rename, not an abstraction.

**You can use it correctly without reading its source.** This is the practical test, and the one
most internal abstractions fail. If callers must know that `save()` must be called after
`prepare()`, or that passing `None` behaves differently from omitting the argument, the boundary
leaks and the "abstraction" is a trap with a friendly name.

A useful sharpening: **an abstraction should let you forget, not merely let you type less.**
Shortening is what functions do. Forgetting is what abstractions do.

---

## 2. Why Pydantic's abstraction is good, in detail

Pydantic is worth studying closely because it makes an unusually large set of correct choices,
and each one is copyable.

### It is declarative: you say *what*, never *how*

```python
class TransferIntent(BaseModel):
    source_account_id: str
    destination_account_number: str = Field(min_length=6, max_length=32)
    amount: int = Field(gt=0)
    note: str | None = Field(default=None, max_length=140)
```

There is no validation code here. There is a *description of what valid means*, and the
mechanism is hidden completely. The hidden decision — how to coerce, in what order, with what
error format, in Python or in Rust — has in fact changed dramatically between v1 and v2, and
this declaration did not.

That is the whole game: **the thing users write is stable precisely because it contains no
mechanism.**

### The declaration is the single source of many artefacts

From the same class you get validation, serialisation, a JSON Schema, editor completion, and
static types:

```python
intent = TransferIntent.model_validate(payload)      # parsing
intent.model_dump(by_alias=True)                     # serialisation
TransferIntent.model_json_schema()                   # contract for a tool or an API
```

This is DRY (§10) applied at the level of *knowledge*: the shape of a transfer is stated once and
every representation is derived. Compare the alternative — a dataclass, a marshmallow schema, a
JSON Schema file and a TypeScript interface, four declarations of one fact, guaranteed to drift.

### Composition instead of a class hierarchy

Constraints compose through `Annotated`, so behaviour is assembled rather than inherited:

```python
Amount = Annotated[float, BeforeValidator(lambda v: v or 0.0), Field(ge=0)]

class OrderSummary(FromRow):
    total_amount: Amount = 0.0

class OrderDetail(FromRow):
    total_amount: Amount = 0.0
```

`Amount` is a reusable *piece of meaning*, not a base class. Two models share it without being
related. Contrast with the inheritance version, where sharing a constraint forces a common
ancestor and the ancestor accumulates everything anyone ever shared (§14).

### Policy is separated from shape

```python
class StrictDomainModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", validate_assignment=True)
```

`model_config` is *policy* — how strict, what to do with unknown fields. Fields are *shape*.
Keeping them in different mechanisms means you can change the policy for a whole family without
touching a single field, which is exactly the axis along which requirements move.

This project uses one two-line application of it:

```python
class FromRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
```

Every tool-facing model inherits one policy: *these are built from database rows*. No field is
repeated to get it.

### Errors are data, not strings

```python
try:
    return TransferIntent.model_validate(raw)
except ValidationError as exc:
    return {"type": "validation_error", "errors": exc.errors()}
```

`exc.errors()` returns structured entries with a location, a type and a message. That is what
makes it possible to build an API response, a form highlight, or a model retry prompt from the
same failure. **An error that is only a string forces every consumer to parse prose.** This is
the same principle as §17 (derive, don't restate) applied to failure.

### Escape hatches exist, and they are typed

A framework without an escape hatch forces users to abandon it at the first unusual case.
Pydantic's is `__get_pydantic_core_schema__`, and SQLAlchemy's equivalent is `TypeDecorator`.
This repository uses the latter to make a database column speak Pydantic:

```python
class PydanticJson(TypeDecorator[Any]):
    impl = JSONB
    cache_ok = True

    def __init__(self, model: Any) -> None:
        super().__init__()
        self.model = model
        self._adapter: TypeAdapter[Any] = TypeAdapter(model)

    def process_bind_param(self, value, dialect):
        return None if value is None else self._adapter.dump_python(value, mode="json")

    def process_result_value(self, value, dialect):
        return None if value is None else self._adapter.validate_python(value)
```

Used as `payload: Mapped[ModelMessage] = mapped_column(PydanticJson(ModelMessage))`, the
conversion disappears from every layer above:

```python
# before: the store knew about JSON
rows = ...; return [MESSAGE.validate_json(row.payload) for row in rows]
self._session.add(Row(payload=MESSAGE.dump_json(message).decode(), ...))

# after: the store knows about messages
return [row.payload for row in rows]
self._session.add(Row(payload=message, ...))
```

**That is what a good abstraction does to calling code: it removes a concept, not a few
characters.** The word "JSON" no longer appears above the column.

### The lesson to copy

| Pydantic does | So you should |
|---|---|
| declares what, never how | keep mechanism out of the thing users write |
| derives every artefact from one declaration | one source of a fact, many representations |
| composes with `Annotated` | share meaning, not ancestors |
| separates `model_config` from fields | separate policy from shape |
| returns errors as data | never make a caller parse prose |
| offers a typed escape hatch | let users extend without forking |

---

## 3. Leaky, premature, and one-implementation abstractions

Three failure modes, each with a tell.

### Leaky: callers must know what is behind it

The tell is documentation that describes *sequence* or *internal state*: "call `connect()`
first", "do not use after `close()`", "`refresh()` if you changed it elsewhere". Every such
sentence is a decision that failed to stay hidden.

`AsyncSession` leaks deliberately and honestly — it tells you it is not concurrency-safe, and
that is a real property of the thing, not a wart. The response is to state it where it binds:

```python
# No overlap: every tool in a turn shares one AsyncSession, which is not concurrency-safe.
values = GroqModelSettings(parallel_tool_calls=False)
```

An honest leak documented at the boundary is fine. A leak that the caller has to *discover* is
not.

### Premature: an abstraction over one case

An interface designed from a single example encodes that example's accidents. The rule of three
is crude but effective: **wait until three real cases exist before extracting the shape they
share**, because two points fit any line.

This repository has a live example of the cost of *not* waiting. A hand-rolled `Database` class
wrapped a driver and a `schema.sql` declared the tables a second time. It was an abstraction
invented for one application, and its real cost was not the code — it was that nobody else in
the world knew that interface. Replacing it with SQLAlchemy meant `Base.metadata` *is* the
schema and `session_scope` *is* the transaction, both concepts a reader already has.

> **A private abstraction over a public one costs every future reader the difference.**

### One implementation, forever

A base class with a single subclass, an interface with one implementer, a factory that returns
one type. These are usually speculative generality: the flexibility was never used, and the
indirection is paid on every read.

The honest version is to write the concrete thing and extract later — extraction is cheap,
because by then you know the shape. Deleting a wrong abstraction is expensive, because callers
have grown into it.

---

## 4. Parse, don't validate

A principle worth naming explicitly, because Pydantic is its clearest mainstream implementation.

**Validation** checks data and returns a boolean or throws; the data keeps its original loose
type, so every downstream function must check again or trust blindly. **Parsing** consumes loose
data and returns a *narrower type* that cannot be invalid — so downstream functions cannot
express the failure case.

```python
# validate: the str survives, and every caller must wonder
def is_valid_email(s: str) -> bool: ...

def notify(user_email: str): ...   # is this checked? nobody can tell

# parse: the type carries the guarantee
class Customer(FromRow):
    customer_id: int
    full_name: str

def notify(customer: Customer): ...   # cannot be handed junk
```

Consequences that follow directly:

**Parse at the boundary, once.** Untrusted input — HTTP body, LLM output, queue message, file —
crosses into typed objects at the edge, and internal layers trust the type. Re-validating trusted
objects at every layer is cost with no information gained.

**A narrowed type is a proof carried in the signature.** `OrderStatus` is a `StrEnum`, so a
function taking one cannot receive `"shippd"`. That misspelling becomes impossible at the
parse boundary rather than a mystery three layers in.

**A missing field is enforcement, not an omission.** Because `Customer` declares no `email`,
`model_validate(row)` drops it. No tool can return it, no trace can carry it, no redaction step
has to be remembered. The guarantee holds for tools that do not exist yet — which is precisely
the difference between a type-level guarantee and a review-level one.

---

# Part II — SOLID

SOLID is often taught as five rules about classes. It is more useful as five questions about
**where change lands**.

## 5. S — One reason to change

The Single Responsibility Principle is not "a class does one thing". Almost everything does one
thing at some level of description. Uncle Bob's sharper form is what to use:

> **A module should have one reason to change — one *audience* whose decisions it serves.**

The test is to name the roles who could demand a change. If two different roles can, the module
holds two responsibilities.

### A real violation

History trimming lived inside the persistence query:

```python
# message_store.py -- the store decided what the model may see
recent_runs = (
    select(func.min(ConversationMessage.seq).label("start"))
    .group_by(ConversationMessage.run_id)
    .limit(MAX_RUNS)          # <- a prompting decision, inside persistence
    .subquery()
)
```

Two audiences: whoever owns *durability and audit* (keep everything, forever, retrievable), and
whoever owns *prompt cost and quality* (show the model twelve runs). Both would ask this file to
change, for unrelated reasons.

Split along the audience line:

```python
# message_store.py -- keeps everything. The audit record.
async def load(self, session_id: str) -> list[ModelMessage]:
    rows = await self._session.scalars(select(...).order_by(...seq))
    return [row.payload for row in rows]

# history.py -- decides what the model sees. A capability.
WINDOW = ProcessHistory(recent_runs, description="Keep the last few complete runs.")
```

The load query lost a subquery, and each file now answers to one person.

### The same test at module scale

`runner.py` held eight top-level symbols and `streaming.py` imported five of them. Two audiences
again: *how a turn is conducted* (shared) and *how a turn is delivered* (one response, or
events). Splitting gave `intake.py` / `runner.py` / `streaming.py`, with neither entry point
importing from the other, and `runner.py` fell from 183 lines to 41.

**Drift symptom.** You describe a file with "and": "it loads history *and* trims it", "it builds
the reply *and* records telemetry *and* persists".

---

## 6. O — Open for extension, closed for modification

You should be able to add behaviour without editing existing code. The mechanism matters less
than the property: **new cases must not require touching the switch statement that everyone
depends on.**

Frameworks live or die on this. Three examples of the shape done well:

**SQLAlchemy's `TypeDecorator`.** A new column type does not require a patch to SQLAlchemy; you
subclass at a defined seam. `PydanticJson` above is thirty lines and needs no knowledge of the
dialects, the compiler, or the caching layer.

**Pydantic's `__get_pydantic_core_schema__`.** Same idea for types.

**pydantic-ai's capabilities.** Cross-cutting behaviour attaches without modifying the agent:

```python
agent = Agent(
    build_model(settings),
    capabilities=[*CAPABILITIES, WINDOW, IdentityGate(access=TOOL_ACCESS)],
)
```

`IdentityGate` enforces access on *every* tool, including tools that do not exist yet, without
one line inside a tool. Adding a capability is addition; nothing is edited.

### The closed-ness that matters most is fail-closed

```python
def needs_customer(self, tool_name: str) -> bool:
    return self.access.get(tool_name, AccessLevel.VERIFIED_CUSTOMER) is not AccessLevel.OPEN
```

An unclassified tool is treated as sensitive. Extension by a new tool is safe *by default*:
forgetting to classify fails closed, which is the harmless direction. A design that enumerates
what is forbidden is wrong the day someone adds something; a design that enumerates what is open
is only wrong when someone adds a public thing and forgets.

**Drift symptom.** Adding a feature means editing an `if/elif` chain that three other features
also live in.

---

## 7. L — Substitutability is what makes tests possible

Liskov substitution sounds academic until you notice that it is the property your entire test
suite rests on.

pydantic-ai's `Model` interface is honoured by `GroqModel`, `TestModel`, `FunctionModel` and
`FallbackModel`. Because they are genuinely substitutable, this works:

```python
with agent.override(model=FunctionModel(explode)):
    ...
```

The agent, the capabilities, the identity gate, the output validator, the persistence — all run
unchanged against a scripted model. No mocking framework, no patching, no `if testing:`. **The
suite is fast and honest because a substitution boundary was designed properly by someone else.**

`FallbackModel` is the same property used in production: it *is* a model, so it drops into the
same slot, and nothing above it knows there is a chain.

```python
return FallbackModel(
    *(GroqModel(name, provider=provider, settings=model_settings(name, settings))
      for name in chain)
)
```

Violations of LSP look like a subtype that throws on a method the base promises, or one that
requires stricter inputs, or one that needs callers to check its concrete type. Each turns a
polymorphic call site back into a conditional.

**Drift symptom.** `isinstance` checks on things that share a base class.

---

## 8. I — Narrow interfaces, and interfaces as enforcement

Interface Segregation says clients should not depend on methods they do not use. Its practical
form: **hand each caller the smallest surface that does its job.**

Two flavours are worth separating.

### Narrow because wide is confusing

A `RunContext` gives a tool its dependencies and nothing about the agent's internals. A tool
signature says exactly what it can reach:

```python
async def get_order_detail(ctx: RunContext[SupportDeps], order_id: int) -> OrderDetail: ...
```

### Narrow because wide is dangerous

This is the version worth internalising. The interface is not just ergonomics — the omission is
the control:

```python
class Customer(FromRow):
    """Just the identity. The contact used to look someone up is never sent back to the
    model or onto a span."""

    customer_id: int
    full_name: str
```

Five columns exist in the table. Two are exposed. `email` and `phone` cannot leak into a
transcript or a trace because they are not in the type — no policy to enforce, no reviewer to
remember.

This is why a library that merges ORM rows with API models (a real temptation; `SQLModel`
exists precisely for this) would have been the wrong call here. It removes an apparent
duplication and deletes a security property with it (§11).

The same reasoning appears in telemetry: the span carries `user.id` as a customer **id**, never
the contact used to look them up.

**Drift symptom.** A model or DTO that exists "so we have everything available".

---

## 9. D — Depend on abstractions, inject the concrete

High-level policy should not import low-level detail. In practice this means: **a module names
the shape it needs; someone else decides which concrete thing satisfies it.**

Services depend on `AsyncSession`, not on a database, a URL, or a pool:

```python
class OrderService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
```

The agent depends on the `Model` interface; `build_model` decides it is Groq, wrapped in a
fallback chain. The composition root — and only the composition root — knows both sides:

```python
def build_agent(settings: Settings) -> Agent[SupportDeps, str]:
    agent = Agent(
        build_model(settings),
        deps_type=SupportDeps,
        output_type=str,
        instructions=BASE,
        capabilities=[*CAPABILITIES, WINDOW, IdentityGate(access=TOOL_ACCESS)],
    )
```

FastAPI expresses the same idea through type annotations, which is why its DI is pleasant: the
dependency is declared where it is used, and resolved by the framework.

```python
Db = Annotated[AsyncSession, Depends(get_session)]

@app.get("/orders/{order_id}")
async def order_detail(order_id: int, customer_hint: str, session: Db) -> OrderDetail: ...
```

Two payoffs, and they are the reason to bother:

**Tests need no patching.** `SupportDeps` is constructed with a real session against a temp
database. Nothing is mocked, because nothing was reached for globally.

**Ownership is explicit.** The place that creates a resource is the place that disposes of it:

```python
if sessions is not None:  # injected pool belongs to the caller; only ours gets disposed
    app.state.sessions = sessions
    yield
    return
```

**Drift symptom.** A module-level singleton reached for from inside a function — a global
`engine`, `client`, or `settings` — instead of a parameter.

---

# Part III — DRY and its counterfeits

## 10. DRY is about knowledge, not text

The original formulation is precise and usually misquoted:

> Every piece of **knowledge** must have a single, unambiguous, authoritative representation
> within a system.

Knowledge, not lines. The operative test:

> **If this changes, must the other change — for the same reason?**

### Real duplication

Two call sites encoded one fact: *how this agent is invoked*.

```python
# runner.py
result = await agent.run(
    message, deps=turn.deps, message_history=turn.history,
    conversation_id=session_id, metadata=turn.metadata, usage_limits=limits(settings),
)

# streaming.py -- the same six arguments, typed again
return await agent.run(
    message, deps=turn.deps, message_history=turn.history,
    conversation_id=session_id, metadata=turn.metadata, usage_limits=limits(settings),
    event_stream_handler=on_event,
)
```

A change to one is a bug in the other, and **no test would name it** — both paths would pass and
simply behave differently. Unified into one method on the object that already holds the state:

```python
def run_args(self, settings: Settings) -> dict[str, Any]:
    """Every argument both entry points hand the agent. Kept in one place because a
    difference between them would be a difference in behaviour that no test would name.
    """
```

### DRY across representations is the bigger win

The instructive cases are not two similar functions; they are one fact expressed in two
*languages*, where drift is silent:

| One fact | Two representations that drift | The fix |
|---|---|---|
| the database schema | `schema.sql` + ORM models | `Base.metadata` **is** the schema |
| the message format | a hand-written serialiser + the library's own | `TypeAdapter` bound to the column |
| the API contract | a Pydantic model + a hand-kept JSON Schema | `model_json_schema()` |
| the tool contract | a docstring + a separate schema | the function signature, read by the framework |

Each right-hand column removes a *file that could disagree*, which is worth more than removing
a hundred repeated lines.

---

## 11. The wrong DRY: coupling things that merely rhyme

Applied to text rather than knowledge, DRY does harm. Two pieces of code that look alike but
change for different reasons must stay apart; unifying them creates a coupling that later forces
a parameter, then a flag, then a branch — the classic decay of a "shared" helper into a
mini-framework nobody wanted.

The repository's clearest case:

```python
# tables.py -- storage. Has everything.
class Customer(Base):
    customer_id: Mapped[int]
    full_name: Mapped[str]
    email: Mapped[str]
    phone: Mapped[str | None]
    loyalty_tier: Mapped[str]

# schemas.py -- what a tool may hand back. Has two fields, on purpose.
class Customer(FromRow):
    customer_id: int
    full_name: str
```

Same name, overlapping fields, and a library exists whose entire purpose is to collapse them.
They change for different reasons: the table changes when the marketplace stores something new,
the schema changes when we decide the *model* may see something new. Merging them would have
deleted a security property while looking like a simplification (§8).

A useful counterweight to memorise: **AHA — Avoid Hasty Abstractions.** Prefer duplication over
the wrong abstraction. Duplication is cheap to find and cheap to fix; a wrong abstraction has
callers grown into it.

**Drift symptom.** You notice two similar shapes and feel an urge to unify. The urge is
aesthetic. Ask what each would change *for* before touching either.

---

# Part IV — Coupling and cohesion

## 12. Coupling is the cost of every change

Cohesion is how strongly the parts inside a module belong together. Coupling is how much a module
depends on what is outside it. **Design is largely the business of maximising the first and
minimising the second**, and most other principles are special cases of it.

A cheap, effective diagnostic: count the symbols one module imports from another.

```
streaming.py imports 5 of runner.py's 8 symbols
```

That ratio says the boundary is in the wrong place. Either it is one module, or — as here —
there is a third thing both depend on that has not been named yet:

```
intake.py     Intake, resolve_customer, classify        the shared lifecycle
runner.py     run_turn                                  one response
streaming.py  stream_turn                               the same turn, as events
```

Neither entry point imports from the other now. That is the shape to aim for: siblings over a
shared abstraction, not a chain of peers reaching into each other.

### Direction matters as much as amount

Dependencies should point toward stability. Domain rules should not import HTTP; HTTP may import
domain rules. Concretely here: `policies.py` is pure functions over a status, so it imports
nothing and can be tested in microseconds; `api/app.py` imports everything and is the only place
that knows about status codes.

### Law of Demeter

`a.b.c.d()` couples you to three shapes at once. Every dot after the first is a fact about
someone else's internals that you have promised not to change.

```python
# reaching through
customer_name = intake.deps.customer.full_name if intake.deps.customer else None

# asking the object that knows
@property
def customer(self) -> Customer | None:
    return self.deps.customer
```

---

## 13. Tell, don't ask

Prefer telling an object to do something over asking for its data and doing it yourself. The
signature tells you when you have got it backwards.

```python
# Asking: the function pulls the object apart, and re-passes state the object already holds.
def run_args(intake: Intake, *, session_id: str, settings: Settings) -> dict[str, Any]: ...
async def finish(intake: Intake, result, *, session_id: str, message: str) -> AgentReply: ...
async def salvage(intake: Intake, captured: list[ModelMessage], session_id: str) -> None: ...

# Telling
class Intake:
    def run_args(self, settings: Settings) -> dict[str, Any]: ...
    async def finish(self, result: Any) -> AgentReply: ...
    async def salvage(self, captured: list[ModelMessage]) -> None: ...
```

Two tells in the "before": every function takes the object first, and two take `session_id` —
which the object already holds. Each call site lost an argument it was only threading through.

**The heuristic:** if a function's first parameter is an object and its other parameters are
fields of that object, it is a method.

---

## 14. Composition over inheritance

Inheritance couples you to a hierarchy that must be right up front. Composition lets behaviour
be assembled per case. Prefer composition unless there is a genuine is-a relationship *and*
substitutability holds (§7).

Well-composed systems look like lists:

```python
# behaviour assembled from independent pieces
capabilities=[*CAPABILITIES, WINDOW, IdentityGate(access=TOOL_ACCESS)]

# constraints assembled from independent pieces
Amount = Annotated[float, BeforeValidator(lambda v: v or 0.0), Field(ge=0)]

# data assembled from independent pieces
class OrderDetail(FromRow):
    items: list[OrderItem] = Field(default_factory=list)
    shipment: Shipment | None = None
```

Where inheritance *is* used, it should carry exactly one thing. `FromRow` carries a
`model_config` and nothing else — no fields, no methods, no behaviour to override. A base class
that carries one policy stays correct; one that accumulates helpers becomes the god object every
model drags around.

React's composition guidance is the same principle in another language: prefer explicit variant
components over boolean props, because `<Turn isAgent isStreaming isError>` is a hierarchy
pretending to be a parameter list.

---

# Part V — Design in the small

## 15. Make illegal states unrepresentable

The strongest guarantee is one where the wrong thing cannot be expressed. Ranked by strength:

1. **Impossible** — the type system rejects it.
2. **Rejected at the boundary** — a parse fails.
3. **Checked at use** — a runtime assertion.
4. **Documented** — a convention and hope.

Move up when you can, and **say so when you move down.**

The original data layer sat at level 1 for ownership scoping: a `Database` class exposed no
method that read customer data without a `customer_id`, so a cross-customer read was
*unreachable*, not merely absent. Moving to SQLAlchemy sessions dropped it to level 4: a service
holds an `AsyncSession` and could write `select()` with no `WHERE`.

The move was still right — a bespoke persistence interface nobody knows costs more than it saves
(§3) — but the honest response is neither to hide the loss nor to abandon the move:

1. **Say it** in the section that claims the guarantee.
2. **Replace structure with a test** that fails if the convention breaks.
3. **Keep the shape** that makes the right thing the easy thing:

```python
def _owned(self, order_id: int, customer_id: int):
    return select(tables.Order).where(
        tables.Order.order_id == order_id, tables.Order.customer_id == customer_id
    )
```

Smaller applications of the same idea: a `StrEnum` instead of a string; a union of typed variants
instead of a `dict` with a `type` key; a `Decision` object instead of `(bool, str, str)`.

> **What did this make possible that was impossible before — and what did it make possible that
> used to be impossible on purpose?**

---

## 16. Errors have three shapes

Not everything that goes wrong is an exception. Three kinds, three mechanisms:

| Kind | Mechanism | Example |
|---|---|---|
| A correct answer that happens to be "no" | a typed result | `ActionResult(code=ORDER_ALREADY_SHIPPED, detail=...)` |
| A recoverable mistake by the caller | ask for a retry | `ModelRetry` on a stale order id |
| Infrastructure failure | catch, log, degrade | a dropped connection becomes a refusal offering escalation |

A refusal is **not** an exception. The address lock, the refund ceiling, a cancelled order — these
are the system working correctly. Raising for them turns normal operation into control flow that
every caller must catch, and callers that forget produce 500s for correct answers.

```python
class ResultCode(StrEnum):
    OK = "ok"
    ORDER_ALREADY_SHIPPED = "order_already_shipped"
    ORDER_CANCELLED = "order_cancelled"
    REFUND_EXCEEDS_LIMIT = "refund_exceeds_limit"
    UNAVAILABLE = "unavailable"

class ActionResult(BaseModel):
    code: ResultCode
    detail: str
```

The code is what a caller branches on; the sentence is what a human reads. No `success` boolean
beside the code — two fields for one fact can disagree (§17).

### A refusal must carry its own evidence

Found in a real conversation. The refusal read "the parcel is already with the courier, contact
them" — while naming no courier. The consumer filled the gap from an earlier turn and told the
customer to chase order 1 using order 2's tracking number.

```python
if not decision.allowed:
    # Name this order's courier, or the model quotes one it remembers from an earlier turn.
    shipment = await self.shipment(order_id, customer_id)
    detail = decision.detail
    if shipment and shipment.tracking_number:
        detail += (f" Paket ini dikirim lewat {shipment.courier} dengan nomor resi "
                   f"{shipment.tracking_number}.")
    return ActionResult(code=decision.code, detail=detail)
```

> **A gap the consumer can see is a gap it will fill.** True of an LLM, a UI with a default
> value, and a downstream service with a fallback. The somewhere it fills from is not under your
> control.

### Prefer failures that raise

Every recovery mechanism — fallback, retry, circuit breaker, supervisor — can only see failures
that **raise**. A component that fails by returning something plausible is invisible to all of
them.

A candidate fallback model here never emitted a tool call; it wrote the protocol into the text
channel as `<function=get_order_detail{"order_id": 1}</function>`. The provider *sometimes*
rejected that with a 400 — recoverable — and *sometimes* returned it as ordinary content, which
raises nothing. In the second case the fallback chain is blind and the customer receives protocol
noise as an answer.

> **A component that fails loudly is recoverable. One that answers confidently and wrongly is
> not.** Prefer the loud one even when it is otherwise stronger.

---

## 17. Derive, don't restate

Prefer a fact the system already holds over the same fact reported by something else. A
restatement can disagree; a derivation cannot.

```python
def outcome(messages: list[ModelMessage]) -> tuple[bool, int | None]:
    """Whether the turn was escalated, and to which ticket -- read from what ran.

    Asking the model to report this would be asking it to restate a fact the runtime already
    holds, and a restatement can disagree with the fact.
    """
```

Generalise past agents. Each of these is a second source of truth waiting to disagree with the
first:

- a `success` boolean beside a status code
- a `total` column beside line items
- a `count` field beside a list
- a cached `is_admin` beside a roles table
- a denormalised `customer_name` beside a foreign key

Each is sometimes justified — by measured read cost, not by convenience — and each needs an owner
responsible for the invariant. If you cannot name that owner, derive instead.

**Drift symptom.** Adding a field so that something downstream "knows" what happened, when
downstream could look.

---

## 18. Own your resources explicitly

Say who creates a resource, who closes it, and what it is bound to. Most async and lifecycle bugs
are one of those three left implicit.

**Scope must outlive use.** FastAPI closes a `yield` dependency *before* a `StreamingResponse`
finishes streaming, so a session injected that way is already closed when the generator resumes:

```python
async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """For plain reads only. A streaming response outlives this teardown, so the chat routes
    open their own scope instead.
    """
```

**A connection belongs to the loop that opened it.** `TestClient` drives an app from a worker
thread with its own event loop; an `asyncpg` connection made on the test's loop then fails with
`got Future attached to a different loop`. Run the app in the same loop:

```python
async with (
    app.router.lifespan_context(app),
    AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
):
    yield client
```

Worth noting that SQLite tolerated this for months. **A more permissive tool is not a safer one;
it is one that defers the bug to a worse moment.**

**Transactions have one boundary.**

```python
@asynccontextmanager
async def session_scope(factory: Sessions) -> AsyncIterator[AsyncSession]:
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

**Drift symptom.** You cannot answer "who closes this?" in one sentence.

---

# Part VI — Restraint

## 19. YAGNI, and the cost of a knob

You Aren't Gonna Need It. Speculative flexibility is paid for on every read, by everyone, forever
— and the future rarely arrives in the shape you guessed.

Everything must be tied to a requirement it satisfies or a failure it prevents:

- **A field with a constant value** carries no information.
- **Two fields encoding one fact** can disagree (§17).
- **A field the model never needs** is prompt weight, and if it is a contact detail it is PII in
  a trace.
- **Instrumentation that emits nothing** should be removed, not documented. `instrument_sqlite3`
  produced zero spans; it was measured, then deleted.
- **An unimported dependency** is pure cost — supply-chain surface, a version constraint, and a
  reader's assumption that it is load-bearing. `arize-phoenix-otel` sat in `pyproject.toml`
  unimported for the life of the project.

A knob is an API: someone will turn it. It earns its place by preventing a specific failure, and
it must handle its own edges:

```python
# "parsed" gives reasoning its own field; "hidden" leaks analysis into content, which Groq
# fails to parse (gpt-oss-20b: 3/3 vs 1/3). Empty for a non-reasoning model.
reasoning_format: Literal["hidden", "raw", "parsed"] | None = "parsed"

@field_validator("reasoning_format", mode="before")
@classmethod
def _blank_is_off(cls, value: object) -> object:
    # An empty env var is how you spell "off"; without this it is a startup crash.
    return None if value == "" else value
```

One knob was deleted outright: its alternate branch made the model invent tools that did not
exist. **A setting whose other position is always wrong is not configuration, it is a trap.**

---

## 20. Reach for the framework's seam before writing machinery

Read the library's public surface once — `dir(Agent)` takes thirty seconds — and ask of each
entry: *what problem was this added to solve, and is one of them mine?*

> Hand-rolled machinery almost always exists to **undo** something the library did on purpose.
> The library nearly always shipped the undo itself.

| Written by hand | The seam that already existed |
|---|---|
| `asyncio.Queue` + background task + sentinel, to escape a callback | `agent.run_stream_events` |
| a `model=` parameter on `build_agent`, used only by tests | `agent.override(model=...)` |
| a trailing-window `WHERE` clause in the load query | `ProcessHistory(processor)` |
| `dump_json()` / `validate_json()` around a `TEXT` column | `TypeDecorator` + `TypeAdapter` |
| a `Database` class wrapping a driver, plus `schema.sql` | SQLAlchemy: `Base.metadata`, `session_scope` |

The streaming case is the clearest. The reasoning that produced the queue was correct as far as
it went — `event_stream_handler` returns `Awaitable[None]`, so it cannot `yield` into a response,
so something must carry events across that boundary. All true. The error was stopping there
rather than asking whether the library had already noticed:

```python
async with agent.run_stream_events(message, **intake.run_args(settings)) as events:
    async for item in events:
        ...
        elif isinstance(item, AgentRunResultEvent):
            result = item.result
```

The queue, the task and its sentinel all went away. Everything they replaced worked and had
passing tests. **Working is not the bar.** The bar is that someone who knows the library
recognises your file.

### The counter-question that keeps this honest

*Is the seam actually a fit, or am I contorting my problem to reach it?* `Agent.to_web()` exists
and was **not** used — the UI here has its own identity model and its own language. Reaching for
a seam you must fight is the same mistake pointing the other way.

**Drift symptom.** You are about to write a class whose job is coordination — a queue, a
registry, a wrapper, a manager.

---

## 21. Helpers, and the ones that want to be methods

A helper used exactly once is usually worse than the code inlined: it adds a name to learn and a
jump to follow. Extract when the code is used more than once, or when the extraction genuinely
*names a concept the reader needs*.

Worse than an unnecessary helper is one that folds two meanings into one return value:

```python
# Bad -- returns lastrowid for inserts and rowcount for updates. One function, two meanings.
async def _write(self, sql, params) -> int: ...

# Good -- two names, each with one meaning.
async def _insert(self, sql, params) -> int: ...
async def _update(self, sql, params) -> bool: ...
```

And see §13: a helper whose first parameter is an object, with the rest being that object's
fields, is a method that has not been moved yet.

---

## 22. Delete what nothing calls — after checking who calls

Deleted from this repository: a `Decision.as_result()` with no caller, and an
`ActionResult.success` property read only by tests that asserted the property existed — a test of
its own subject, guarding a value nothing branched on.

### The trap: "unreferenced" is not "unused"

A crude scan flagged eight `StrEnum` members as dead. Deleting them would have broken the system:
`'refunded'` and `'out_for_delivery'` are values in seed data — real rows that would fail to
parse — and `TicketCategory` is the vocabulary an LLM chooses from as a tool argument. Neither is
referenced by Python code; both are load-bearing.

Before deleting a symbol, check **four** callers:

1. **Code** — grep.
2. **Data** — could a stored row, fixture, or migration contain this value?
3. **Consumers you do not compile** — an LLM tool schema, a frontend, a public API.
4. **The framework** — called by name, not by you: `process_bind_param`, `cache_ok`, route
   handlers, `__init__` parameter names read via reflection.

That fourth category is the subtle one. A cache key silently collapsed here because SQLAlchemy
reads `__init__` parameter names and matches them against instance attributes:

```python
self.model = model     # not `_model`: the framework looks for this exact name
```

**Drift symptom.** A static scan says "unused" and you believe it without asking who else reads
this program.

---

# Part VII — Communication

## 23. Naming: one name, one meaning

A name is chosen against every other use of that word in the system, not against its own module.

Two classes named `Turn` existed here at once: one an exchange in a transcript (`role`, `text`,
`tools`), the other the working set assembled before a run. Both were locally sensible; together
they made "the turn" ambiguous in every conversation about the code.

The first attempt was `TurnContext` — half a fix, since `Turn` and `TurnContext` still read as
two spellings of one idea. The question that resolved it: **which meaning has the stronger claim
on the word?** `Turn` is the wire shape of an endpoint and the type the UI renders, so it keeps
the name; the other became `Intake`, a word already used for that phase.

### Avoid umbrella names

`contracts.py`, `utils.py`, `helpers.py`, `base.py`, `common.py`, `types.py`, `manager.py`,
`handler.py`. **If a name would fit five unrelated files, it is too broad.** "Contract" is the
worst offender: every interface is a contract, so the word names nothing.

```
contracts.py   ->  access_levels.py     # it defines who may reach which tool
errors.py      ->  results.py           # it holds outcomes, not errors
```

Prefer the concrete noun the module is actually about: `identity_gate.py`, `message_store.py`,
`model_factory.py`, `transcript.py`.

**Drift symptom.** You disambiguate by adding a suffix — `Context`, `Info`, `Data`, `Manager` —
instead of asking which meaning owns the root word.

---

## 24. Comments carry four things and nothing else

A comment earns its place by carrying a **rationale**, an **invariant**, a **trade-off**, or a
**contract at a boundary**. Anything else is noise, and noise is not neutral: it dilutes the
comments that matter, and it rots.

### The drift has one cause: writing the same explanation three times

Every time this project turned up something non-obvious, the discovery was written into the
module docstring, *and* the commit message, *and* the design document. That felt like diligence.
It is three copies of one explanation that can rot apart — and the docstring is the copy nobody
updates.

| Where | Its one job |
|---|---|
| Design document | the decision and the argument for it |
| Commit message | why this change, now |
| Test | the fact, executably |
| Comment | only what a reader **at that line** would otherwise get wrong |

Note row three. **A test that asserts a fact makes the paragraph describing that fact
redundant** — and unlike the paragraph, the test cannot lie.

### The measurement that catches it

Prose-to-code ratio per file. Crude, and it works:

```
0.88  prose=14 code=16   data/pydantic_column.py
2.00  prose= 6 code= 3   shared/from_row.py
```

The explanation was larger than the thing explained. After the cut: `0.44`, `1.67`, and **0.18
across `src/`**. Exempt modules whose docstrings are read by a consumer — an LLM tool
description is row four of the table, a contract at a boundary.

### What survives a cut

Comments a reasonable person would "tidy" straight back into a bug:

```python
# Not `_model`: `cache_ok` requires an attribute named for the __init__ parameter, or
# the cache key drops it and every PydanticJson column compares equal.
self.model = model
```

```python
# Name this order's courier, or the model quotes one it remembers from an earlier turn.
shipment = await self.shipment(order_id, customer_id)
```

Both are invariants held by nothing else. Delete either and the next cleanup reintroduces a
defect that has already happened once.

**A wrong comment is worse than none.** When the code beneath a comment moves, re-read the
comment.

**Drift symptom.** You are pleased with a sentence you just wrote in a docstring. Pleasure is a
signal that it was written for an audience that admires reasoning, not for someone trying to
change the line below it.

---

## 25. Record reversals and costs, not just decisions

When you reverse a decision, the valuable part is not the new choice. It is **why the original
argument failed** — because that argument will be made again, by someone reasonable, possibly by
you.

SQLAlchemy was rejected here with a plausible case: only ~10 queries, and pooling is meaningless
against a local file. Both facts were true and the conclusion was wrong, because the argument
measured *query volume* when what mattered was *interface familiarity* and a schema declared
twice. Writing only "we now use SQLAlchemy" would have preserved the mistake and thrown away the
lesson.

A reversal entry carries three things: the original reasoning, the fact that broke it, and **what
the original reasoning was measuring instead of what mattered.** Mark it rather than deleting the
old row. **A decision log showing only the decisions that survived is a log of hindsight, not of
thinking.**

The same applies to cost. Every decision buys something and spends something; write the spending
down where it will be felt (§15). A decision recorded only in terms of its benefits reads, six
months later, as a decision with no downside — and nobody revisits those.

**Drift symptom.** A summary of your own work in which everything got better.

---

# Part VIII — Evidence

## 26. Verify against the installed version

Before building on a behaviour, observe it in the version that is installed. Not the docs for the
version you remember, and not your recollection of the docs.

> **Have I seen this happen, or do I only believe it?**

If it is belief, spend the two minutes:

```python
inspect.signature(Agent.run)                    # what does it actually accept?
util.get_cls_kwargs(PydanticJson)               # what does the framework read from my class?
grep -rn "'interrupted'" .venv/.../pydantic_ai/ # who writes this value, and when?
```

Four claims that looked obviously true here and were not:

- **`metadata=` on a run "attaches to the message."** It reaches `RunContext.metadata`,
  `result.metadata` and the span. The message field stays `null`. A design that stored app data
  there would have shipped a permanently empty column.
- **`state='interrupted'` "marks a run that died."** It is written when a *tool* is cancelled. A
  run whose model call raised still reads `complete`.
- **`cache_ok = True` "includes the type's state in its cache key."** Only if that state is stored
  under the `__init__` parameter's own name, un-underscored. Two differently-parameterised
  instances compared equal.
- **`instrument_sqlite3` "instruments the database."** Zero spans, because the driver ran on a
  worker thread.

Each was caught by a five-line script or a failing test. Each would otherwise have become a
confident paragraph describing something that never happened — the worst outcome, because **a
design note asserting behaviour you did not observe stops the next person from checking.**

**Drift symptom.** You write "because the framework does X" without having run anything.

---

## 27. Measure before you order things

Any ranking you write down — model quality, retry counts, cache sizes, timeouts, index choices —
is a claim. Either measure it or label it a guess.

Measurements that changed decisions here:

- **Model ordering.** Three runs each of one real question, scored on whether the answer was
  grounded in a tool call. It reordered the list, changed the default, and removed two candidates.
- **Reasoning format.** `parsed` 3/3 versus `hidden` 1/3, so the default is `parsed` and the
  comment carries the numbers.
- **Output type.** A structured output tool produced no result 2/4 times on the hardest case;
  plain text with derived structure, 4/4.
- **Instrumentation.** One instrumentor emitted zero spans and was deleted; its replacement was
  verified against an in-memory exporter *before* being wired in.
- **Comment volume.** A prose/code ratio, which is how §24's regression was found rather than
  argued about.

Cheap measurement beats confident reasoning, and it is usually five lines:

```python
exp = InMemorySpanExporter()
logfire.configure(send_to_logfire=False, additional_span_processors=[SimpleSpanProcessor(exp)])
...
print([s.name for s in exp.get_finished_spans()])
```

**Drift symptom.** A ranked list in a comment with no numbers beside it.

---

## 28. Tests are design feedback, not a chore

A test that is hard to write is telling you something about the design. Listen before reaching
for a mock.

**Hard to construct** → too many dependencies, or dependencies reached for globally. Fix with
injection (§9), not with patching.

**Needs patching to observe** → the fact you want is not exposed. Here, escalation is derived
from the transcript (§17), so the test reads what ran instead of intercepting a call.

**Needs a running model, browser, or network** → the logic is entangled with I/O. Policies here
are pure functions over a status, so the rules are asserted in microseconds:

```python
@pytest.mark.parametrize(
    ("amount", "escalate"),
    [(0, False), (999_999, False), (1_000_000, False), (1_000_001, True)],
)
def test_refund_ceiling_is_exclusive(amount: float, escalate: bool) -> None:
    assert refund_policies.requires_escalation(amount) is escalate
```

**Only passes in one order** → shared state between tests.

Two further rules worth holding:

**Test behaviour, not your own scaffolding.** A test asserting that a derived property exists,
which nothing else reads, tests only itself. It was deleted here along with the property.

**A test should be able to fail for one reason.** The clearest tests in this repository each pin
exactly one claim: that a crashed run is persisted once and not duplicated; that a run holding an
unanswered tool call is never replayed; that two column types do not share a cache key. Each was
written *because* a specific belief turned out to be false — which is the best reason a test ever
has.

---

# Closing

## 29. The drift checklist

Run these before calling work done. Ordered by how often they catch something.

**Is the abstraction hiding a decision, or just a layer?** — §1
Name the decision it hides and how it might change. If you cannot, it is a rename.

**Did I write machinery the library already has?** — §20
Read `dir()` on the main class. Any coordination class you wrote — queue, wrapper, registry,
manager — is a suspect.

**Did I assert behaviour I did not observe?** — §26
Search your diff for "because", "so that", "the framework". Each is a claim. Which did you run?

**Does this module have one audience?** — §5
Describe it without using "and".

**Would unifying these two things couple facts that change for different reasons?** — §10, §11
Ask what each would change *for*.

**Does any function take its object as the first argument?** — §13
It is a method.

**Did I remove a constraint and describe only what got easier?** — §15, §25
Say what is now possible that used to be impossible on purpose.

**Does any recovery path assume the failure raises?** — §16
Name the failure mode it *cannot* see, and write that next to it.

**Is this comment carrying a rationale, an invariant, a trade-off, or a boundary contract?** — §24
If not, delete it. If the same explanation is also in a commit message and a design document, two
of the three are wrong.

**Did I check all four callers before deleting?** — §22
Code, data, unbuilt consumers, framework-by-name.

**Is any ranking in this diff unmeasured?** — §27
Numbers, or an admission. Not prose.

**Does any name in this diff already mean something else here?** — §23

**Did I say plainly what did not work?** — everywhere
Tests that fail, steps skipped, parts unfinished. A report in which everything succeeded is the
least likely report to be true.
