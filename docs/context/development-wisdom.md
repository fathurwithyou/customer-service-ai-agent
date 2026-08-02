# SKILL.md

## Pydantic and PydanticAI Coding Wisdom

Build the agentic system with clear boundaries.

```text
Pydantic model
-> service function
-> tool
-> capability
-> agent
-> runner
```

Pydantic is used for data contracts.

PydanticAI is used for agent runtime.

Service is used for business logic.

Tool is used as a thin adapter from the model to the service.

Capability is used as a reusable domain ability.

Agent is used as the composition root for model, dependencies, output, capabilities, hooks, model settings, and message history.

Runner is used as the application entry point.

Do not put business logic inside the agent. Do not put database transaction logic inside tools. Do not use prompt as the only security boundary. Prompt guides model behavior, but security must be enforced by schema, validators, tool filtering, approval flow, permission checks, and service-level policy.

## Folder Structure

Use this structure as the default.

```text
src/
  agentic_system/
    agents/
      banking/
        agent.py
        deps.py
        output.py
        instructions.py
        runner.py
        specs.py

    capabilities/
      transfer/
        capability.py
        tools.py
        schemas.py
        instructions.py
        services.py
        policies.py

      account_lookup/
        capability.py
        tools.py
        schemas.py
        instructions.py
        services.py

      complaint/
        capability.py
        tools.py
        schemas.py
        instructions.py
        services.py
        policies.py

    shared/
      settings.py
      errors.py
      validation.py
      serialization.py
      telemetry.py
      http_client.py
      model_factory.py
      tool_utils.py

    evaluation/
      datasets/
      evaluators.py
      test_cases.py
```

Do not create an orchestration folder too early. Start with runner.py. Split into a more complex workflow only after the complexity is real.

## Pydantic Model Wisdom

Use BaseModel for data contracts between layers.

```python
# capabilities/transfer/schemas.py

from pydantic import BaseModel, ConfigDict, Field


class TransferIntent(BaseModel):
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        populate_by_name=True,
    )

    source_account_id: str
    destination_account_number: str = Field(
        min_length=6,
        max_length=32,
        description="Destination bank account number.",
    )
    amount: int = Field(gt=0)
    note: str | None = Field(default=None, max_length=140)
```

Pydantic model is not just a DTO. It is a boundary that keeps data valid before it enters service logic, tool arguments, agent output, API responses, queue payloads, or external requests.

Use extra="forbid" for important input. Do not allow unknown fields to silently enter the system.

Use strict=True when coercion is dangerous. For example, "100000" should not always be accepted as 100000, especially for money, role, permission, limit, and status.

## Field Wisdom

Use Field for constraints, description, alias, and schema documentation.

```python
from pydantic import BaseModel, Field


class TransferPreview(BaseModel):
    recipient_name: str = Field(description="Resolved recipient account name.")
    destination_account_number: str
    amount: int = Field(gt=0)
    fee: int = Field(ge=0)
    total_amount: int = Field(gt=0)
    requires_confirmation: bool = True
```

Do not validate important numbers only in the prompt. Constraints must live in schema and service.

## Alias Wisdom

Use alias when external payload names are different from Python names.

```python
from pydantic import BaseModel, ConfigDict, Field


class TransferIntent(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        extra="forbid",
    )

    source_account_id: str = Field(alias="sourceAccountId")
    destination_account_number: str = Field(alias="destinationAccountNumber")
    amount: int
```

Internal Python code should use snake_case. External API payload can use camelCase.

```python
intent = TransferIntent.model_validate(
    {
        "sourceAccountId": "acc-1",
        "destinationAccountNumber": "1234567890",
        "amount": 100_000,
    }
)

payload = intent.model_dump(by_alias=True)
```

Do not spread camelCase across Python code only because the frontend uses camelCase.

## Configuration Wisdom

Use explicit configuration for important models.

```python
from pydantic import BaseModel, ConfigDict


class StrictDomainModel(BaseModel):
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        validate_assignment=True,
        populate_by_name=True,
    )
```

Use a base domain model when multiple models share the same validation policy.

```python
class DomainModel(StrictDomainModel):
    pass


class TransferIntent(DomainModel):
    source_account_id: str
    destination_account_number: str
    amount: int
```

Do not repeat model configuration everywhere if the domain rule is the same.

## Union Output Wisdom

Use structured output for agent results that will be consumed by backend code.

```python
# agents/banking/output.py

from typing import Literal

from pydantic import BaseModel, Field


class NeedClarification(BaseModel):
    type: Literal["need_clarification"]
    question: str


class TransferDraft(BaseModel):
    type: Literal["transfer_draft"]
    source_account_id: str | None = None
    destination_account_number: str | None = None
    amount: int | None = Field(default=None, gt=0)
    note: str | None = None


class RequireConfirmation(BaseModel):
    type: Literal["require_confirmation"]
    preview_id: str
    message: str


class RejectRequest(BaseModel):
    type: Literal["reject_request"]
    reason: str


class PlainAnswer(BaseModel):
    type: Literal["plain_answer"]
    answer: str


BankingOutput = (
    NeedClarification
    | TransferDraft
    | RequireConfirmation
    | RejectRequest
    | PlainAnswer
)
```

