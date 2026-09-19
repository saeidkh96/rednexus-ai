import hashlib
import json
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from jsonschema import Draft202012Validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class CapabilitySpec(Contract):
    name: str = Field(pattern=r"^[a-z][a-z0-9_.]{2,100}$")
    project: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,60}$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    description: str = Field(max_length=500)
    mode: Literal["demo", "http", "disabled"] = "disabled"
    protocol: Literal["nexus", "redworld_v140", "redworld_v200", "redpulse_v400", "redguard_v100", "redforge_v161", "redpa_v191"] = "nexus"
    workspace_binding: str | None = None
    resource_binding: str | None = Field(default=None, min_length=1, max_length=1000)
    effect: Literal["read", "propose", "write"] = "read"
    approval: bool = False
    endpoint: str | None = None
    health_endpoint: str | None = None
    credential_env: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]*$")
    timeout_seconds: int = Field(default=20, ge=1, le=60)
    max_attempts: int = Field(default=2, ge=1, le=4)
    estimated_cost_microunits: int = Field(default=0, ge=0, le=1000000000)
    input_schema: dict = Field(default_factory=lambda: {"type": "object"})
    output_schema: dict = Field(default_factory=lambda: {"type": "object"})

    @model_validator(mode="after")
    def valid(self):
        Draft202012Validator.check_schema(self.input_schema)
        Draft202012Validator.check_schema(self.output_schema)
        for schema in [self.input_schema, self.output_schema]:
            # Schemas are local contracts. Never fetch remote refs during validation.
            if '"$ref"' in canonical(schema):
                raise ValueError("schema references are not supported; inline schemas")
        if self.effect != "read" and not self.approval:
            raise ValueError("proposal/write capabilities must require approval")
        if self.mode == "http" and not self.endpoint:
            raise ValueError("HTTP capability requires an explicit endpoint")
        if self.protocol in ("redworld_v140", "redworld_v200"):
            if not self.workspace_binding or self.project != "redworld":
                raise ValueError("RedWorld requires a fixed workspace binding")
            expected = {"redworld.snapshot": "read", "redworld.advance": "write"}
            if self.name not in expected or self.effect != expected[self.name]:
                raise ValueError("RedWorld capability/effect mismatch")
            if self.mode == "http" and not self.endpoint.rstrip("/").endswith("/api/v1/world"):
                raise ValueError("RedWorld endpoint must end in /api/v1/world")
        if self.protocol not in ("nexus", "redworld_v140", "redworld_v200"):
            from rednexus.integrations.native import validate_native_spec
            validate_native_spec(self)
        return self


class OutputBinding(Contract):
    step: int = Field(ge=0, le=19)
    pointer: str = Field(default="", max_length=500, pattern=r"^(|/.*)$")
    format: Literal["value", "json"] = "value"


class Condition(OutputBinding):
    op: Literal["eq", "ne", "gt", "gte", "lt", "lte", "exists"] = "eq"
    value: Any = None


class StepInput(Contract):
    capability: str
    input: dict[str, Any] = Field(default_factory=dict)
    use_previous: bool = False
    bindings: dict[str, OutputBinding] = Field(default_factory=dict, max_length=50)
    when: Condition | None = None


class RunInput(Contract):
    title: str = Field(min_length=1, max_length=200)
    steps: list[StepInput] = Field(min_length=1, max_length=20)
    budget_microunits: int = Field(default=1000000, ge=0, le=1000000000)
    max_tool_calls: int = Field(default=20, ge=1, le=80)
    deadline_seconds: int = Field(default=3600, ge=10, le=86400)

    @model_validator(mode="after")
    def size(self):
        if len(canonical(self.model_dump()).encode()) > 65536:
            raise ValueError("workflow exceeds 64 KiB")
        for index, step in enumerate(self.steps):
            references = list(step.bindings.values()) + ([step.when] if step.when else [])
            if any(ref.step >= index for ref in references):
                raise ValueError("bindings and conditions must reference earlier steps")
            if any(not key or len(key) > 100 or key in step.input for key in step.bindings):
                raise ValueError("binding targets must be nonempty unique top-level input fields")
            if step.use_previous and "previous" in step.bindings:
                raise ValueError("previous cannot also be a binding target")
        return self


class LoginInput(Contract):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)
    workspace: str = Field(min_length=1, max_length=80)


class UserInput(Contract):
    username: str = Field(pattern=r"^[a-zA-Z0-9_.@-]{3,80}$")
    password: str = Field(min_length=12, max_length=256)
    role: Literal["admin", "operator", "reviewer", "viewer"]
    grants: list[str] = Field(default_factory=list, max_length=100)
    kind: Literal["human", "service"] = "human"


class AccessInput(Contract):
    role: Literal["admin", "operator", "reviewer", "viewer"]
    grants: list[str] = Field(default_factory=list, max_length=100)
    enabled: bool = True


class ReviewInput(Contract):
    allow: bool
    digest: str = Field(min_length=64, max_length=64)
    reason: str = Field(min_length=1, max_length=1000)


class MemoryInput(Contract):
    namespace: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,60}$")
    key: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=16000)
    source: str = Field(min_length=1, max_length=1000)
    ttl_seconds: int = Field(default=604800, ge=60, le=31536000)


class AgentInput(Contract):
    name: str = Field(min_length=1, max_length=100)
    capabilities: list[str] = Field(min_length=1, max_length=20)
    strategy: Literal["ordered", "model"] = "ordered"
    budget_microunits: int = Field(default=1000000, ge=0, le=1000000000)


class PlanInput(Contract):
    objective: str = Field(min_length=1, max_length=4000)


class EventInput(Contract):
    id: str = Field(min_length=1, max_length=100)
    source: str = Field(min_length=1, max_length=200)
    type: str = Field(pattern=r"^[a-zA-Z0-9_.-]{3,200}$")
    data: dict = Field(default_factory=dict)

    @field_validator("data")
    @classmethod
    def data_size(cls, value):
        if len(canonical(value).encode()) > 65536:
            raise ValueError("event data too large")
        return value


class RuleInput(Contract):
    event_type: str = Field(min_length=1, max_length=200)
    source: str = Field(min_length=1, max_length=200)
    producer_id: str
    workflow: RunInput


class ReconcileInput(Contract):
    outcome: Literal["confirmed_succeeded", "confirmed_failed", "abandon"]
    evidence: str = Field(min_length=10, max_length=4000)
    output: dict = Field(default_factory=dict)
