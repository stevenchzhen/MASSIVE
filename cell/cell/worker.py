from __future__ import annotations

import asyncio
import os

from temporalio.client import Client
from temporalio.worker import Worker

from cell.runtime.activities import run_builder, run_diagnostician, run_executor, run_verifier
from cell.runtime.workflow import CellWorkflow


async def main() -> None:
    host = os.getenv("TEMPORAL_HOST", "localhost:7233")
    task_queue = os.getenv("TEMPORAL_TASK_QUEUE", "cell-task-queue")
    client = await Client.connect(host)
    worker = Worker(
        client,
        task_queue=task_queue,
        workflows=[CellWorkflow],
        activities=[run_executor, run_diagnostician, run_builder, run_verifier],
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())