Backend must read output.type. Do not parse natural language text to decide application state.

```python
def handle_agent_output(output: BankingOutput):
    match output.type:
        case "need_clarification":
            return output.question

        case "transfer_draft":
            return output

        case "require_confirmation":
            return output.message

        case "reject_request":
            return output.reason

        case "plain_answer":
            return output.answer
```

Use Literal for state. Use union for branching output. Use BaseModel for each output shape.

## TypeAdapter Wisdom

Use TypeAdapter when validating a type that is not a single BaseModel, especially union, list, dict, and dynamic payloads.

```python
from pydantic import TypeAdapter

BankingOutputAdapter = TypeAdapter(BankingOutput)

output = BankingOutputAdapter.validate_python(raw_output)
json_schema = BankingOutputAdapter.json_schema()
```

Do not create fake wrapper models just to validate a union.

## Validator Wisdom

Use validators for local data invariants. Do not put database-dependent business rules inside validators.

```python
from pydantic import BaseModel, Field, field_validator, model_validator


class TransferIntent(BaseModel):
    source_account_id: str
    destination_account_number: str
    amount: int = Field(gt=0)
    note: str | None = None

    @field_validator("destination_account_number")
    @classmethod
    def account_number_must_be_numeric(cls, value: str) -> str:
        if not value.isdigit():
            raise ValueError("destination account number must be numeric")
        return value

    @model_validator(mode="after")
    def source_and_destination_must_differ(self):
        if self.source_account_id == self.destination_account_number:
            raise ValueError("source and destination account cannot be the same")
        return self
```

Validators are good for local invariants. Permission, ownership, balance, fraud check, and limit check must stay in service or policy.

## Serialization Wisdom

Use model_dump for Python dict. Use model_dump_json for JSON string. Use by_alias=True when sending payload to external systems.

```python
payload = intent.model_dump()
external_payload = intent.model_dump(by_alias=True)
json_payload = intent.model_dump_json(by_alias=True)
```

Do not send **dict** as payload. That bypasses Pydantic serialization rules.

## JSON Schema Wisdom

Use JSON Schema for tool contracts, output contracts, documentation, and evaluation.

```python
schema = TransferIntent.model_json_schema()
```

If a schema will be read by a model or external tool, add descriptions to the model and fields.

```python
from pydantic import BaseModel, Field


class TransferIntent(BaseModel):
    """Bank transfer draft before final confirmation."""

    destination_account_number: str = Field(
        description="Destination bank account number provided by the user."
    )
    amount: int = Field(
        gt=0,
        description="Transfer amount in IDR."
    )
```

Clear schema reduces wrong tool calls.

## Pydantic Settings Wisdom

Use pydantic-settings for environment configuration. Do not scatter os.getenv across the codebase.

```python
# shared/settings.py

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="APP_",
        extra="ignore",
    )

    environment: str = "development"
    redis_url: str
    database_url: str
    default_model: str = "openai:gpt-5.2"
    logfire_token: str | None = None


settings = AppSettings()
```

Settings are application dependencies. Pass them into services or dependency containers when needed.

## Dataclass Dependency Wisdom

Use dataclass for lightweight runtime dependency containers. Use BaseModel for payloads that need validation, serialization, and JSON Schema.

```python
# agents/banking/deps.py

from dataclasses import dataclass
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class BankingDeps:
    user_id: str
    session: AsyncSession
    redis: Redis
    account_service: "AccountService"
    transfer_service: "TransferService"
    permission_service: "PermissionService"
```

deps is not an external payload. deps is runtime application context. A dataclass is usually enough.

## Validate Call Wisdom

Use validate_call for function boundaries that receive untrusted input and need validation.

```python
from pydantic import validate_call


@validate_call
def calculate_admin_fee(amount: int) -> int:
    if amount < 1_000_000:
        return 2_500
    return 0
```

Do not put validate_call on every function. Use it on boundaries.

## Error Wisdom

Treat ValidationError as input error, not as internal crash.

```python
from pydantic import ValidationError


async def parse_transfer_intent(raw: dict):
    try:
        return TransferIntent.model_validate(raw)
    except ValidationError as exc:
        return {
            "type": "validation_error",
            "errors": exc.errors(),
        }
```

Do not show raw traceback to the user. Convert validation errors into safe application errors.

## Agent Wisdom

Agent is the composition root. It should be thin.

