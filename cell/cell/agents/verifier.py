from __future__ import annotations

import ast
import random
import string
from typing import Any

from cell.tools.sandbox import Sandbox
from cell.types import ToolArtifact, ToolSpec, ToolVerdict, VerificationResult


class VerifierAgent:
    """Deterministic tool verification. No LLM calls."""

    async def verify(self, artifact: ToolArtifact, spec: ToolSpec, sandbox: Sandbox) -> ToolVerdict:
        results: list[VerificationResult] = []

        results.append(self._check_syntax(artifact.source_code))
        results.append(self._check_imports(artifact.source_code, sandbox.policy.allowed_imports))
        results.append(self._check_no_network(artifact.source_code))
        results.append(self._check_no_filesystem(artifact.source_code))
        results.append(self._check_no_subprocess(artifact.source_code))

        if not all(result.passed for result in results):
            return _build_verdict(artifact, spec, results)

        for test_case in spec.test_cases:
            results.append(await sandbox.run_test(artifact, test_case))

        for edge_case in spec.edge_cases:
            results.append(await sandbox.run_test(artifact, edge_case))

        for fuzz_input in generate_fuzz_inputs(spec.input_schema, count=10):
            results.append(await sandbox.run_fuzz(artifact, fuzz_input, spec.output_schema))

        for test_case in spec.test_cases:
            try:
                output = await sandbox.execute(artifact, test_case.input)
            except Exception as exc:
                results.append(
                    VerificationResult(
                        check_name=f"schema:{test_case.case_id}",
                        passed=False,
                        details=f"Could not validate output schema because execution failed: {exc}",
                    )
                )
                continue
            results.append(validate_json_schema(output, spec.output_schema, check_name=f"schema:{test_case.case_id}"))

        return _build_verdict(artifact, spec, results)

    def _check_syntax(self, source_code: str) -> VerificationResult:
        try:
            ast.parse(source_code)
            return VerificationResult(check_name="syntax", passed=True, details="Syntax valid")
        except SyntaxError as exc:
            return VerificationResult(check_name="syntax", passed=False, details=f"Syntax error: {exc}")

    def _check_imports(self, source_code: str, allowed_imports: list[str]) -> VerificationResult:
        tree = ast.parse(source_code)
        disallowed: list[str] = []
        allowed = set(allowed_imports)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] not in allowed:
                        disallowed.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = (node.module or "").split(".")[0]
                if module not in allowed:
                    disallowed.append(node.module or "")
        if disallowed:
            return VerificationResult(
                check_name="imports",
                passed=False,
                details=f"Disallowed imports detected: {', '.join(disallowed)}",
            )
        return VerificationResult(check_name="imports", passed=True, details="Imports allowed")

    def _check_no_network(self, source_code: str) -> VerificationResult:
        return _check_ast_forbidden(
            source_code,
            check_name="network",
            forbidden_calls={"socket", "requests", "urllib", "http"},
            forbidden_attributes={"socket", "requests", "urllib", "http"},
        )

    def _check_no_filesystem(self, source_code: str) -> VerificationResult:
        return _check_ast_forbidden(
            source_code,
            check_name="filesystem",
            forbidden_calls={"open"},
            forbidden_attributes={"open"},
        )

    def _check_no_subprocess(self, source_code: str) -> VerificationResult:
        return _check_ast_forbidden(
            source_code,
            check_name="subprocess",
            forbidden_calls={"subprocess", "os.system"},
            forbidden_attributes={"__import__", "eval", "exec", "compile", "system"},
        )


def _build_verdict(
    artifact: ToolArtifact,
    spec: ToolSpec,
    results: list[VerificationResult],
) -> ToolVerdict:
    passed = all(result.passed for result in results)
    failures = [f"{result.check_name}: {result.details}" for result in results if not result.passed]
    return ToolVerdict(
        artifact_id=artifact.artifact_id,
        spec_id=spec.spec_id,
        passed=passed,
        results=results,
        failure_report=None if passed else "; ".join(failures),
    )


