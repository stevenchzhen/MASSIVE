from __future__ import annotations

from statistics import mean, median


TOOL_ID = "csv_reader"
ENTRY_POINT = "csv_reader"
DESCRIPTION = "Parses CSV text, computes column statistics, and filters rows by equality."
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "operation": {"type": "string", "enum": ["parse", "stats", "filter"]},
        "csv_data": {"type": "string"},
        "column": {"type": "string"},
        "equals": {"type": "string"},
    },
    "required": ["operation", "csv_data"],
}
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"result": {}},
    "required": ["result"],
}


def csv_reader(
    operation: str,
    csv_data: str,
    column: str | None = None,
    equals: str | None = None,
) -> dict:
    lines = [line.strip() for line in csv_data.strip().splitlines() if line.strip()]
    headers = [header.strip() for header in lines[0].split(",")]
    rows = [
        {headers[index]: value.strip() for index, value in enumerate(line.split(","))}
        for line in lines[1:]
    ]
    if operation == "parse":
        return {"result": rows}
    if operation == "stats":
        values = [float(row[column or ""]) for row in rows]
        return {
            "result": {
                "mean": mean(values),
                "median": median(values),
                "sum": sum(values),
                "min": min(values),
                "max": max(values),
            }
        }
    if operation == "filter":
        return {"result": [row for row in rows if row.get(column or "") == equals]}
    raise ValueError(f"Unsupported operation: {operation}")