```python
# agents/banking/agent.py

from pydantic_ai import Agent

from .deps import BankingDeps
from .instructions import BANKING_AGENT_INSTRUCTIONS
from .output import BankingOutput
from src.agentic_system.capabilities.account_lookup.capability import account_lookup_capability
from src.agentic_system.capabilities.complaint.capability import complaint_capability
from src.agentic_system.capabilities.transfer.capability import transfer_capability


banking_agent = Agent[BankingDeps, BankingOutput](
    "openai:gpt-5.2",
    deps_type=BankingDeps,
    output_type=BankingOutput,
    instructions=BANKING_AGENT_INSTRUCTIONS,
    capabilities=[
        account_lookup_capability,
        transfer_capability,
        complaint_capability,
    ],
)
```

Create another agent only when persona, permission boundary, output contract, or risk boundary is different.

Do not create another agent just because there is one new action.

## Dependencies Wisdom

deps_type is a typing contract. deps is the runtime object that becomes ctx.deps.

```python
# agents/banking/runner.py

from .agent import banking_agent
from .deps import BankingDeps


async def run_banking_agent(
    *,
    user_id: str,
    message: str,
    session,
    redis,
    account_service,
    transfer_service,
    permission_service,
    message_history=None,
):
    deps = BankingDeps(
        user_id=user_id,
        session=session,
        redis=redis,
        account_service=account_service,
        transfer_service=transfer_service,
        permission_service=permission_service,
    )

    result = await banking_agent.run(
        message,
        deps=deps,
        message_history=message_history,
    )

    return result.output, result.all_messages()
```

Do not assume deps_type validates runtime dependencies. If deps is wrong, the error may happen only when a tool accesses ctx.deps.some_field.

Use parent deps only when the capability only needs fields from the parent type.

```python
from dataclasses import dataclass


@dataclass
class BaseDeps:
    user_id: str


@dataclass
class BankingDeps(BaseDeps):
    transfer_service: "TransferService"
```

If a tool needs transfer_service, use RunContext[BankingDeps], not RunContext[BaseDeps].

## Capability Wisdom

Capability is the recommended unit for reusable behavior.

A capability can provide instructions, tools, toolsets, hooks, native tools, wrapper toolsets, and model settings.

```python
# capabilities/transfer/capability.py

from pydantic_ai.capabilities import Capability

from .instructions import TRANSFER_CAPABILITY_INSTRUCTIONS
from .tools import create_transfer_preview, validate_recipient


transfer_capability = Capability(
    id="transfer",
    description="Prepare transfer drafts and validate transfer recipients.",
    instructions=TRANSFER_CAPABILITY_INSTRUCTIONS,
    tools=[
        validate_recipient,
        create_transfer_preview,
    ],
)
```

```python
# capabilities/transfer/instructions.py

TRANSFER_CAPABILITY_INSTRUCTIONS = """
Use this capability only for transfer-related requests.

Always validate the recipient before creating a transfer preview.
Ask for clarification when the amount, recipient, or source account is missing.
Never claim that a transfer has been executed unless the backend returns a receipt.
"""
```

Capability is not a service layer. It packages the domain ability so the agent does not need to register every tool manually.

Use deferred capability when the capability is large, expensive, rarely used, or should only be loaded after the model decides it needs it.

```python
from pydantic_ai.capabilities import Capability

transfer_capability = Capability(
    id="transfer",
    description="Load this when the user wants to prepare or review a bank transfer.",
    defer_loading=True,
    instructions=TRANSFER_CAPABILITY_INSTRUCTIONS,
    tools=[
        validate_recipient,
        create_transfer_preview,
    ],
)
```

If you need settings, hooks, native tools, or custom per-run logic, create a custom capability by subclassing AbstractCapability.

## Tool Wisdom

Tool is a thin adapter from LLM to service.

```python
# capabilities/transfer/tools.py

from pydantic_ai import RunContext

from src.agentic_system.agents.banking.deps import BankingDeps
from .schemas import TransferIntent, TransferPreview


async def validate_recipient(
    ctx: RunContext[BankingDeps],
    account_number: str,
) -> str:
    return await ctx.deps.transfer_service.validate_recipient(
        account_number=account_number,
    )


async def create_transfer_preview(
    ctx: RunContext[BankingDeps],
    intent: TransferIntent,
) -> TransferPreview:
    await ctx.deps.permission_service.ensure_can_create_transfer(
        user_id=ctx.deps.user_id,
    )

    return await ctx.deps.transfer_service.create_preview(intent)
```

Do not put SQL, long HTTP retry logic, permission chains, or database transaction logic in a tool. Put those in service.

A pure tool can be a normal function.

```python
def calculate_admin_fee(amount: int) -> int:
    return 2_500 if amount < 1_000_000 else 0
```

Use sequential tools only when order matters. Let independent tools run concurrently.

Use requires_approval for tools that need human or application approval before execution.

## Service Wisdom

Service owns business logic.

```python
# capabilities/transfer/services.py

from .schemas import TransferIntent, TransferPreview


class TransferService:
    async def validate_recipient(
        self,
        *,
        account_number: str,
    ) -> str:
        ...

    async def create_preview(
        self,
        intent: TransferIntent,
    ) -> TransferPreview:
        ...

    async def execute_transfer(
        self,
        *,
        preview_id: str,
        approved_by: str,
    ) -> str:
        ...
```

