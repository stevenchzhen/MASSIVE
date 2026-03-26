#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextlib
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "cell"))

from cell.artifacts import load_artifact_bundle
from cell.types import CompletionStatus


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run deterministic and live structure tests for the MASSIVE single-cell runtime."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    quick = subparsers.add_parser("quick", help="Run the deterministic self-healing proof suite.")
    _add_common_flags(quick, include_artifacts=False)

    baseline = subparsers.add_parser("baseline", help="Run the baseline live example and validate its artifact bundle.")
    _add_common_flags(baseline, include_artifacts=True)

    self_heal = subparsers.add_parser("self-heal", help="Run the live self-healing drill and assert that a verified tool was created.")
    _add_common_flags(self_heal, include_artifacts=True)

    all_parser = subparsers.add_parser("all", help="Run the deterministic suite, doctor, baseline demo, and live self-healing drill.")
    _add_common_flags(all_parser, include_artifacts=True)
    return parser


def _add_common_flags(parser: argparse.ArgumentParser, *, include_artifacts: bool) -> None:
    parser.add_argument("--host", default="localhost:7233", help="Temporal host to use for live checks.")
    parser.add_argument("--task-queue", default="cell-task-queue", help="Temporal task queue for live runs.")
    parser.add_argument("--doctor-no-fix", action="store_true", help="Do not auto-start Temporal during doctor checks.")
    parser.add_argument(
        "--use-running-worker",
        action="store_true",
        help="Assume a worker is already running instead of starting an ephemeral local one.",
    )
    if include_artifacts:
        parser.add_argument(
            "--artifacts-root",
            default=str(REPO_ROOT / ".artifacts" / "structure-tests"),
            help="Base directory for generated artifact bundles.",
        )


def run(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "quick":
        run_quick()
        return 0
    if args.command == "baseline":
        run_doctor(args.host, args.doctor_no_fix)
        bundle_dir = Path(args.artifacts_root) / "baseline"
        with managed_worker(args.host, args.task_queue, use_running_worker=args.use_running_worker):
            run_baseline(args.host, args.task_queue, bundle_dir)
        return 0
    if args.command == "self-heal":
        run_doctor(args.host, args.doctor_no_fix)
        bundle_dir = Path(args.artifacts_root) / "self-heal"
        with managed_worker(args.host, args.task_queue, use_running_worker=args.use_running_worker):
            run_self_heal(args.host, args.task_queue, bundle_dir)
        return 0
    if args.command == "all":
        run_quick()
        run_doctor(args.host, args.doctor_no_fix)
        root = Path(args.artifacts_root)
        with managed_worker(args.host, args.task_queue, use_running_worker=args.use_running_worker):
            run_baseline(args.host, args.task_queue, root / "baseline")
            run_self_heal(args.host, args.task_queue, root / "self-heal")
        return 0
    raise AssertionError(f"Unhandled command: {args.command}")


def run_quick() -> None:
    print_step("Deterministic guardrails")
    invoke(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "cell/tests/test_workflow.py",
            "cell/tests/test_verifier.py",
            "cell/tests/test_artifacts.py",
            "cell/tests/test_cli.py",
            "cell/tests/test_cell_api.py",
        ]
    )


def run_doctor(host: str, no_fix: bool) -> None:
    print_step("Environment doctor")
    command = [sys.executable, "-m", "cellforge", "doctor", "--host", host]
    if no_fix:
        command.append("--no-fix")
    invoke(command)


def run_baseline(host: str, task_queue: str, bundle_dir: Path) -> None:
    print_step("Baseline live run")
    invoke(
        [
            sys.executable,
            "-m",
            "cellforge",
            "run",
            "--example",
            "document-extraction",
            "--host",
            host,
            "--task-queue",
            task_queue,
            "--artifacts",
            str(bundle_dir),
        ]
    )
    bundle = load_artifact_bundle(bundle_dir)
    if bundle.task_output.completion_status != CompletionStatus.COMPLETE:
        raise SystemExit(f"Baseline run did not complete: {bundle.task_output.completion_status.value}")
    print(f"  baseline    OK: {bundle.task_output.task_id} -> {bundle.task_output.completion_status.value}")


def run_self_heal(host: str, task_queue: str, bundle_dir: Path) -> None:
    print_step("Self-healing live run")
    invoke(
        [
            sys.executable,
            "-m",
            "cellforge",
            "run",
            "--example",
            "tool-creation",
            "--config",
            str(REPO_ROOT / "cell" / "configs" / "toolpath_cell.yaml"),
            "--host",
            host,
            "--task-queue",
            task_queue,
            "--artifacts",
            str(bundle_dir),
        ]
    )
    bundle = load_artifact_bundle(bundle_dir)
    if bundle.task_output.completion_status != CompletionStatus.COMPLETE:
        raise SystemExit(f"Self-heal run did not complete: {bundle.task_output.completion_status.value}")

    transitions = bundle.state_transitions
    if "building" not in transitions or "verifying" not in transitions:
        raise SystemExit(
            "Self-heal run completed but did not enter building/verifying. "
            "The model likely solved the task manually instead of triggering the tool path."
        )
    if not bundle.blockers:
        raise SystemExit("Self-heal run completed without recording a blocker.")
    if not bundle.dynamic_tools_created:
        raise SystemExit("Self-heal run completed without registering a dynamic tool.")
    if not bundle.verifier_reports:
        raise SystemExit("Self-heal run completed without a verifier report.")
    print(
        "  self-heal   OK: "
        f"{bundle.task_output.task_id} -> dynamic_tools={', '.join(bundle.dynamic_tools_created)}"
    )


def invoke(command: list[str]) -> None:
    print(f"$ {shlex.join(command)}", flush=True)
    subprocess.run(command, cwd=REPO_ROOT, check=True)


def print_step(title: str) -> None:
    print()
    print(f"== {title} ==", flush=True)


@contextlib.contextmanager
def managed_worker(host: str, task_queue: str, *, use_running_worker: bool):
    if use_running_worker:
        yield
        return

    print_step("Ephemeral worker")
    command = [
        sys.executable,
        "-m",
        "cellforge",
        "dev",
        "--no-start",
        "--host",
        host,
        "--task-queue",
        task_queue,
    ]
    print(f"$ {shlex.join(command)}", flush=True)
    process = subprocess.Popen(
        command,
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    try:
        if process.stdout is None:
            raise SystemExit("Failed to capture worker output.")
        ready = False
        deadline = time.time() + 20
        while time.time() < deadline:
            line = process.stdout.readline()
            if line:
                print(f"  worker> {line.rstrip()}", flush=True)
                if "worker       starting" in line:
                    ready = True
                    break
            elif process.poll() is not None:
                raise SystemExit(f"Ephemeral worker exited early with code {process.returncode}.")
            else:
                time.sleep(0.2)
        if not ready:
            raise SystemExit("Timed out waiting for the ephemeral worker to start.")
        yield
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    raise SystemExit(run())
