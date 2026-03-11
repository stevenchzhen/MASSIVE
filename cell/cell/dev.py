from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import subprocess
import sys
from pathlib import Path

from temporalio.client import Client

from cell.worker import create_worker


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def compose_file() -> Path:
    return repo_root() / "docker-compose.yaml"


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


async def run_dev_server(host: str, task_queue: str, auto_start: bool = True) -> int:
    print("CellForge local dev")
    print(f"  repo        {repo_root()}")
    print(f"  temporal    {host}")
    print(f"  task queue  {task_queue}")

    if sys.version_info < (3, 12):
        print("  python      FAIL: Python 3.12+ is required.")
        return 1
    print(f"  python      OK: {sys.version.split()[0]}")

    if auto_start:
        ok, message = await ensure_local_stack(host)
    else:
        ok, message = await temporal_connectivity(host)
        if not ok:
            message = (
                f"{message}\nRun `cellforge dev` without `--no-start` to boot the local stack, or start Temporal manually."
            )
    print(f"  temporal    {'OK' if ok else 'FAIL'}: {message}")
    if not ok:
        return 1

    print("  worker      starting (Ctrl-C to stop)")
    client = await Client.connect(host)
    worker = create_worker(client, task_queue)
    try:
        await worker.run()
    except KeyboardInterrupt:
        print("\n  worker      stopped")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Start the local CellForge worker against a local Temporal stack.")
    parser.add_argument("--host", default=os.getenv("CELLFORGE_TEMPORAL_HOST", os.getenv("TEMPORAL_HOST", "localhost:7233")))
    parser.add_argument("--task-queue", default=os.getenv("CELLFORGE_TASK_QUEUE", os.getenv("TEMPORAL_TASK_QUEUE", "cell-task-queue")))
    parser.add_argument("--no-start", action="store_true", help="Do not attempt to start docker compose services automatically.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return asyncio.run(run_dev_server(args.host, args.task_queue, auto_start=not args.no_start))


if __name__ == "__main__":
    raise SystemExit(main())