Service must be testable without LLM. If logic cannot be tested without the agent, it is in the wrong place.

Final side effects must not be exposed as normal tools. Money transfer, delete operation, permanent status update, or email sending must go through service-level permission check, idempotency, transaction, and audit log.

## Policy Wisdom

Policy is code. Prompt is only instruction.

```python
# capabilities/transfer/policies.py

class TransferPolicy:
    async def ensure_transfer_allowed(
        self,
        *,
        user_id: str,
        amount: int,
    ) -> None:
        ...

    async def ensure_execution_allowed(
        self,
        *,
        user_id: str,
        preview_id: str,
    ) -> None:
        ...
```

```python
# capabilities/transfer/services.py

class TransferService:
    def __init__(self, policy: TransferPolicy):
        self.policy = policy

    async def create_preview(
        self,
        *,
        user_id: str,
        intent: TransferIntent,
    ) -> TransferPreview:
        await self.policy.ensure_transfer_allowed(
            user_id=user_id,
            amount=intent.amount,
        )

        ...
```

The model may help fill the form. The model must not become the source of permission.

## Output Mode Wisdom

Use structured output when backend code consumes the result.

Prefer native output or tool output when supported by the model.

Use prompted output only when the provider does not support stronger structured output modes or when quality is better for that case.

```python
from pydantic_ai import Agent, NativeOutput

agent = Agent(
    "openai:gpt-5.2",
    output_type=NativeOutput(
        BankingOutput,
        name="BankingOutput",
        description="Structured banking assistant output.",
    ),
)
```

If using output functions, do not also register the same function as a normal tool. That can confuse the model.

Use output validators for final output checks that may need to ask the model to retry.

```python
from pydantic_ai import ModelRetry, RunContext


@banking_agent.output_validator
async def validate_output(
    ctx: RunContext[BankingDeps],
    output: BankingOutput,
) -> BankingOutput:
    if output.type == "transfer_draft" and output.amount is None:
        raise ModelRetry("Transfer amount is required for a transfer draft.")
    return output
```

## Hooks Wisdom

Hooks are for lifecycle behavior, not domain business logic.

Use hooks for logging, telemetry, audit metadata, masking, metrics, request inspection, and tool call inspection.

```python
# shared/telemetry.py

from pydantic_ai import RunContext


async def log_before_model_request(ctx: RunContext):
    user_id = getattr(ctx.deps, "user_id", None)

    logger.info(
        "agent_model_request_started",
        extra={
            "user_id": user_id,
            "run_id": ctx.run_id,
            "run_step": ctx.run_step,
        },
    )
```

If a hook starts to know about balance, transfer amount, account ownership, approval, or role rules, move that logic into service or policy.

Hooks may live inside capabilities. Deferred capability hooks run only after that capability is loaded. If a rule must always run, put it in an always-on capability.

## Thinking Wisdom

Use Thinking capability for requests that benefit from deeper reasoning.

```python
from pydantic_ai import Agent
from pydantic_ai.capabilities import Thinking

agent = Agent(
    "anthropic:claude-opus-4-7",
    capabilities=[
        Thinking(effort="high"),
        transfer_capability,
    ],
)
```

Use thinking for hard planning, multi-step reasoning, and analytical tasks.

Do not enable high thinking everywhere. It can increase cost and latency.

Use lower effort for simple form filling, classification, and direct extraction.

Do not expose raw reasoning to users.

## HTTP Retry Wisdom

Use retrying HTTP clients for transient provider failures, rate limits, network timeouts, and server errors.

```python
# shared/http_client.py

from httpx import AsyncClient, HTTPStatusError
from tenacity import retry_if_exception_type, stop_after_attempt, wait_exponential

from pydantic_ai.retries import AsyncTenacityTransport, RetryConfig, wait_retry_after


def create_retrying_client() -> AsyncClient:
    def should_retry_status(response):
        if response.status_code in (429, 502, 503, 504):
            response.raise_for_status()

    transport = AsyncTenacityTransport(
        config=RetryConfig(
            retry=retry_if_exception_type((HTTPStatusError, ConnectionError)),
            wait=wait_retry_after(
                fallback_strategy=wait_exponential(multiplier=1, max=60),
                max_wait=300,
            ),
            stop=stop_after_attempt(5),
            reraise=True,
        ),
        validate_response=should_retry_status,
    )

    return AsyncClient(transport=transport)
```

Start conservative. Use 3 to 5 attempts. Use exponential backoff. Respect Retry-After headers. Monitor retries in production.

Retries add latency and cost. Excessive retries usually mean a systemic issue.

## Model Factory Wisdom

Keep model construction in one place.

