from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from cell.types import EventLogEntry, SourceRef, TaskOutput, CompletionStatus


def build_output_envelope(
    *,
    cell_id: str,
    task_id: str,
    result: dict[str, Any],
    result_schema_id: str,
    confidence: float,
    completion_status: CompletionStatus,
    sources: list[dict[str, Any]] | list[SourceRef],
    reasoning_summary: str,
    assumptions: list[str],
    tools_used: list[str],
    dynamic_tools_created: list[str],
    model_id: str,
    blockers_encountered: int,
    retries: int,
    total_latency_ms: int,
    total_tokens: dict[str, int],
    total_cost_usd: float,
    event_log: list[EventLogEntry],
    state_transitions: list[str],
    timestamp: datetime | None = None,
) -> TaskOutput:
    normalized_sources: list[SourceRef] = []
    for index, item in enumerate(sources):
        if isinstance(item, SourceRef):
            normalized_sources.append(item)
            continue
        normalized_sources.append(
            SourceRef(
                source_id=str(item.get("source_id", f"src_{index:04d}")),
                content_hash=str(item.get("content_hash", "")),
                usage_description=str(item.get("usage_description", "Used during task execution.")),
            )
        )
    return TaskOutput(
        cell_id=cell_id,
        task_id=task_id,
        timestamp=timestamp or datetime.now(timezone.utc),
        result=result,
        result_schema_id=result_schema_id,
        confidence=confidence,
        completion_status=completion_status,
        sources=normalized_sources,
        reasoning_summary=reasoning_summary,
        assumptions=assumptions,
        tools_used=tools_used,
        dynamic_tools_created=dynamic_tools_created,
        model_id=model_id,
        blockers_encountered=blockers_encountered,
        retries=retries,
        total_latency_ms=total_latency_ms,
        total_tokens=total_tokens,
        total_cost_usd=total_cost_usd,
        event_log_ref=f"event-log://{cell_id}/{task_id}",
        state_transitions=state_transitions,
    )
