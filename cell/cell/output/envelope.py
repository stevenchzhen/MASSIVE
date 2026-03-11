from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from cell.types import CellOutputEnvelope, EvidenceItem, EventLogEntry, VerdictType


def build_output_envelope(
    *,
    cell_id: str,
    task_id: str,
    verdict: dict[str, Any],
    confidence: float,
    verdict_type: VerdictType,
    evidence: list[dict[str, Any]] | list[EvidenceItem],
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
) -> CellOutputEnvelope:
    normalized_evidence: list[EvidenceItem] = []
    for index, item in enumerate(evidence):
        if isinstance(item, EvidenceItem):
            normalized_evidence.append(item)
            continue
        normalized_evidence.append(
            EvidenceItem(
                evidence_id=str(item.get("evidence_id", f"ev_{index:04d}")),
                summary=str(item.get("summary", "evidence")),
                content=item,
                source=str(item.get("source", "executor")),
                confidence=float(item.get("confidence", confidence)),
            )
        )
    return CellOutputEnvelope(
        cell_id=cell_id,
        task_id=task_id,
        timestamp=timestamp or datetime.now(timezone.utc),
        verdict=verdict,
        confidence=confidence,
        verdict_type=verdict_type,
        evidence=normalized_evidence,
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
