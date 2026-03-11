from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import AsyncIterator

from temporalio.client import Client

from cell import Cell, CellConfig, CellHooks, TaskInput, TaskOutput, load_cell_config
from cell.artifacts import ArtifactBundle, load_artifact_bundle
from cell.types import CellEvent


class CellForge:
    def __init__(
        self,
        *,
        config: CellConfig | str | Path | None = None,
        temporal_host: str | None = None,
        task_queue: str | None = None,
        hooks: CellHooks | None = None,
    ):
        self.config = config if isinstance(config, CellConfig) or config is None else load_cell_config(config)
        self.temporal_host = temporal_host or os.getenv("CELLFORGE_TEMPORAL_HOST", os.getenv("TEMPORAL_HOST", "localhost:7233"))
        self.task_queue = task_queue or os.getenv("CELLFORGE_TASK_QUEUE", os.getenv("TEMPORAL_TASK_QUEUE", "cell-task-queue"))
        self.hooks = hooks

    @classmethod
    def from_env(
        cls,
        *,
        config: CellConfig | str | Path | None = None,
        temporal_host: str | None = None,
        task_queue: str | None = None,
        hooks: CellHooks | None = None,
    ) -> "CellForge":
        return cls(config=config, temporal_host=temporal_host, task_queue=task_queue, hooks=hooks)

    async def run_async(
        self,
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
        workflow_id: str | None = None,
        artifacts_dir: str | Path | None = None,
    ) -> TaskOutput:
        client = await Client.connect(self.temporal_host)
        return await Cell.run(
            instruction,
            documents=documents,
            input_data=input_data,
            result_schema=result_schema,
            result_schema_id=result_schema_id,
            context=context,
            trust_level=trust_level,
            allow_dynamic_tools=allow_dynamic_tools,
            max_cost_usd=max_cost_usd,
            config=self.config,
            client=client,
            task_queue=self.task_queue,
            workflow_id=workflow_id,
            hooks=self.hooks,
            artifacts_dir=artifacts_dir,
        )

    def run(self, instruction: str | TaskInput, **kwargs) -> TaskOutput:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.run_async(instruction, **kwargs))
        raise RuntimeError("CellForge.run() cannot be called inside an active event loop; use run_async() instead.")

    async def stream(
        self,
        instruction: str | TaskInput,
        **kwargs,
    ) -> AsyncIterator[CellEvent]:
        client = await Client.connect(self.temporal_host)
        async for event in Cell.stream(
            instruction,
            config=self.config,
            client=client,
            task_queue=self.task_queue,
            hooks=self.hooks,
            **kwargs,
        ):
            yield event

    @staticmethod
    def replay(path: str | Path) -> ArtifactBundle:
        return load_artifact_bundle(path)
