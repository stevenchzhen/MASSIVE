from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any, Callable

from cell.types import ToolArtifact, ToolDescription


@dataclass(frozen=True)
class StaticTool:
    tool_id: str
    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    func: Callable[..., Any]
    entry_point: str


class ToolRegistry:
    """Manages static (pre-verified) and dynamic (runtime-built) tools."""

    def __init__(self, static_tools: list[str]):
        self._static: dict[str, StaticTool] = {}
        self._dynamic: dict[str, ToolArtifact] = {}
        self._load_static(static_tools)

    def _load_static(self, static_tools: list[str]) -> None:
        for tool_id in static_tools:
            module = importlib.import_module(f"cell.tools.static.{tool_id}")
            entry_point = getattr(module, "ENTRY_POINT", tool_id)
            self._static[tool_id] = StaticTool(
                tool_id=getattr(module, "TOOL_ID"),
                name=getattr(module, "TOOL_ID"),
                description=getattr(module, "DESCRIPTION"),
                input_schema=getattr(module, "INPUT_SCHEMA"),
                output_schema=getattr(module, "OUTPUT_SCHEMA"),
                func=getattr(module, entry_point),
                entry_point=entry_point,
            )

    def list(self) -> list[ToolDescription]:
        descriptions = [
            ToolDescription(
                tool_id=tool.tool_id,
                name=tool.name,
                description=tool.description,
                input_schema=tool.input_schema,
                output_schema=tool.output_schema,
                is_dynamic=False,
            )
            for tool in self._static.values()
        ]
        descriptions.extend(
            ToolDescription(
                tool_id=artifact.name,
                name=artifact.name,
                description=f"Dynamically built tool {artifact.name}",
                input_schema={},
                output_schema={},
                is_dynamic=True,
            )
            for artifact in self._dynamic.values()
        )
        return descriptions

    def register_dynamic(self, artifact: ToolArtifact) -> str:
        self._dynamic[artifact.name] = artifact
        return artifact.name

    def get(self, tool_id: str) -> StaticTool | ToolArtifact:
        if tool_id in self._static:
            return self._static[tool_id]
        if tool_id in self._dynamic:
            return self._dynamic[tool_id]
        raise KeyError(f"Unknown tool: {tool_id}")

