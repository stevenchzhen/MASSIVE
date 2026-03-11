from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable

from temporalio.client import Client

from cell.config import load_cell_config
from cell.worker import create_worker


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def compose_file() -> Path:
    return repo_root() / "docker-compose.yaml"


def default_config_path() -> Path:
    return repo_root() / "cell" / "configs" / "default_cell.yaml"


async def temporal_connectivity(host: str) -> tuple[bool, str]:
    try:
        await Client.connect(host)
        return True, f"Temporal reachable at {host}"
    except Exception as exc:
        return False, f"Temporal unavailable at {host}: {exc}"


def docker_compose_command() -> list[str] | None:
    docker = shutil.which("docker")
    if docker:
        probe = subprocess.run([docker, "compose", "version"], capture_output=True, text=True)
        if probe.returncode == 0:
            return [docker, "compose"]
    legacy = shutil.which("docker-compose")
    if legacy:
        return [legacy]
    return None


async def ensure_local_stack(host: str) -> tuple[bool, str]:
    ok, message = await temporal_connectivity(host)
    if ok:
        return True, message

    compose_cmd = docker_compose_command()
    compose = compose_file()
    if compose_cmd is None or not compose.exists():
        return (
            False,
            f"{message}\nStart Temporal with `docker compose up -d postgres temporal temporal-ui` from {repo_root()} "
            "or point CELLFORGE_TEMPORAL_HOST/TEMPORAL_HOST at an existing cluster.",
        )

    start = subprocess.run(
        [*compose_cmd, "-f", str(compose), "up", "-d", "postgres", "temporal", "temporal-ui"],
        cwd=repo_root(),
        capture_output=True,
        text=True,
    )
    if start.returncode != 0:
        return False, f"Failed to start local Temporal stack:\n{start.stderr.strip() or start.stdout.strip()}"

    for _ in range(30):
        ok, connect_message = await temporal_connectivity(host)
        if ok:
            return True, f"Started local Temporal stack with docker compose.\n{connect_message}"
        await asyncio.sleep(1)
    return False, "Started docker services, but Temporal did not become reachable within 30 seconds."


def provider_for_model(model: str) -> str:
    if model.startswith("claude"):
        return "anthropic"
    if model.startswith(("gpt", "o1", "o3")):
        return "openai"
    return "ollama"


def provider_setup_hints(provider: str, configured_alternates: Iterable[str] = ()) -> list[str]:
    hints: list[str] = []
    if provider == "anthropic":
        hints.append("Set it with: export ANTHROPIC_API_KEY=your_key")
    elif provider == "openai":
        hints.append("Set it with: export OPENAI_API_KEY=your_key")
    elif provider == "ollama":
        hints.append("Start Ollama locally and ensure http://localhost:11434 is reachable.")
    alternates = sorted({item for item in configured_alternates if item != provider and item != "deterministic"})
    if alternates:
        hints.append(f"Other providers already configured in this config: {', '.join(alternates)}")
    else:
        hints.append("Supported alternates: OpenAI (OPENAI_API_KEY) or Ollama (local model runtime).")
    return hints


def configured_providers(cfg) -> set[str]:
    providers: set[str] = set()
    for role_name in cfg.agents.model_dump(exclude_none=True):
        agent = getattr(cfg.agents, role_name)
        model = getattr(agent, "model", None)
        providers.add("deterministic" if not model else provider_for_model(model))
    return providers


def provider_diagnostics(cfg) -> list[tuple[str, str, str, list[str]]]:
    diagnostics: list[tuple[str, str, str, list[str]]] = []
    configured = configured_providers(cfg)
    for role_name in sorted(cfg.agents.model_dump(exclude_none=True)):
        agent = getattr(cfg.agents, role_name)
        model = getattr(agent, "model", None)
        if not model:
            diagnostics.append((role_name, "OK", "deterministic / disabled", []))
            continue
        provider = provider_for_model(model)
        if provider == "anthropic":
            if os.getenv("ANTHROPIC_API_KEY"):
                diagnostics.append((role_name, "OK", f"{model} via Anthropic", []))
            else:
                diagnostics.append(
                    (
                        role_name,
                        "FAIL",
                        f"{model} via Anthropic (missing ANTHROPIC_API_KEY)",
                        provider_setup_hints("anthropic", configured),
                    )
                )
            continue
        if provider == "openai":
            if os.getenv("OPENAI_API_KEY"):
                diagnostics.append((role_name, "OK", f"{model} via OpenAI", []))
            else:
                diagnostics.append(
                    (
                        role_name,
                        "FAIL",
                        f"{model} via OpenAI (missing OPENAI_API_KEY)",
                        provider_setup_hints("openai", configured),
                    )
                )
            continue
        diagnostics.append(
            (
                role_name,
                "WARN",
                f"{model} via Ollama (local runtime expected)",
                provider_setup_hints("ollama", configured),
            )
        )
    return diagnostics


async def run_dev_server(
    host: str,
    task_queue: str,
    auto_start: bool = True,
    config_path: str | Path | None = None,
) -> int:
    cfg_path = Path(config_path or default_config_path())
    print("CellForge startup wizard")
    print(f"  repo        {repo_root()}")
    print(f"  config      {cfg_path}")
    print(f"  temporal    {host}")
    print(f"  task queue  {task_queue}")

    if sys.version_info < (3, 12):
        print("[1/4] Python       FAIL: Python 3.12+ is required.")
        return 1
    print(f"[1/4] Python       OK: {sys.version.split()[0]}")

    try:
        cfg = load_cell_config(cfg_path)
        print(f"[2/4] Config       OK: loaded {cfg_path}")
    except Exception as exc:
        print(f"[2/4] Config       FAIL: could not load {cfg_path} ({exc})")
        return 1

    if auto_start:
        ok, message = await ensure_local_stack(host)
    else:
        ok, message = await temporal_connectivity(host)
        if not ok:
            message = (
                f"{message}\nRun `cellforge dev` without `--no-start` to boot the local stack, or start Temporal manually."
            )
    print(f"[3/4] Temporal     {'OK' if ok else 'FAIL'}: {message}")
    if not ok:
        return 1

    print("[4/4] Providers    checking model/provider setup")
    for role_name, status, detail, hints in provider_diagnostics(cfg):
        print(f"        {role_name:14} {status}: {detail}")
        for hint in hints:
            print(f"          -> {hint}")

    print("        worker       starting (Ctrl-C to stop)")
    client = await Client.connect(host)
    worker = create_worker(client, task_queue)
    try:
        await worker.run()
    except KeyboardInterrupt:
        print("\n        worker       stopped")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Start the local CellForge worker against a local Temporal stack.")
    parser.add_argument("--host", default=os.getenv("CELLFORGE_TEMPORAL_HOST", os.getenv("TEMPORAL_HOST", "localhost:7233")))
    parser.add_argument("--task-queue", default=os.getenv("CELLFORGE_TASK_QUEUE", os.getenv("TEMPORAL_TASK_QUEUE", "cell-task-queue")))
    parser.add_argument("--config", default=str(default_config_path()))
    parser.add_argument("--no-start", action="store_true", help="Do not attempt to start docker compose services automatically.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return asyncio.run(run_dev_server(args.host, args.task_queue, auto_start=not args.no_start, config_path=args.config))


if __name__ == "__main__":
    raise SystemExit(main())
