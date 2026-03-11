from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx
import yaml

from cell import ResultSchemaRegistry, load_cell_config
from cell.dev import repo_root, run_dev_server, temporal_connectivity
from cell.tools.registry import ToolRegistry

from .api import CellForge


def default_config_path() -> Path:
    return repo_root() / "cell" / "configs" / "default_cell.yaml"


def examples_root() -> Path:
    return repo_root() / "examples"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CellForge CLI for running and inspecting the MASSIVE single-cell runtime.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = _add_task_parser(subparsers.add_parser("run", help="Run one task through the cell."))
    run_parser.add_argument("--json", action="store_true", help="Print the full TaskOutput as JSON.")

    _add_task_parser(subparsers.add_parser("stream", help="Replay lifecycle events for one task run."))

    replay_parser = subparsers.add_parser("replay", help="Replay a previously emitted artifact bundle.")
    replay_parser.add_argument("bundle", help="Path to an artifact bundle directory.")

    tools_parser = subparsers.add_parser("tools", help="Inspect bundled tools.")
    tools_subparsers = tools_parser.add_subparsers(dest="tools_command", required=True)
    tools_list = tools_subparsers.add_parser("list", help="List tools available from the configured registry.")
    tools_list.add_argument("--config", default=str(default_config_path()))

    doctor_parser = subparsers.add_parser("doctor", help="Validate local setup.")
    doctor_parser.add_argument("--config", default=str(default_config_path()))
    doctor_parser.add_argument("--host", default=os.getenv("CELLFORGE_TEMPORAL_HOST", os.getenv("TEMPORAL_HOST", "localhost:7233")))

    dev_parser = subparsers.add_parser("dev", help="Start the local worker against a local Temporal stack.")
    dev_parser.add_argument("--host", default=os.getenv("CELLFORGE_TEMPORAL_HOST", os.getenv("TEMPORAL_HOST", "localhost:7233")))
    dev_parser.add_argument("--task-queue", default=os.getenv("CELLFORGE_TASK_QUEUE", os.getenv("TEMPORAL_TASK_QUEUE", "cell-task-queue")))
    dev_parser.add_argument("--no-start", action="store_true")
    return parser


