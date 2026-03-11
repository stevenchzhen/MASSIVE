from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from cell.models.base import ModelAdapter


class AgentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payload: dict[str, Any] = Field(description="Role-specific structured payload.")
    tools: list[str] = Field(default_factory=list, description="Available tool identifiers.")
    context_window: str = Field(description="Scoped context available to the agent.")
    config: dict[str, Any] = Field(default_factory=dict, description="Agent configuration.")


class AgentOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = Field(description='Outcome status: "complete", "blocker", or "error".')
    payload: dict[str, Any] = Field(description="Role-specific structured output payload.")
    reasoning_trace: str = Field(description="Raw response trace for audit logging.")
    token_usage: dict[str, int] = Field(description="Token usage in {input, output} form.")
    model_id: str = Field(description="Actual model identifier used.")
    latency_ms: int = Field(ge=0, description="Wall-clock latency in milliseconds.")
    cost_usd: float = Field(ge=0.0, description="Estimated cost in USD.")


class Agent(ABC):
    def __init__(self, model: ModelAdapter):
        self.model = model

    @abstractmethod
    async def invoke(self, input: AgentInput) -> AgentOutput:
        raise NotImplementedError