```python
# shared/model_factory.py

from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from .http_client import create_retrying_client
from .settings import settings


def create_chat_model():
    client = create_retrying_client()

    return OpenAIChatModel(
        settings.default_model,
        provider=OpenAIProvider(http_client=client),
    )
```

Do not construct provider clients across many files.

## File Input Wisdom

Use ImageUrl, AudioUrl, VideoUrl, or DocumentUrl when sending file URLs to the model.

Use BinaryContent when the file is local or when you want the server to send bytes directly.

```python
from pathlib import Path

from pydantic_ai import Agent, BinaryContent

agent = Agent(model="anthropic:claude-sonnet-4-6")

result = agent.run_sync(
    [
        "What is the main content of this document?",
        BinaryContent(
            data=Path("document.pdf").read_bytes(),
            media_type="application/pdf",
        ),
    ]
)
```

Validate URL scheme and scope before constructing file URL parts from user input.

Do not allow untrusted users to pass arbitrary s3, gs, local, or internal URLs.

Use force_download=True only for safe http or https URLs when you want the server to download and send bytes.

Use UploadedFile when the file has already been uploaded to a provider file API.

Always set provider_name for UploadedFile.

```python
from pydantic_ai import Agent, UploadedFile

agent = Agent(model)

result = await agent.run(
    [
        "Summarize this document.",
        UploadedFile(
            file_id=uploaded_file.id,
            provider_name=model.system,
            media_type="application/pdf",
        ),
    ]
)
```

Provider-specific uploaded files are not portable across providers. If the message history may be reused with another provider, process or remove uploaded file parts before sending.

## Message History Wisdom

Message history is conversation state. Business state belongs in the application database.

```python
# agents/banking/runner.py

async def run_with_history(
    *,
    message: str,
    deps: BankingDeps,
    message_history: list | None = None,
):
    result = await banking_agent.run(
        message,
        deps=deps,
        message_history=message_history,
    )

    return result.output, result.all_messages()
```

Do not store unlimited message history. Long history increases cost, latency, and context pollution.

Use history processors when the message history needs pruning, masking, compaction, or provider-specific rewriting.

Do not store transfer draft, transfer preview, approval state, or receipt only in chat history. Store them in database tables.

## Direct Model Request Wisdom

Use direct model request when you do not need agent, dependencies, tools, capabilities, hooks, or long message history.

Direct requests are good for simple classification, extraction, summarization, and rewriting.

```python
# shared/direct_requests.py

from pydantic import BaseModel, Field


class IntentClassification(BaseModel):
    intent: str
    confidence: float = Field(ge=0, le=1)


async def classify_intent(model, text: str) -> IntentClassification:
    response = await model.request(
        prompt=f"Classify this user message: {text}",
        output_type=IntentClassification,
    )

    return response.output
```

Do not use an agent for every LLM call. Use an agent when you need instructions, dependencies, tools, capabilities, hooks, output validation, or message history.

## Agent Spec Wisdom

Use agent specs for declarative configuration. Do not hide business logic in specs.

```python
# agents/banking/specs.py

from pydantic import BaseModel, Field


class BankingAgentSpec(BaseModel):
    name: str
    model: str
    instructions_slug: str
    capability_ids: list[str] = Field(default_factory=list)


DEFAULT_BANKING_AGENT_SPEC = BankingAgentSpec(
    name="banking_agent",
    model="openai:gpt-5.2",
    instructions_slug="banking_agent_instructions",
    capability_ids=[
        "account_lookup",
        "transfer",
        "complaint",
    ],
)
```

Spec is for configuration such as model name, instruction slug, capability IDs, and runtime settings.

Logic remains in service, schema, tool, and capability.

## Performance Wisdom

Validate at boundaries. Do not repeatedly validate trusted internal objects in every layer.

Use model_validate for untrusted input.

Use model_construct only for trusted internal data that is already valid.

```python
intent = TransferIntent.model_validate(raw_payload)
```

Never use model_construct for user input, LLM output, external API payload, queue message, or file content.

## Integration Wisdom

Use Pydantic models as contracts for API request, API response, queue payload, database boundary, and tool arguments.

```python
class TransferCreatedEvent(BaseModel):
    transfer_id: str
    user_id: str
    amount: int
    status: str
```

Validate event payloads and queue messages like API payloads.

Do not send raw ORM objects to the agent. Convert them to safe Pydantic views.

```python
class AccountView(BaseModel):
    account_id: str
    account_name: str
    masked_account_number: str
```

The agent should not see password hashes, raw risk scores, internal metadata, or hidden database fields.

## Testing Wisdom

Test schema, service, tool, capability, and agent separately.

```python
# tests/capabilities/transfer/test_schemas.py

import pytest
from pydantic import ValidationError

from src.agentic_system.capabilities.transfer.schemas import TransferIntent


def test_transfer_intent_rejects_zero_amount():
    with pytest.raises(ValidationError):
        TransferIntent(
            source_account_id="acc-1",
            destination_account_number="1234567890",
            amount=0,
        )
```

