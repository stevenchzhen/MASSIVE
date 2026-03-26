from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any

from cell.types import Blocker, TaskDataSample, TaskInput


def should_derive_task_data_samples(task: TaskInput, blocker: Blocker) -> bool:
    if not task.input_documents and not task.input_data:
        return False

    text = " ".join(
        part
        for part in [
            blocker.description,
            blocker.what_would_unblock,
            blocker.input_sample or "",
        ]
        if part
    ).lower()

    generic_indicators = {
        "adder",
        "add two numbers",
        "arithmetic",
        "calculate",
        "calculation",
        "sum",
        "subtract",
        "multiply",
        "divide",
        "date arithmetic",
        "statistical test",
        "z score",
        "correlation",
    }
    if any(term in text for term in generic_indicators):
        return False

    data_shape_indicators = {
        "parse",
        "parser",
        "extract",
        "normalize",
        "transform",
        "schema",
        "format",
        "document",
        "record",
        "row",
        "column",
        "field",
        "segment",
        "delimiter",
        "csv",
        "json",
        "xml",
        "html",
        "pdf",
        "table",
        "<<",
        "image",
        "audio",
        "video",
    }
    if blocker.input_sample:
        return True
    return any(term in text for term in data_shape_indicators)


def derive_task_data_samples(
    task: TaskInput,
    blocker: Blocker,
    *,
    sample_ratio: float,
    max_samples: int,
) -> list[TaskDataSample]:
    if max_samples <= 0:
        return []

    focus_terms = _focus_terms(blocker)
    samples: list[TaskDataSample] = []

    for document in task.input_documents:
        remaining = max_samples - len(samples)
        if remaining <= 0:
            break
        samples.extend(_sample_document(document.document_id, document.content, focus_terms, sample_ratio, remaining))

    if len(samples) < max_samples and task.input_data:
        samples.extend(
            _sample_input_data(
                task.input_data,
                focus_terms=focus_terms,
                sample_ratio=sample_ratio,
                max_samples=max_samples - len(samples),
                source_id="input_data",
            )
        )

    deduped: list[TaskDataSample] = []
    seen_hashes: set[str] = set()
    for sample in samples:
        if sample.content_hash in seen_hashes:
            continue
        deduped.append(sample)
        seen_hashes.add(sample.content_hash)
        if len(deduped) >= max_samples:
            break
    return deduped


def _focus_terms(blocker: Blocker) -> list[str]:
    candidates = [blocker.input_sample or "", blocker.description, blocker.what_would_unblock]
    terms: set[str] = set()
    for value in candidates:
        if not value:
            continue
        if "<<" in value:
            prefix = value.split("<<", 1)[0].strip()
            if prefix:
                terms.add(prefix)
        for match in re.findall(r"[A-Za-z0-9_<>:=;-]{4,}", value):
            terms.add(match)
    return sorted(terms)


def _sample_document(
    source_id: str,
    content: str,
    focus_terms: list[str],
    sample_ratio: float,
    max_samples: int,
) -> list[TaskDataSample]:
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not lines:
        return []
    focus_lines = [line for line in lines if any(term in line for term in focus_terms)]
    chosen_lines = _stable_select(focus_lines or lines, sample_ratio, max_samples)
    return [
        TaskDataSample(
            sample_id=_sample_id(source_id, line),
            source_id=source_id,
            content_hash=_content_hash(line),
            content=line,
            selection_reason="matched blocker focus terms" if line in focus_lines else "sampled from task document",
            metadata={"kind": "document_line"},
        )
        for line in chosen_lines
    ]


def _sample_input_data(
    value: Any,
    *,
    focus_terms: list[str],
    sample_ratio: float,
    max_samples: int,
    source_id: str,
) -> list[TaskDataSample]:
    leaves = list(_iter_data_leaves(value, path=[]))
    if not leaves:
        return []
    focus_leaves = [item for item in leaves if any(term in item[1] for term in focus_terms)]
    chosen = _stable_select(focus_leaves or leaves, sample_ratio, max_samples)
    samples: list[TaskDataSample] = []
    for path, rendered in chosen:
        samples.append(
            TaskDataSample(
                sample_id=_sample_id(source_id, rendered, path),
                source_id=source_id,
                content_hash=_content_hash(rendered),
                content=rendered,
                selection_reason="matched blocker focus terms" if (path, rendered) in focus_leaves else "sampled from input_data",
                metadata={"kind": "input_data", "path": path},
            )
        )
    return samples


def _iter_data_leaves(value: Any, *, path: list[str]) -> list[tuple[str, str]]:
    leaves: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            leaves.extend(_iter_data_leaves(item, path=path + [str(key)]))
        if not value:
            leaves.append((".".join(path) or "root", "{}"))
        return leaves
    if isinstance(value, list):
        for index, item in enumerate(value):
            leaves.extend(_iter_data_leaves(item, path=path + [str(index)]))
        if not value:
            leaves.append((".".join(path) or "root", "[]"))
        return leaves
    rendered = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
    return [(".".join(path) or "root", str(rendered))]


def _stable_select(items: list[Any], sample_ratio: float, max_samples: int) -> list[Any]:
    if not items or max_samples <= 0:
        return []
    target = max(1, math.ceil(len(items) * sample_ratio))
    count = min(len(items), max_samples, target)
    return sorted(items, key=lambda item: _content_hash(_stable_repr(item)))[:count]


def _stable_repr(value: Any) -> str:
    if isinstance(value, tuple):
        return "|".join(str(part) for part in value)
    return str(value)


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _sample_id(source_id: str, content: str, path: str | None = None) -> str:
    material = f"{source_id}|{path or ''}|{content}"
    return f"sample_{_content_hash(material)[:12]}"
