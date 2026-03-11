from __future__ import annotations

from temporalio import activity

from cell.agents.base import AgentInput
from cell.agents.builder import BuilderAgent
from cell.agents.diagnostician import DiagnosticianAgent
from cell.agents.executor import ExecutorAgent
from cell.agents.verifier import VerifierAgent
from cell.models import create_adapter
from cell.tools.registry import ToolRegistry
from cell.tools.sandbox import Sandbox, SandboxPolicy
from cell.types import ToolArtifact, ToolSpec


@activity.defn(name="run_executor")
async def run_executor(task_input: dict, tools: list[str], model_config: dict | str, context: str) -> dict:
    adapter = create_adapter(model_config)
    agent = ExecutorAgent(model=adapter)
    result = await agent.invoke(
        AgentInput(
            payload=task_input,
            tools=tools,
            context_window=context,
            config=model_config if isinstance(model_config, dict) else {"model": model_config},
        )
    )
    return result.model_dump(mode="json")


@activity.defn(name="run_diagnostician")
async def run_diagnostician(blocker: dict, model_config: dict | str) -> dict:
    adapter = create_adapter(model_config)
    agent = DiagnosticianAgent(model=adapter)
    result = await agent.invoke(
        AgentInput(
            payload=blocker,
            tools=[],
            context_window="",
            config=model_config if isinstance(model_config, dict) else {"model": model_config},
        )
    )
    return result.model_dump(mode="json")


@activity.defn(name="run_builder")
async def run_builder(spec: dict, model_config: dict | str, previous_failure: dict | None = None) -> dict:
    adapter = create_adapter(model_config)
    agent = BuilderAgent(model=adapter)
    result = await agent.invoke(
        AgentInput(
            payload={"tool_spec": spec, "previous_failure": previous_failure},
            tools=[],
            context_window="",
            config=(model_config if isinstance(model_config, dict) else {"model": model_config}),
        )
    )
    return result.model_dump(mode="json")


@activity.defn(name="run_verifier")
async def run_verifier(artifact: dict, spec: dict, sandbox_config: dict) -> dict:
    sandbox = Sandbox(SandboxPolicy.model_validate(sandbox_config))
    verifier = VerifierAgent()
    result = await verifier.verify(
        ToolArtifact.model_validate(artifact),
        ToolSpec.model_validate(spec),
        sandbox,
    )
    return result.model_dump(mode="json")


@activity.defn(name="install_public_tool")
async def install_public_tool(tool_id: str, static_tools: list[str]) -> dict:
    registry = ToolRegistry(static_tools)
    package = registry.install_public_package(tool_id)
    return {
        "artifact": package.artifact.model_dump(mode="json"),
        "spec": package.spec.model_dump(mode="json"),
        "origin": package.origin,
    }
