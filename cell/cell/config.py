from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from cell.types import Topology


class LegacyModelsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    executor: str = Field(description="Model ID for the executor agent.")
    diagnostician: str = Field(description="Model ID for the diagnostician agent.")
    builder: str = Field(description="Model ID for the builder agent.")
    verifier: str | None = Field(
        default=None,
        description="Model ID for the verifier if ever made non-deterministic.",
    )


class AgentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    model: str | None = Field(default=None, description="Model identifier for the agent.")
    additional_instructions: str = Field(
        default="",
        description="Optional extra role instructions.",
    )
    confidence_threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Threshold below which the executor must block.",
    )


class AgentsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    executor: AgentConfig
    diagnostician: AgentConfig | None = None
    builder: AgentConfig | None = None
    verifier: AgentConfig | None = None
    diagnostician_builder: AgentConfig | None = None
    builder_verifier: AgentConfig | None = None


class LimitsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_execution_retries: int = Field(default=3, ge=0)
    max_tool_build_retries: int = Field(default=2, ge=0)
    max_blockers_per_task: int = Field(default=5, ge=0)
    execution_timeout_sec: int = Field(default=300, ge=1)
    build_timeout_sec: int = Field(default=120, ge=1)
    verify_timeout_sec: int = Field(default=60, ge=1)
    total_cell_timeout_sec: int = Field(default=1800, ge=1)


class SandboxConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_execution_time_sec: int = Field(default=30, ge=1)
    max_memory_mb: int = Field(default=256, ge=16)
    allowed_imports: list[str] = Field(
        default_factory=lambda: [
            "math",
            "json",
            "re",
            "datetime",
            "decimal",
            "collections",
            "statistics",
            "itertools",
            "functools",
            "typing",
            "fractions",
        ]
    )


class CostConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    budget_usd: float = Field(default=5.0, ge=0.0)
    alert_threshold_usd: float = Field(default=3.0, ge=0.0)


class CellConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cell_id: str = Field(description="Unique cell identifier.")
    version: str = Field(description="Cell implementation version.")
    topology: Topology = Field(default=Topology.HIGH_TRUST)
    agents: AgentsConfig | None = Field(
        default=None,
        description="Agent topology and model configuration.",
    )
    models: LegacyModelsConfig | None = Field(
        default=None,
        description="Backward-compatible legacy model configuration.",
    )
    limits: LimitsConfig = Field(default_factory=LimitsConfig)
    static_tools: list[str] = Field(description="Static tool identifiers to preload.")
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    cost: CostConfig = Field(default_factory=CostConfig)

    @model_validator(mode="after")
    def normalize_agents(self) -> "CellConfig":
        if self.agents is not None:
            return self
        if self.models is None:
            raise ValueError("Either agents or models must be configured")
        object.__setattr__(
            self,
            "agents",
            AgentsConfig(
                executor=AgentConfig(model=self.models.executor),
                diagnostician=AgentConfig(model=self.models.diagnostician),
                builder=AgentConfig(model=self.models.builder),
                verifier=AgentConfig(model=self.models.verifier),
            ),
        )
        return self

    def agent(self, role: str) -> AgentConfig:
        agent = getattr(self.agents, role)
        if agent is None:
            raise KeyError(f"Agent role {role!r} is not configured for topology {self.topology.value}")
        return agent

    def planner_role(self) -> str:
        if self.topology == Topology.HIGH_TRUST:
            return "diagnostician"
        if self.topology == Topology.STANDARD:
            return "diagnostician_builder"
        return "builder_verifier"

    def builder_role(self) -> str:
        if self.topology == Topology.HIGH_TRUST:
            return "builder"
        if self.topology == Topology.STANDARD:
            return "diagnostician_builder"
        return "builder_verifier"


def load_cell_config(path: str | Path) -> CellConfig:
    raw = yaml.safe_load(Path(path).read_text()) or {}
    return CellConfig.model_validate(raw)


def load_cell_config_data(data: dict[str, Any]) -> CellConfig:
    return CellConfig.model_validate(data)
