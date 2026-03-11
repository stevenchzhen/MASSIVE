from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class CellState(str, Enum):
    INITIALIZING = "initializing"
    EXECUTING = "executing"
    DIAGNOSING = "diagnosing"
    BUILDING = "building"
    VERIFYING = "verifying"
    WAIT_HUMAN = "wait_human"
    COMPLETE = "complete"
    ESCALATED = "escalated"
    TOOL_FAILED = "tool_failed"
    ERROR = "error"


class MessageType(str, Enum):
    TASK_INPUT = "task_input"
    VERDICT = "verdict"
    BLOCKER = "blocker"
    TOOL_SPEC = "tool_spec"
    CONTEXT_REQUEST = "context_request"
    ESCALATION = "escalation"
    TOOL_ARTIFACT = "tool_artifact"
    TOOL_VERDICT = "tool_verdict"
    TOOL_READY = "tool_ready"
    TOOL_BUILD_RETRY = "tool_build_retry"


class BlockerCategory(str, Enum):
    MISSING_CAPABILITY = "missing_capability"
    INSUFFICIENT_CONTEXT = "insufficient_context"
    AMBIGUOUS_INSTRUCTION = "ambiguous_instruction"
    IMPOSSIBILITY = "impossibility"


class VerdictType(str, Enum):
    CONCLUSIVE = "conclusive"
    QUALIFIED = "qualified"
    INCONCLUSIVE = "inconclusive"


class AgentRole(str, Enum):
    EXECUTOR = "executor"
    DIAGNOSTICIAN = "diagnostician"
    BUILDER = "builder"
    VERIFIER = "verifier"
    RUNTIME = "runtime"


class TaskInput(FrozenModel):
    task_id: str = Field(description="Unique task identifier.")
    scope: str = Field(description="Scoped task instruction for this cell.")
    context: str = Field(description="Context window provided to the cell.")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary task metadata for tracing and downstream use.",
    )


class TestCase(FrozenModel):
    case_id: str = Field(
        default_factory=lambda: f"tc_{uuid4().hex[:12]}",
        description="Unique test-case identifier.",
    )
    description: str = Field(description="Human-readable description of the case.")
    input: dict[str, Any] = Field(description="Keyword arguments supplied to the tool.")
    expected_output: Any = Field(description="Expected output value from the tool.")


TestCase.__test__ = False


class Blocker(FrozenModel):
    blocker_id: str = Field(
        default_factory=lambda: f"blk_{uuid4().hex[:12]}",
        description="Unique blocker identifier.",
    )
    category: BlockerCategory = Field(description="Root-cause category for the blocker.")
    description: str = Field(description="Detailed description of the blocker.")
    attempted_approaches: list[str] = Field(
        min_length=1,
        description="Approaches already attempted before blocking.",
    )
    what_would_unblock: str = Field(description="Concrete action that would unblock execution.")
    input_sample: str | None = Field(
        default=None,
        description="Optional sample input that reproduces the blocker.",
    )
    confidence_in_diagnosis: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score in the blocker diagnosis.",
    )


class ToolSpec(FrozenModel):
    spec_id: str = Field(
        default_factory=lambda: f"spec_{uuid4().hex[:12]}",
        description="Unique tool specification identifier.",
    )
    name: str = Field(description="Stable tool name.")
    description: str = Field(description="Detailed tool behavior description.")
    input_schema: dict[str, Any] = Field(description="JSON Schema describing tool inputs.")
    output_schema: dict[str, Any] = Field(description="JSON Schema describing tool outputs.")
    test_cases: list[TestCase] = Field(description="Nominal behavioral test cases.")
    edge_cases: list[TestCase] = Field(description="Edge-case and boundary-condition tests.")
    constraints: list[str] = Field(
        default_factory=list,
        description="Additional operational or behavioral constraints.",
    )

    @field_validator("test_cases")
    @classmethod
    def validate_test_cases(cls, value: list[TestCase]) -> list[TestCase]:
        if len(value) < 3:
            raise ValueError("ToolSpec requires at least 3 test_cases")
        return value

    @field_validator("edge_cases")
    @classmethod
    def validate_edge_cases(cls, value: list[TestCase]) -> list[TestCase]:
        if len(value) < 2:
            raise ValueError("ToolSpec requires at least 2 edge_cases")
        return value


class ToolArtifact(FrozenModel):
    artifact_id: str = Field(
        default_factory=lambda: f"art_{uuid4().hex[:12]}",
        description="Unique tool artifact identifier.",
    )
    spec_id: str = Field(description="ToolSpec identifier used to create this artifact.")
    name: str = Field(description="Tool name implemented by the artifact.")
    entry_point: str = Field(description="Function name that should be invoked.")
    source_code: str = Field(description="Python source code implementing the tool.")
    created_at: datetime = Field(
        default_factory=utc_now,
        description="Artifact creation timestamp in UTC.",
    )


class VerificationResult(FrozenModel):
    check_name: str = Field(description="Name of the verification step.")
    passed: bool = Field(description="Whether the verification step passed.")
    details: str = Field(description="Human-readable outcome details.")
    observed_output: Any | None = Field(
        default=None,
        description="Observed output or diagnostic data when available.",
    )