```python
# tests/capabilities/transfer/test_services.py

async def test_create_preview_requires_confirmation(transfer_service):
    preview = await transfer_service.create_preview(
        intent=TransferIntent(
            source_account_id="acc-1",
            destination_account_number="1234567890",
            amount=100_000,
        ),
    )

    assert preview.requires_confirmation is True
```

```python
# tests/agents/banking/test_agent_output.py

async def test_agent_returns_clarification_when_amount_missing(fake_banking_deps):
    result = await banking_agent.run(
        "transfer ke rekening 1234567890",
        deps=fake_banking_deps,
    )

    assert result.output.type == "need_clarification"
```

Test behavior, not only prompt text.

Use agent override for tests when you need to replace model, deps, tools, toolsets, or instructions.

## Anti Patterns

Do not put business logic in agent.py.

Do not put database transaction logic in tools.py.

Do not use prompt as the security boundary.

Do not create a capability without a clear domain boundary.

Do not create a new agent for one small action.

Do not use free text output for backend-controlled flow.

Do not assume deps_type validates runtime deps.

Do not store unlimited chat history.

Do not use agent when direct model request is enough.

Do not use model_construct for untrusted data.

Do not send raw ORM objects to the agent.

Do not pass untrusted file URLs directly to model providers.

Do not enable high thinking for every request.

Do not retry forever.

## Preferred Coding Pattern

```text
agents/<name>/agent.py
  Composition root.

agents/<name>/deps.py
  Runtime dependencies.

agents/<name>/output.py
  Structured output contract.

agents/<name>/instructions.py
  Global agent boundary.

agents/<name>/runner.py
  Application entry point.

agents/<name>/specs.py
  Optional declarative config.

capabilities/<domain>/capability.py
  Capability packaging.

capabilities/<domain>/tools.py
  Thin LLM adapters.

capabilities/<domain>/schemas.py
  Pydantic contracts.

capabilities/<domain>/services.py
  Business logic.

capabilities/<domain>/instructions.py
  Domain-specific instructions.

capabilities/<domain>/policies.py
  Domain permission and safety rules.

shared/settings.py
  pydantic-settings config.

shared/validation.py
  TypeAdapter and validation helpers.

shared/serialization.py
  dump and JSON helpers.

shared/http_client.py
  retrying HTTP clients.

shared/model_factory.py
  model and provider construction.

shared/telemetry.py
  hooks and observability helpers.
```

## Final Wisdom

Write code as if the model can choose the wrong tool at any time.

If the wrong tool is called but the service remains safe, the design is correct.

If the prompt is ignored but policy still blocks dangerous actions, the design is correct.

If the model can be replaced without changing business logic, the design is correct.

If the service can be tested without an LLM, the design is correct.

If the agent output can be processed without parsing natural language, the design is correct.

If Pydantic schemas are used as boundaries between layers, the system becomes easier to test, audit, and extend.

---

# Development Wisdom

Rules given directly by the owner during this project. They apply to every file, not only the
agent layer.

## Naming Wisdom

A name must say what is *inside* the thing, not what role it plays in the architecture.

Umbrella names are the failure mode. `contracts.py`, `utils.py`, `helpers.py`, `base.py`,
`common.py`, `types.py`, `manager.py`, `handler.py` — each of these could be attached to five
different files without feeling wrong, which is exactly why none of them tells a reader
anything. "Contract" in particular is so broad it names nothing: every interface is a contract.

Use the test: **if the name would fit five unrelated files, it is too broad.**

```text
contracts.py   -> access_levels.py     # it defines who may reach which tool
errors.py      -> results.py           # it holds outcomes, not errors
```

Prefer the concrete noun the module is actually about. `identity_gate.py`, `message_store.py`,
`model_factory.py`, `transcript.py` all pass; they name their contents and nothing else.

The same applies to functions and classes. `Decision` inside `policies` is fine because the
surrounding namespace supplies the rest of the meaning; a bare `Manager` never is.

## Comment Wisdom

Comment only where the *why* is non-obvious. Never narrate what the code plainly does.

A comment earns its place by carrying one of four things: a rationale, an invariant, a
trade-off, or a contract at a boundary. Anything else is noise, and noise makes code dirty.

```python
# Bad -- restates the line beneath it.
# Get the customer from the database
customer = await db.customer_row(contact)

# Good -- carries a rationale the code cannot show.
# The threshold is applied to a number from the database. Had the amount been a tool
# argument, the model could have named one below the limit and walked under it.
```

Module docstrings: one or two sentences unless the module encodes a genuinely non-obvious
decision. Skip docstrings on `__init__`, thin delegations, and private helpers whose name
already says it.

A comment that is *wrong* is worse than none. Re-read comments when the code beneath them moves.

## Helper Wisdom

Do not create small helper functions that are not really needed.

