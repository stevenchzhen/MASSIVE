from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from cell.types import Blocker, EventLogEntry, TaskInput, TaskOutput, ToolVerdict


class ArtifactBundle(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    bundle_version: str = Field(default="1")
    input_manifest: TaskInput
    state_transitions: list[str]
    blockers: list[Blocker]
    tools_used: list[str]
    dynamic_tools_created: list[str]
    verifier_reports: list[ToolVerdict]
    task_output: TaskOutput
    event_log: list[EventLogEntry]


def build_artifact_bundle(task_input: TaskInput, task_output: TaskOutput) -> ArtifactBundle:
    blockers: list[Blocker] = []
    for event in task_output.event_log:
        if event.event != "message":
            continue
        payload = event.payload_summary.get("blocker")
        if isinstance(payload, dict):
            blockers.append(Blocker.model_validate(payload))
    return ArtifactBundle(
        input_manifest=task_input,
        state_transitions=task_output.state_transitions,
        blockers=blockers,
        tools_used=task_output.tools_used,
        dynamic_tools_created=task_output.dynamic_tools_created,
        verifier_reports=task_output.verifier_reports,
        task_output=task_output,
        event_log=task_output.event_log,
    )


def write_artifact_bundle(path: str | Path, task_input: TaskInput, task_output: TaskOutput) -> ArtifactBundle:
    bundle = build_artifact_bundle(task_input, task_output)
    bundle_path = Path(path)
    bundle_path.mkdir(parents=True, exist_ok=True)

    _write_json(bundle_path / "bundle_manifest.json", {"bundle_version": bundle.bundle_version})
    _write_json(bundle_path / "input_manifest.json", bundle.input_manifest.model_dump(mode="json"))
    _write_json(bundle_path / "state_transitions.json", {"state_transitions": bundle.state_transitions})
    _write_json(
        bundle_path / "tools_used.json",
        {
            "tools_used": bundle.tools_used,
            "dynamic_tools_created": bundle.dynamic_tools_created,
        },
    )
    _write_json(
        bundle_path / "blockers.json",
        {"blockers": [item.model_dump(mode="json") for item in bundle.blockers]},
    )
    _write_json(
        bundle_path / "verifier_report.json",
        {"verifier_reports": [item.model_dump(mode="json") for item in bundle.verifier_reports]},
    )
    _write_json(bundle_path / "event_log.json", {"event_log": [item.model_dump(mode="json") for item in bundle.event_log]})
    _write_json(bundle_path / "task_output.json", bundle.task_output.model_dump(mode="json"))
    return bundle


def load_artifact_bundle(path: str | Path) -> ArtifactBundle:
    bundle_path = Path(path)
    input_manifest = TaskInput.model_validate(_read_json(bundle_path / "input_manifest.json"))
    task_output = TaskOutput.model_validate(_read_json(bundle_path / "task_output.json"))
    blockers_payload = _read_json(bundle_path / "blockers.json").get("blockers", [])
    verifier_payload = _read_json(bundle_path / "verifier_report.json").get("verifier_reports", [])
    event_payload = _read_json(bundle_path / "event_log.json").get("event_log", [])
    transitions_payload = _read_json(bundle_path / "state_transitions.json").get("state_transitions", [])
    tools_payload = _read_json(bundle_path / "tools_used.json")
    return ArtifactBundle(
        input_manifest=input_manifest,
        state_transitions=[str(item) for item in transitions_payload],
        blockers=[Blocker.model_validate(item) for item in blockers_payload],
        tools_used=[str(item) for item in tools_payload.get("tools_used", [])],
        dynamic_tools_created=[str(item) for item in tools_payload.get("dynamic_tools_created", [])],
        verifier_reports=[ToolVerdict.model_validate(item) for item in verifier_payload],
        task_output=task_output,
        event_log=[EventLogEntry.model_validate(item) for item in event_payload],
    )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())