def _check_ast_forbidden(
    source_code: str,
    check_name: str,
    forbidden_calls: set[str],
    forbidden_attributes: set[str],
) -> VerificationResult:
    tree = ast.parse(source_code)
    findings: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            target = ast.unparse(node.func)
            if target in forbidden_calls or any(target.startswith(f"{name}.") for name in forbidden_calls):
                findings.append(target)
        if isinstance(node, ast.Attribute) and node.attr in forbidden_attributes:
            findings.append(node.attr)
        if isinstance(node, ast.Name) and node.id in forbidden_attributes:
            findings.append(node.id)
    if findings:
        return VerificationResult(
            check_name=check_name,
            passed=False,
            details=f"Forbidden usage detected: {', '.join(sorted(set(findings)))}",
        )
    return VerificationResult(check_name=check_name, passed=True, details=f"No {check_name} access detected")


def generate_fuzz_inputs(schema: dict[str, Any], count: int = 10) -> list[dict[str, Any]]:
    generator = random.Random(0)
    inputs: list[dict[str, Any]] = []
    for index in range(count):
        inputs.append(_generate_value(schema, generator, index))
    return [item if isinstance(item, dict) else {"value": item} for item in inputs]


def _generate_value(schema: dict[str, Any], generator: random.Random, index: int) -> Any:
    schema_type = schema.get("type")
    if schema_type == "object":
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))
        result: dict[str, Any] = {}
        for name, subschema in properties.items():
            if name in required or generator.random() > 0.35:
                result[name] = _generate_value(subschema, generator, index)
        if schema.get("additionalProperties") is True:
            result[f"extra_{index}"] = index
        return result
    if schema_type == "array":
        items_schema = schema.get("items", {})
        length = [0, 1, 5][index % 3]
        return [_generate_value(items_schema, generator, index + offset) for offset in range(length)]
    if schema_type == "string":
        if "enum" in schema:
            return schema["enum"][index % len(schema["enum"])]
        length = [0, 1, 8, 32][index % 4]
        return "".join(generator.choice(string.ascii_letters + string.digits) for _ in range(length))
    if schema_type == "integer":
        values = [0, -1, 1, 2**31 - 1, -(2**31)]
        return values[index % len(values)]
    if schema_type == "number":
        values = [0, -1, 1, 1.5, -2.75, 10**6]
        return values[index % len(values)]
    if schema_type == "boolean":
        return bool(index % 2)
    if schema_type == "null":
        return None
    return {}


def validate_json_schema(output: Any, schema: dict[str, Any], check_name: str = "output_schema") -> VerificationResult:
    passed = schema_matches(output, schema)
    return VerificationResult(
        check_name=check_name,
        passed=passed,
        details="Output matched schema" if passed else "Output failed schema validation",
        observed_output=output,
    )


def schema_matches(value: Any, schema: dict[str, Any]) -> bool:
    if not schema:
        return True
    schema_type = schema.get("type")
    if not schema_type:
        return True
    if schema_type == "object":
        if not isinstance(value, dict):
            return False
        required = schema.get("required", [])
        if any(name not in value for name in required):
            return False
        properties = schema.get("properties", {})
        for name, subschema in properties.items():
            if name in value and not schema_matches(value[name], subschema):
                return False
        if schema.get("additionalProperties") is False:
            if any(name not in properties for name in value):
                return False
        return True
    if schema_type == "array":
        if not isinstance(value, list):
            return False
        item_schema = schema.get("items", {})
        return all(schema_matches(item, item_schema) for item in value)
    if schema_type == "string":
        if not isinstance(value, str):
            return False
        if "enum" in schema and value not in schema["enum"]:
            return False
        return True
    if schema_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if schema_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if schema_type == "boolean":
        return isinstance(value, bool)
    if schema_type == "null":
        return value is None
    return True