A helper used exactly once is usually worse than the code inlined: it adds a name to learn and
a jump to follow, and buys nothing. Extract only when the code is used more than once, or when
the extraction genuinely names a concept.

Worse still is a helper that folds two meanings into one return value:

```python
# Bad -- returns lastrowid for inserts and rowcount for updates. One function, two meanings.
async def _write(self, sql, params) -> int: ...

# Good -- two names, each with one meaning.
async def _insert(self, sql, params) -> int: ...
async def _update(self, sql, params) -> bool: ...
```

## Essentialism Wisdom

Everything built must be essential and necessary. If a field, a layer, a setting, or a file
cannot be tied to a requirement it satisfies or a failure it prevents, delete it.

Applies especially to:

- **Model fields.** Two fields encoding one fact can disagree. Derive instead of storing —
  `success` is `code is OK`, not a second column.
- **Fields with a constant value.** A `status` that is always `"open"` at construction carries
  no information.
- **Data handed to the model.** A field the model never needs is prompt weight, and if it is a
  contact detail it is also PII in a trace.
- **Config knobs.** A setting nobody sets, or one whose alternate branch has only ever caused
  bugs, should be removed rather than documented.
- **Instrumentation.** If it emits nothing when measured, take it out.

## Frontend Wisdom

Keep the frontend as small as it can be while still demonstrating the system.

No build step and no framework unless one earns its place. One HTML file, plain fetch, and the
few elements needed to show what the backend does. A demo UI exists to make the agent legible;
every extra layer is surface that has to be maintained and that hides the thing being shown.

## Import Wisdom

No imports inside functions. Every import belongs at the top of the module.

A deferred import hides a dependency from anyone reading the file's head, makes the import
cost unpredictable, and turns a missing package into a runtime failure at the worst moment
instead of an error at startup. The usual excuses -- "it is optional", "it is slow to import",
"it avoids a cycle" -- are each a symptom: an optional dependency belongs behind a real
extras marker, a slow import belongs behind a factory, and a cycle means the seam is in the
wrong place.

```python
# Bad -- the module's real dependencies are invisible from the top.
def build_model(settings):
    from groq import AsyncGroq
    ...

# Good.
from groq import AsyncGroq

def build_model(settings):
    ...
```

Enforce it rather than remember it: ruff's `PLC0415`.

```toml
[tool.ruff.lint]
extend-select = ["I", "UP", "B", "PLC0415"]
```

## Verification Wisdom

Before you design on top of a framework's behaviour, go read that behaviour in the version that
is installed. Not the docs for the version you remember, and not your memory of the docs.

Ask, out loud, of every claim you are about to build on: **have I seen this happen, or do I only
believe it?** If the answer is belief, spend the two minutes.

```python
inspect.signature(Agent.run)          # what does it actually accept?
inspect.getdoc(Agent.run_stream_events)
grep -rn "'interrupted'" .venv/.../pydantic_ai/    # who writes this value, and when?
```

Three claims in this project looked obviously true and were not:

- `metadata=` on `agent.run` "attaches to the message". It reaches `RunContext.metadata`,
  `result.metadata`, and the `invoke_agent` span. `ModelMessage.metadata` stays `null`. A design
  that had put app data there would have shipped a column that is always empty.
- `state='interrupted'` "marks a run that died". The framework writes it when a *tool* is
  cancelled. A run whose model call raised still reads `complete`, so the check that mattered —
  does every tool call in this run have a return? — had to be written explicitly.
- `logfire.instrument_sqlite3` "instruments the database". It emitted zero spans, because
  `aiosqlite` runs `sqlite3` on a worker thread. Measured, then removed.

Each was caught by a five-line script or a failing test, and each would otherwise have become a
paragraph of confident documentation describing something that never happened. **A design note
asserting behaviour you did not observe is worse than no note: it stops the next person from
checking.**

## Seam Wisdom

Before writing machinery, look for the seam the library already offers. Read its public surface
end to end once — `dir(Agent)` is thirty seconds — and ask: **what problem was each of these
added to solve, and is one of them mine?**

The tell is that hand-rolled machinery usually exists to *undo* something the library did on
purpose, and the library almost always shipped the undo itself.

| Written by hand | The seam that already existed |
|---|---|
| `asyncio.Queue` + a background task + a sentinel, to escape a callback | `agent.run_stream_events` — wraps `run`, hands back an async iterator, ends with `AgentRunResultEvent` |
| A `model` parameter on `build_agent`, used only by tests | `agent.override(model=...)` — the framework's own test seam |
| A trailing-window clause inside the load query | `ProcessHistory(processor)` — a capability, where a prompting decision belongs |
| `dump_json().decode()` / `validate_json()` around a `TEXT` column | `TypeDecorator` binding a `TypeAdapter` to `JSONB`, so validation happens at the column |
| A `Database` class wrapping a driver, plus `schema.sql` | SQLAlchemy: `Base.metadata` *is* the schema; `session_scope` *is* the transaction |