def _add_task_parser(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument("instruction", nargs="?", help="Task instruction. Omit when using --task-file or --example.")
    parser.add_argument("--task-file", help="YAML or JSON task manifest.")
    parser.add_argument("--example", choices=["document-extraction"], help="Run a bundled example task.")
    parser.add_argument("--document", dest="documents", action="append", default=[], help="Input document path. Repeatable.")
    parser.add_argument("--config", default=str(default_config_path()))
    parser.add_argument("--host", default=os.getenv("CELLFORGE_TEMPORAL_HOST", os.getenv("TEMPORAL_HOST", "localhost:7233")))
    parser.add_argument("--task-queue", default=os.getenv("CELLFORGE_TASK_QUEUE", os.getenv("TEMPORAL_TASK_QUEUE", "cell-task-queue")))
    parser.add_argument("--trust-level", default=None, choices=["minimal", "standard", "high"])
    parser.add_argument("--artifacts", help="Directory for replayable local artifacts.")
    parser.add_argument("--workflow-id", help="Optional workflow ID override.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "run":
        return asyncio.run(run_command(args))
    if args.command == "stream":
        return asyncio.run(stream_command(args))
    if args.command == "replay":
        return replay_command(args)
    if args.command == "tools":
        return tools_list_command(args)
    if args.command == "doctor":
        return asyncio.run(doctor_command(args))
    if args.command == "dev":
        return asyncio.run(run_dev_server(args.host, args.task_queue, auto_start=not args.no_start))
    raise AssertionError(f"Unhandled command: {args.command}")


async def run_command(args: argparse.Namespace) -> int:
    task = resolve_task_input(args)
    cell = CellForge.from_env(config=args.config, temporal_host=args.host, task_queue=args.task_queue)
    output = await cell.run_async(
        task["instruction"],
        documents=task["documents"],
        input_data=task["input_data"],
        result_schema=task["result_schema"],
        result_schema_id=task["result_schema_id"],
        context=task["context"],
        trust_level=task["trust_level"],
        allow_dynamic_tools=task["allow_dynamic_tools"],
        max_cost_usd=task["max_cost_usd"],
        workflow_id=args.workflow_id,
        artifacts_dir=args.artifacts,
    )
    if args.json:
        print(json.dumps(output.model_dump(mode="json"), indent=2))
    else:
        print(f"task_id: {output.task_id}")
        print(f"status: {output.completion_status.value}")
        print(f"confidence: {output.confidence:.2f}")
        print(f"tools_used: {', '.join(output.tools_used) if output.tools_used else '(none)'}")
        print(json.dumps(output.result, indent=2))
        if args.artifacts:
            print(f"artifacts: {Path(args.artifacts).resolve()}")
    return 0 if output.completion_status.value == "complete" else 1


async def stream_command(args: argparse.Namespace) -> int:
    task = resolve_task_input(args)
    cell = CellForge.from_env(config=args.config, temporal_host=args.host, task_queue=args.task_queue)
    async for event in cell.stream(
        task["instruction"],
        documents=task["documents"],
        input_data=task["input_data"],
        result_schema=task["result_schema"],
        result_schema_id=task["result_schema_id"],
        context=task["context"],
        trust_level=task["trust_level"],
        allow_dynamic_tools=task["allow_dynamic_tools"],
        max_cost_usd=task["max_cost_usd"],
        workflow_id=args.workflow_id,
        artifacts_dir=args.artifacts,
    ):
        print(f"[{event.event_type}] {json.dumps(event.data, sort_keys=True)}")
    return 0


def replay_command(args: argparse.Namespace) -> int:
    bundle = CellForge.replay(args.bundle)
    print(f"task_id: {bundle.task_output.task_id}")
    print(f"status: {bundle.task_output.completion_status.value}")
    print(f"state_transitions: {' -> '.join(bundle.state_transitions)}")
    print(f"blockers: {len(bundle.blockers)}")
    print(f"tools_used: {', '.join(bundle.tools_used) if bundle.tools_used else '(none)'}")
    if bundle.dynamic_tools_created:
        print(f"dynamic_tools_created: {', '.join(bundle.dynamic_tools_created)}")
    if bundle.verifier_reports:
        print("verifier_reports:")
        for report in bundle.verifier_reports:
            print(f"  - {report.spec_id}: {'passed' if report.passed else 'failed'}")
    print("result:")
    print(json.dumps(bundle.task_output.result, indent=2))
    return 0


def tools_list_command(args: argparse.Namespace) -> int:
    cfg = load_cell_config(args.config)
    registry = ToolRegistry(cfg.static_tools)
    for tool in registry.list():
        kind = "dynamic" if tool.is_dynamic else "static"
        print(f"{tool.tool_id:24} {kind:7} {tool.description}")
    return 0


async def doctor_command(args: argparse.Namespace) -> int:
    failures = 0
    print("CellForge doctor")
    if sys.version_info < (3, 12):
        failures += 1
        print(f"  python      FAIL: {sys.version.split()[0]} (need 3.12+)")
    else:
        print(f"  python      OK: {sys.version.split()[0]}")

    config_path = Path(args.config)
    try:
        cfg = load_cell_config(config_path)
        print(f"  config      OK: {config_path}")
    except Exception as exc:
        print(f"  config      FAIL: {config_path} ({exc})")
        return 1

    ok, message = await temporal_connectivity(args.host)
    if ok:
        print(f"  temporal    OK: {message}")
    else:
        failures += 1
        print(f"  temporal    FAIL: {message}")
        print("               Start it with `cellforge dev` or `docker compose up -d postgres temporal temporal-ui`.")

    for label, status, detail in provider_checks(cfg):
        if status == "FAIL":
            failures += 1
        print(f"  {label:11} {status}: {detail}")

    return 1 if failures else 0


def provider_checks(cfg) -> list[tuple[str, str, str]]:
    checks: list[tuple[str, str, str]] = []
    for role_name in sorted(cfg.agents.model_dump(exclude_none=True)):
        agent = getattr(cfg.agents, role_name)
        model = getattr(agent, "model", None)
        if not model:
            checks.append((role_name, "OK", "deterministic / disabled"))
            continue
        provider = provider_for_model(model)
        if provider == "anthropic":
            checks.append(
                (
                    role_name,
                    "OK" if os.getenv("ANTHROPIC_API_KEY") else "FAIL",
                    f"{model} via Anthropic ({'ANTHROPIC_API_KEY set' if os.getenv('ANTHROPIC_API_KEY') else 'missing ANTHROPIC_API_KEY'})",
                )
            )
            continue
        if provider == "openai":
            checks.append(
                (
                    role_name,
                    "OK" if os.getenv("OPENAI_API_KEY") else "FAIL",
                    f"{model} via OpenAI ({'OPENAI_API_KEY set' if os.getenv('OPENAI_API_KEY') else 'missing OPENAI_API_KEY'})",
                )
            )
            continue
        if provider == "ollama":
            checks.append((role_name, *_ollama_status(model)))
            continue
        checks.append((role_name, "FAIL", f"unsupported model/provider mapping for {model!r}"))
    return checks


def _ollama_status(model: str) -> tuple[str, str]:
    try:
        response = httpx.get("http://localhost:11434/api/tags", timeout=2.0)
        response.raise_for_status()
        return "OK", f"{model} via Ollama (localhost:11434 reachable)"
    except Exception as exc:
        return "FAIL", f"{model} via Ollama (localhost:11434 unreachable: {exc})"


def provider_for_model(model: str) -> str:
    if model.startswith("claude"):
        return "anthropic"
    if model.startswith(("gpt", "o1", "o3")):
        return "openai"
    return "ollama"


def resolve_task_input(args: argparse.Namespace) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    base_dir = repo_root()
    if args.example:
        example_name = args.example.replace("-", "_")
        base_dir = examples_root() / example_name
        payload = load_manifest(base_dir / "task.yaml")
    elif args.task_file:
        task_path = Path(args.task_file).resolve()
        base_dir = task_path.parent
        payload = load_manifest(task_path)

    instruction = args.instruction or payload.get("instruction")
    if not instruction:
        raise SystemExit("Provide an instruction, --task-file, or --example.")

    document_paths = list(payload.get("documents", []))
    document_paths.extend(args.documents)
    resolved_documents = [str((base_dir / item).resolve()) if not Path(item).is_absolute() else str(Path(item)) for item in document_paths]

    result_schema = payload.get("result_schema")
    schema_name = payload.get("result_schema_name")
    if result_schema is None and schema_name:
        result_schema = named_schema(schema_name)
    if result_schema is None:
        result_schema = ResultSchemaRegistry.analysis()

    trust_level = args.trust_level or payload.get("trust_level", "standard")
    if trust_level == "high":
        trust_level = "high"

    return {
        "instruction": instruction,
        "documents": resolved_documents,
        "input_data": payload.get("input_data", {}),
        "result_schema": result_schema,
        "result_schema_id": payload.get("result_schema_id", schema_name or "custom"),
        "context": payload.get("context", {}),
        "trust_level": trust_level,
        "allow_dynamic_tools": payload.get("allow_dynamic_tools", True),
        "max_cost_usd": payload.get("max_cost_usd"),
    }


def load_manifest(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text()) if path.suffix in {".yaml", ".yml"} else json.loads(path.read_text())
    return raw or {}


def named_schema(name: str) -> dict[str, Any]:
    registry = ResultSchemaRegistry
    if not hasattr(registry, name):
        raise SystemExit(f"Unknown schema registry name: {name}")
    return getattr(registry, name)()
