from __future__ import annotations


TOOL_ID = "json_parser"
ENTRY_POINT = "json_parser"
DESCRIPTION = "Queries nested JSON, flattens nested objects, and diffs two JSON values."
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "operation": {"type": "string", "enum": ["query", "flatten", "diff"]},
        "data": {"type": "object"},
        "path": {"type": "string"},
        "left": {"type": "object"},
        "right": {"type": "object"},
    },
    "required": ["operation"],
}
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"result": {}},
    "required": ["result"],
}


def json_parser(
    operation: str,
    data: dict | None = None,
    path: str | None = None,
    left: dict | None = None,
    right: dict | None = None,
) -> dict:
    if operation == "query":
        current = data or {}
        for part in (path or "").split("."):
            if not part:
                continue
            current = current[part]
        return {"result": current}
    if operation == "flatten":
        flat: dict[str, object] = {}

        def _flatten(prefix: str, value: object) -> None:
            if isinstance(value, dict):
                for key, nested in value.items():
                    _flatten(f"{prefix}.{key}" if prefix else key, nested)
            else:
                flat[prefix] = value

        _flatten("", data or {})
        return {"result": flat}
    if operation == "diff":
        diff: dict[str, dict[str, object]] = {}
        left = left or {}
        right = right or {}
        for key in sorted(set(left) | set(right)):
            if left.get(key) != right.get(key):
                diff[key] = {"left": left.get(key), "right": right.get(key)}
        return {"result": diff}
    raise ValueError(f"Unsupported operation: {operation}")

