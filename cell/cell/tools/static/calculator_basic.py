from __future__ import annotations


TOOL_ID = "calculator_basic"
ENTRY_POINT = "calculator_basic"
DESCRIPTION = "Performs arithmetic, percentages, compound interest, and static-rate currency conversion."
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "operation": {
            "type": "string",
            "enum": [
                "add",
                "subtract",
                "multiply",
                "divide",
                "percentage",
                "compound_interest",
                "currency_convert",
            ],
        },
        "operands": {"type": "array", "items": {"type": "number"}},
        "value": {"type": "number"},
        "rate": {"type": "number"},
        "principal": {"type": "number"},
        "periods": {"type": "integer"},
        "amount": {"type": "number"},
        "from_currency": {"type": "string"},
        "to_currency": {"type": "string"},
    },
    "required": ["operation"],
}
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"result": {"type": "number"}},
    "required": ["result"],
    "additionalProperties": False,
}

_RATES = {
    ("USD", "EUR"): 0.92,
    ("EUR", "USD"): 1.09,
    ("USD", "GBP"): 0.78,
    ("GBP", "USD"): 1.28,
}


def calculator_basic(
    operation: str,
    operands: list[float] | None = None,
    value: float | None = None,
    rate: float | None = None,
    principal: float | None = None,
    periods: int | None = None,
    amount: float | None = None,
    from_currency: str | None = None,
    to_currency: str | None = None,
) -> dict[str, float]:
    operands = operands or []
    if operation == "add":
        return {"result": float(sum(operands))}
    if operation == "subtract":
        result = operands[0]
        for operand in operands[1:]:
            result -= operand
        return {"result": float(result)}
    if operation == "multiply":
        result = 1.0
        for operand in operands:
            result *= operand
        return {"result": float(result)}
    if operation == "divide":
        result = operands[0]
        for operand in operands[1:]:
            result /= operand
        return {"result": float(result)}
    if operation == "percentage":
        return {"result": float((value or 0.0) * (rate or 0.0) / 100.0)}
    if operation == "compound_interest":
        return {"result": float((principal or 0.0) * ((1 + (rate or 0.0)) ** int(periods or 0)))}
    if operation == "currency_convert":
        if from_currency == to_currency:
            return {"result": float(amount or 0.0)}
        fx = _RATES[(from_currency or "USD", to_currency or "USD")]
        return {"result": float((amount or 0.0) * fx)}
    raise ValueError(f"Unsupported operation: {operation}")

