from __future__ import annotations

from cell.types import Blocker, TaskInput, TaskOutput, ToolArtifact, ToolVerdict


class CellHooks:
    async def on_task_start(self, task_input: TaskInput) -> TaskInput:
        return task_input

    async def on_blocker(self, blocker: Blocker) -> Blocker:
        return blocker

    async def on_tool_created(self, artifact: ToolArtifact, verdict: ToolVerdict) -> None:
        return None

    async def on_result(self, output: TaskOutput) -> TaskOutput:
        return output

    async def on_escalation(self, reason: str, partial_result: dict | None) -> None:
        return None

