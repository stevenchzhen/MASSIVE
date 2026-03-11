from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CompletionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(description="Model response content.")
    tokens_in: int = Field(ge=0, description="Prompt token count.")
    tokens_out: int = Field(ge=0, description="Completion token count.")
    model: str = Field(description="Provider-specific model identifier.")
    latency_ms: int = Field(ge=0, description="Latency in milliseconds.")
    cost_usd: float = Field(ge=0.0, description="Estimated completion cost in USD.")


class ModelAdapter(ABC):
    @abstractmethod
    async def complete(
        self,
        messages: list[dict[str, Any]],
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        response_format: dict[str, Any] | None = None,
    ) -> CompletionResult:
        raise NotImplementedError


def parse_json_content(content: str) -> dict[str, Any]:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1 or start >= end:
            raise
        return json.loads(content[start : end + 1])

