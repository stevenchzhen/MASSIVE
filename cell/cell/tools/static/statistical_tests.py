from __future__ import annotations

import math
from statistics import mean, median, pstdev


TOOL_ID = "statistical_tests"
ENTRY_POINT = "statistical_tests"
DESCRIPTION = "Runs basic descriptive statistics, z-scores, correlation, t-tests, chi-square, and percentiles."
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "operation": {
            "type": "string",
            "enum": ["t_test", "chi_square", "z_score", "stddev", "correlation", "percentile"],
        },
        "sample_a": {"type": "array", "items": {"type": "number"}},
        "sample_b": {"type": "array", "items": {"type": "number"}},
        "observed": {"type": "array", "items": {"type": "number"}},
        "expected": {"type": "array", "items": {"type": "number"}},
        "value": {"type": "number"},
        "population_mean": {"type": "number"},
        "population_stddev": {"type": "number"},
        "data": {"type": "array", "items": {"type": "number"}},
        "p": {"type": "number"},
    },
    "required": ["operation"],
}
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"result": {"type": "number"}},
    "required": ["result"],
    "additionalProperties": False,
}


def statistical_tests(
    operation: str,
    sample_a: list[float] | None = None,
    sample_b: list[float] | None = None,
    observed: list[float] | None = None,
    expected: list[float] | None = None,
    value: float | None = None,
    population_mean: float | None = None,
    population_stddev: float | None = None,
    data: list[float] | None = None,
    p: float | None = None,
) -> dict[str, float]:
    sample_a = sample_a or []
    sample_b = sample_b or []
    observed = observed or []
    expected = expected or []
    data = data or []
    if operation == "stddev":
        return {"result": float(pstdev(data))}
    if operation == "z_score":
        return {"result": float(((value or 0.0) - (population_mean or 0.0)) / (population_stddev or 1.0))}
    if operation == "correlation":
        mean_a = mean(sample_a)
        mean_b = mean(sample_b)
        numerator = sum((a - mean_a) * (b - mean_b) for a, b in zip(sample_a, sample_b))
        denom_a = math.sqrt(sum((a - mean_a) ** 2 for a in sample_a))
        denom_b = math.sqrt(sum((b - mean_b) ** 2 for b in sample_b))
        return {"result": float(numerator / (denom_a * denom_b))}
    if operation == "percentile":
        ordered = sorted(data)
        index = int(round(((p or 0.0) / 100.0) * (len(ordered) - 1)))
        return {"result": float(ordered[index])}
    if operation == "chi_square":
        return {
            "result": float(
                sum(((obs - exp) ** 2) / exp for obs, exp in zip(observed, expected) if exp != 0)
            )
        }
    if operation == "t_test":
        mean_diff = mean(sample_a) - mean(sample_b)
        var_a = pstdev(sample_a) ** 2
        var_b = pstdev(sample_b) ** 2
        denom = math.sqrt((var_a / len(sample_a)) + (var_b / len(sample_b)))
        return {"result": float(mean_diff / denom)}
    raise ValueError(f"Unsupported operation: {operation}")

