from __future__ import annotations

from datetime import datetime, timedelta


TOOL_ID = "date_arithmetic"
ENTRY_POINT = "date_arithmetic"
DESCRIPTION = "Computes day deltas, shifts dates, business days, and fiscal quarters."
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "operation": {"type": "string", "enum": ["days_between", "add_days", "business_days", "fiscal_quarter"]},
        "start_date": {"type": "string"},
        "end_date": {"type": "string"},
        "date": {"type": "string"},
        "days": {"type": "integer"},
        "fiscal_year_start_month": {"type": "integer"},
    },
    "required": ["operation"],
}
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"result": {}},
    "required": ["result"],
}


def _parse_date(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d")


def date_arithmetic(
    operation: str,
    start_date: str | None = None,
    end_date: str | None = None,
    date: str | None = None,
    days: int | None = None,
    fiscal_year_start_month: int | None = None,
) -> dict:
    if operation == "days_between":
        return {"result": abs((_parse_date(end_date or "1970-01-01") - _parse_date(start_date or "1970-01-01")).days)}
    if operation == "add_days":
        return {"result": (_parse_date(date or "1970-01-01") + timedelta(days=int(days or 0))).strftime("%Y-%m-%d")}
    if operation == "business_days":
        start = _parse_date(start_date or "1970-01-01")
        end = _parse_date(end_date or "1970-01-01")
        if end < start:
            start, end = end, start
        count = 0
        cursor = start
        while cursor < end:
            if cursor.weekday() < 5:
                count += 1
            cursor += timedelta(days=1)
        return {"result": count}
    if operation == "fiscal_quarter":
        parsed = _parse_date(date or "1970-01-01")
        fiscal_start = int(fiscal_year_start_month or 1)
        shifted = (parsed.month - fiscal_start) % 12
        return {"result": (shifted // 3) + 1}
    raise ValueError(f"Unsupported operation: {operation}")

