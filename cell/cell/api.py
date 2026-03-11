from __future__ import annotations

import hashlib
from pathlib import Path
from typing import AsyncIterator
from uuid import uuid4

from temporalio.client import Client

from cell.artifacts import write_artifact_bundle
from cell.config import CellConfig, load_cell_config
from cell.hooks import CellHooks
from cell.schema_registry import ResultSchemaRegistry
from cell.types import CellEvent, CompletionStatus, Document, MessageType, TaskInput, TaskOutput, utc_now


def _document_from_path(path: str | Path) -> Document:
    file_path = Path(path)
    content = file_path.read_text()
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return Document(
        name=file_path.name,
        content=content,
        mime_type=None,
        content_hash=content_hash,
    )


class Cell:
    @classmethod
    async def run(
        cls,
        instruction: str | TaskInput,
        *,
        documents: list[str | Path] | None = None,
        input_data: dict | None = None,
        result_schema: dict | None = None,
        result_schema_id: str = "custom",
        context: dict | None = None,
        trust_level: str = "standard",
        allow_dynamic_tools: bool = True,
        max_cost_usd: float | None = None,
        config: CellConfig | str | Path | None = None,
        client: Client,
        task_queue: str = "cell-task-queue",
        workflow_id: str | None = None,
        hooks: CellHooks | None = None,
        artifacts_dir: str | Path | None = None,
    ) -> TaskOutput:
        if isinstance(instruction, TaskInput):
            task_input = instruction
        else:
            task_input = TaskInput(
                task_id=workflow_id or f"task_{uuid4().hex[:12]}",
                instruction=instruction,
                input_data=input_data or {},
                input_documents=[_document_from_path(path) for path in (documents or [])],
                result_schema=result_schema or ResultSchemaRegistry.analysis(),
                result_schema_id=result_schema_id,
                context=context or {},
                trust_level=trust_level,
                allow_dynamic_tools=allow_dynamic_tools,
                max_cost_usd=max_cost_usd,
            )

        cfg = config if isinstance(config, CellConfig) else load_cell_config(config or Path(__file__).resolve().parents[1] / "configs" / "default_cell.yaml")
        hooks = hooks or CellHooks()
        task_input = await hooks.on_task_start(task_input)
        raw_output = await client.execute_workflow(
            "CellWorkflow",
            args=[task_input.model_dump(mode="json"), cfg.model_dump(mode="json")],
            id=workflow_id or task_input.task_id,
            task_queue=task_queue,
        )
        output = TaskOutput.model_validate(raw_output)
        if artifacts_dir is not None:
            bundle_dir = Path(artifacts_dir)
            output = output.model_copy(update={"event_log_ref": bundle_dir.resolve().as_uri()})
        output = await hooks.on_result(output)
        if artifacts_dir is not None:
            write_artifact_bundle(Path(artifacts_dir), task_input, output)
        if output.completion_status != CompletionStatus.COMPLETE:
            await hooks.on_escalation(output.result.get("reason", "Task did not complete"), output.result)
        return output

    @classmethod
    async def stream(
        cls,
        instruction: str | TaskInput,
        **kwargs,
    ) -> AsyncIterator[CellEvent]:
        task_id = instruction.task_id if isinstance(instruction, TaskInput) else kwargs.get("workflow_id") or f"task_{uuid4().hex[:12]}"
        cell_id = "cell_default"
        yield CellEvent(
            timestamp=utc_now(),
            event_type="cell.started",
            cell_id=cell_id,
            task_id=task_id,
            data={},
        )
        output = await cls.run(instruction, workflow_id=task_id, **kwargs)
        for event in output.event_log:
            if event.event == "state_transition":
                yield CellEvent(
                    timestamp=event.timestamp,
                    event_type="state_changed",
                    cell_id=output.cell_id,
                    task_id=output.task_id,
                    data=event.payload_summary,
                )
                continue
            if event.message_type == MessageType.BLOCKER:
                blocker_payload = event.payload_summary.get("blocker", event.payload_summary)
                yield CellEvent(
                    timestamp=event.timestamp,
                    event_type="blocker.detected",
                    cell_id=output.cell_id,
                    task_id=output.task_id,
                    data=blocker_payload if isinstance(blocker_payload, dict) else {"blocker": blocker_payload},
                )
        for report in output.verifier_reports:
            yield CellEvent(
                timestamp=utc_now(),
                event_type="tool.verified",
                cell_id=output.cell_id,
                task_id=output.task_id,
                data={
                    "artifact_id": report.artifact_id,
                    "spec_id": report.spec_id,
                    "passed": report.passed,
                },
            )
        yield CellEvent(
            timestamp=utc_now(),
            event_type="cell.complete" if output.completion_status == CompletionStatus.COMPLETE else "cell.escalated",
            cell_id=output.cell_id,
            task_id=output.task_id,
            data={"completion_status": output.completion_status.value, "confidence": output.confidence},
        )