class ToolVerdict(FrozenModel):
    verdict_id: str = Field(
        default_factory=lambda: f"ver_{uuid4().hex[:12]}",
        description="Unique tool-verdict identifier.",
    )
    artifact_id: str = Field(description="Verified artifact identifier.")
    spec_id: str = Field(description="Tool specification identifier.")
    passed: bool = Field(description="Whether the artifact passed verification.")
    results: list[VerificationResult] = Field(
        default_factory=list,
        description="Individual verification step results.",
    )
    failure_report: str | None = Field(
        default=None,
        description="Concise failure report for builder retries.",
    )


class EvidenceItem(FrozenModel):
    evidence_id: str = Field(
        default_factory=lambda: f"ev_{uuid4().hex[:12]}",
        description="Unique evidence item identifier.",
    )
    summary: str = Field(description="Short summary of the evidence.")
    content: dict[str, Any] = Field(description="Structured evidence payload.")
    source: str = Field(description="Origin of the evidence item.")
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score for the evidence item.",
    )


class CellMessage(FrozenModel):
    id: str = Field(
        default_factory=lambda: f"msg_{uuid4().hex[:12]}",
        description="Unique message identifier.",
    )
    timestamp: datetime = Field(
        default_factory=utc_now,
        description="Message creation timestamp in UTC.",
    )
    source_agent: AgentRole = Field(description="Agent that emitted the message.")
    target_agent: AgentRole = Field(description="Intended message recipient.")
    message_type: MessageType = Field(description="Typed message category.")
    payload: dict[str, Any] = Field(description="Structured message payload.")
    correlation_id: str = Field(description="Correlation identifier for a workflow cycle.")


class EventLogEntry(FrozenModel):
    timestamp: datetime = Field(description="Event timestamp in UTC.")
    cell_id: str = Field(description="Cell identifier.")
    task_id: str = Field(description="Task identifier.")
    event: str = Field(description="Event kind, such as message or state_transition.")
    agent: AgentRole = Field(description="Agent or runtime associated with the event.")
    message_type: MessageType | None = Field(
        default=None,
        description="Message type for message events.",
    )
    payload_summary: dict[str, Any] = Field(
        default_factory=dict,
        description="Summarized event payload for logging and audit.",
    )
    correlation_id: str | None = Field(
        default=None,
        description="Correlation identifier for grouped events.",
    )
    state: CellState | None = Field(
        default=None,
        description="State reached during a state-transition event.",
    )


class ToolDescription(FrozenModel):
    tool_id: str = Field(description="Tool identifier.")
    name: str = Field(description="Human-readable tool name.")
    description: str = Field(description="Tool description for prompting.")
    input_schema: dict[str, Any] = Field(description="JSON Schema describing tool inputs.")
    output_schema: dict[str, Any] = Field(description="JSON Schema describing tool outputs.")
    is_dynamic: bool = Field(description="Whether the tool was created dynamically.")


class CellOutputEnvelope(FrozenModel):
    cell_id: str = Field(description="Cell identifier.")
    task_id: str = Field(description="Task identifier.")
    timestamp: datetime = Field(description="Envelope creation timestamp in UTC.")
    verdict: dict[str, Any] = Field(description="Structured verdict payload.")
    confidence: float = Field(ge=0.0, le=1.0, description="Overall verdict confidence.")
    verdict_type: VerdictType = Field(description="Verdict qualification category.")
    evidence: list[EvidenceItem] = Field(description="Evidence supporting the verdict.")
    reasoning_summary: str = Field(description="Short reasoning summary for audit consumers.")
    assumptions: list[str] = Field(description="Assumptions made during execution.")
    tools_used: list[str] = Field(description="Identifiers of tools used during execution.")
    dynamic_tools_created: list[str] = Field(
        description="Identifiers of dynamic tools created during execution.",
    )
    model_id: str = Field(description="Primary model identifier used for the task.")
    blockers_encountered: int = Field(
        ge=0,
        description="Number of blockers encountered during execution.",
    )
    retries: int = Field(ge=0, description="Total retry count across the workflow.")
    total_latency_ms: int = Field(ge=0, description="Aggregate end-to-end latency.")
    total_tokens: dict[str, int] = Field(
        description="Aggregate token counts, typically input/output totals.",
    )
    total_cost_usd: float = Field(ge=0.0, description="Total estimated model cost in USD.")
    event_log_ref: str = Field(description="Reference to the append-only event log.")
    state_transitions: list[str] = Field(description="Ordered state transition trace.")


    @field_validator("total_tokens")
    @classmethod
    def validate_total_tokens(cls, value: dict[str, int]) -> dict[str, int]:
        required = {"input", "output"}
        if not required.issubset(value):
            raise ValueError("total_tokens must include input and output keys")
        return value


    @model_validator(mode="after")
    def validate_evidence_confidence(self) -> "CellOutputEnvelope":
        if self.evidence and self.confidence == 0:
            raise ValueError("confidence must be > 0 when evidence is present")
        return self