Every row on the left was working code with tests passing. Working is not the bar. The bar is
that a person who knows the library can read your file and recognise it. **A private interface
over a public one costs every future reader the difference.**

The counter-question keeps this honest: *is the framework's seam actually a fit, or am I
contorting my problem to reach it?* `Agent.to_web()` exists and was not used, because the UI has
its own identity model and Indonesian activity labels. Reaching for a seam you have to fight is
the same mistake in the other direction.

## Placement Wisdom

Most design errors are not wrong logic. They are correct logic in the wrong layer, where nothing
disagrees with it and no test names it.

Ask of any rule you are about to write: **whose decision is this, and would that owner recognise
it here?**

- Trimming history to the last twelve runs sat in the store's `SELECT`. It is a *prompting*
  decision — what the model is allowed to see — living inside persistence. Moved to a capability,
  the store went back to being the audit record and the agent got to own its own context window.
- `get_customer` used to set `ctx.deps.customer`. That is a domain tool granting its own session
  a privilege. Moved into the identity gate's `after_tool_execute`, where a security decision is
  reviewed as one.
- The refund ceiling reads the amount from `order_items`. Taking it as a tool argument would let
  the guarded party choose the number the guard checks.

The smell is a layer that has to *know* something outside its job to be correct.

## Reversal Wisdom

When you reverse a decision, the valuable part of the record is not the new choice. It is **why
the original argument was wrong** — because that argument will be made again.

`SQLAlchemy` was rejected here with a reasonable-sounding case: only ~10 queries, and connection
pooling is meaningless against a local file. Both facts were true and the conclusion was still
wrong, because the argument was about *query volume* and the real cost was *interface
familiarity* and a schema declared in two places that could drift apart. Writing only "we now use
SQLAlchemy" would have preserved the mistake and thrown away the lesson.

So a reversal entry carries three things: the original reasoning, the fact that broke it, and
what the original reasoning was measuring instead of what mattered. Mark it (`⟲`) rather than
deleting the old row. **A decision log that only shows decisions that survived is a log of
hindsight, not of thinking.**

## Cost Wisdom

Every decision buys something and spends something. Write down the part it spends, in the place
the spending will be felt.

Moving from a hand-rolled `Database` to SQLAlchemy sessions gave up a real guarantee: the old
class had no unscoped method, so cross-customer reads were *unreachable*, not merely absent. A
service holding an `AsyncSession` can write `select()` with no `WHERE customer_id`. That is now
a convention.

The honest response is not to hide it and not to abandon the move. It is to say so in the
section that claims the guarantee, and to replace structure with a test that fails if the
convention is broken.

Ask: **what did this make possible that was impossible before — and what did it make possible
that used to be impossible on purpose?**

## Omission Wisdom

What a schema leaves out is part of its behaviour.

`Customer` carries `customer_id` and `full_name`. It does not carry `email` or `phone`, and that
absence is the mechanism that keeps a contact detail out of the transcript, out of the model's
context, and out of a trace — with no redaction step to remember and no rule to enforce.

This is why the tool-facing models are not the ORM rows and must not be merged with them. The
temptation is real: `SQLModel` unifies them and removes an apparent duplication. Here it would
also have deleted a security property. **Two models that look alike are not duplication if one of
them is defined by what it refuses to include.**

Ask of each field you add to a model the agent sees: *what does the customer gain from the model
knowing this, and what happens when it appears in a log?*

## Derivation Wisdom

Prefer a fact the runtime already holds over the same fact restated by the model. A restatement
can disagree; a derivation cannot.

`escalated` and `ticket_id` are read from the transcript — did `escalate_ticket` run, what did
`create_ticket` return — rather than asked for in the output schema. The model cannot claim it
escalated when it did not, and cannot forget to mention that it did. It also removed four fields
the model had to fill in, which measurably improved the case that mattered most.

The general question: **is this something the system knows, or only something the model says?**
If the system knows it, asking the model is adding a way to be wrong.

## One Name One Meaning Wisdom

Two classes named `Turn` existed in this codebase at once: one was an exchange in a transcript
(`role`, `text`, `tools`), the other the working set assembled before a run (`store`, `history`,
`deps`, `metadata`). Both were locally sensible. Together they made "the turn" ambiguous in every
conversation about the code.

A name is not chosen against its own module. It is chosen against every other use of that word in
the system. **If the word already means something here, either reuse it exactly or pick another
word.**

## Frontend Wisdom (revised)

⟲ The rule above — no build step, no framework unless one earns its place — was written before
streaming. It still holds; the earning happened. Token-by-token rendering with incremental
Markdown, and tool activity interleaved with text, is a state-synchronisation problem, and hand
-rolled DOM updates for it are more code and more bugs than a component tree.

The test did not change: *what is the smallest thing that makes the system legible?* Only the
answer did, and it changed because the requirement did. **When a rule stops fitting, say which
requirement moved — an unexplained exception is how rules quietly stop being followed.**
