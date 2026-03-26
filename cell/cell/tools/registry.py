from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any, Callable

from cell.tools.sandbox import Sandbox
from cell.types import TestCase, ToolArtifact, ToolDescription, ToolSpec


@dataclass(frozen=True)
class StaticTool:
    tool_id: str
    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    func: Callable[..., Any]
    entry_point: str


@dataclass(frozen=True)
class ToolPackage:
    artifact: ToolArtifact
    spec: ToolSpec
    origin: str


class ToolRegistry:
    """Manages static, shared dynamic, and public tools."""

    _shared_dynamic: dict[str, ToolPackage] = {}
    _public_library: dict[str, ToolPackage] = {}

    def __init__(self, static_tools: list[str]):
        self._static: dict[str, StaticTool] = {}
        self._load_static(static_tools)

    def _load_static(self, static_tools: list[str]) -> None:
        for tool_id in static_tools:
            try:
                module = importlib.import_module(f"cell.tools.static.{tool_id}")
            except ModuleNotFoundError:
                if tool_id in self._shared_dynamic or tool_id in self._public_library:
                    continue
                raise
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
        return self.describe_available()

    def describe_available(self, tool_ids: list[str] | None = None) -> list[ToolDescription]:
        selected = set(tool_ids) if tool_ids is not None else None
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
            if selected is None or tool.tool_id in selected
        ]
        descriptions.extend(
            ToolDescription(
                tool_id=package.artifact.name,
                name=package.artifact.name,
                description=package.spec.description,
                input_schema=package.spec.input_schema,
                output_schema=package.spec.output_schema,
                is_dynamic=True,
            )
            for package in self._shared_dynamic.values()
            if selected is None or package.artifact.name in selected
        )
        return descriptions

    def register_dynamic(self, artifact: ToolArtifact, spec: ToolSpec | None = None) -> str:
        package = ToolPackage(
            artifact=artifact,
            spec=spec
            or ToolSpec(
                name=artifact.name,
                description=f"Dynamically built tool {artifact.name}",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
                test_cases=_placeholder_cases(),
                edge_cases=_placeholder_edge_cases(),
                constraints=["pure"],
            ),
            origin="dynamic",
        )
        self._shared_dynamic[artifact.name] = package
        return artifact.name

    def get(self, tool_id: str) -> StaticTool | ToolArtifact:
        if tool_id in self._static:
            return self._static[tool_id]
        if tool_id in self._shared_dynamic:
            return self._shared_dynamic[tool_id].artifact
        raise KeyError(f"Unknown tool: {tool_id}")

    def get_package(self, tool_id: str) -> ToolPackage | None:
        if tool_id in self._shared_dynamic:
            return self._shared_dynamic[tool_id]
        if tool_id in self._public_library:
            return self._public_library[tool_id]
        return None

    def is_local_tool(self, tool_id: str) -> bool:
        return tool_id in self._static or tool_id in self._shared_dynamic

    async def execute(self, tool_id: str, arguments: dict[str, Any], sandbox: Sandbox) -> Any:
        if tool_id in self._static:
            return self._static[tool_id].func(**arguments)
        package = self.get_package(tool_id)
        if package is None:
            raise KeyError(f"Unknown tool: {tool_id}")
        return await sandbox.execute(package.artifact, arguments)

    @classmethod
    def register_public_package(cls, tool_id: str, artifact: ToolArtifact, spec: ToolSpec) -> None:
        cls._public_library[tool_id] = ToolPackage(artifact=artifact, spec=spec, origin="public")

    @classmethod
    def install_public_package(cls, tool_id: str) -> ToolPackage:
        if tool_id not in cls._public_library:
            raise KeyError(f"Unknown public tool: {tool_id}")
        package = cls._public_library[tool_id]
        cls._shared_dynamic[package.artifact.name] = ToolPackage(
            artifact=package.artifact,
            spec=package.spec,
            origin="installed_public",
        )
        return cls._shared_dynamic[package.artifact.name]


def _placeholder_cases() -> list[TestCase]:
    return [
        TestCase(description="placeholder-one", input={}, expected_output={}),
        TestCase(description="placeholder-two", input={}, expected_output={}),
        TestCase(description="placeholder-three", input={}, expected_output={}),
    ]


def _placeholder_edge_cases() -> list[TestCase]:
    return [
        TestCase(description="placeholder-edge-one", input={}, expected_output={}),
        TestCase(description="placeholder-edge-two", input={}, expected_output={}),
    ]
