from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field


class ModelsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    executor: str = Field(description="Model ID for the executor agent.")
    diagnostician: str = Field(description="Model ID for the diagnostician agent.")
    builder: str = Field(description="Model ID for the builder agent.")
    verifier: str | None = Field(
        default=None,
        description="Model ID for the verifier if ever made non-deterministic.",
    )


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
    models: ModelsConfig = Field(description="Model configuration by agent role.")
    limits: LimitsConfig = Field(default_factory=LimitsConfig)
    static_tools: list[str] = Field(description="Static tool identifiers to preload.")
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    cost: CostConfig = Field(default_factory=CostConfig)


def load_cell_config(path: str | Path) -> CellConfig:
    raw = yaml.safe_load(Path(path).read_text()) or {}
    return CellConfig.model_validate(raw)


def load_cell_config_data(data: dict[str, Any]) -> CellConfig:
    return CellConfig.model_validate(data)
